"""
区块链交易数据自动获取模块
===========================
根据 chain_id + tx_hash 自动从链上获取交易数据，
解析为符合业务规则的标准数据结构，消除用户手动输入导致的格式问题。

核心能力:
  1. 通过 MultiRpcClient 获取交易详情 + 收据
  2. 解析 receipt logs 中的 Transfer/Approval 事件
  3. 提取攻击者/被攻击地址（启发式推断）
  4. 输出符合 KnowledgeBaseCreate.alert_data 结构的标准字典
"""

import logging
import time
from typing import Any, Optional

from detectors.trace.provider import MultiRpcClient, get_rpc_client, CHAIN_META

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────
# 常量
# ────────────────────────────────────────────

# ERC20 Transfer event topic
_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
# ERC20 Approval event topic
_APPROVAL_TOPIC = "0x8c5be1e5ebec7d5bd14f7f27da2898506d9e09ccf5c36a18b47b4dd681bc0b41"


# ────────────────────────────────────────────
# 核心类
# ────────────────────────────────────────────

class TxFetcher:
    """
    交易数据自动获取器 — 从链上拉取交易数据并解析为标准结构。

    用法:
        fetcher = TxFetcher()
        result = await fetcher.fetch(chain_id=1, tx_hash="0x...")
        # result.alert_data 可直接用于创建知识库样本
    """

    def __init__(self, rpc_client: Optional[MultiRpcClient] = None):
        self._rpc = rpc_client or get_rpc_client()

    async def fetch(self, chain_id: int, tx_hash: str) -> dict[str, Any]:
        """
        从链上获取交易数据并解析为标准结构。

        Args:
            chain_id: 链 ID (如 1=Ethereum, 56=BSC, 137=Polygon)
            tx_hash: 交易哈希 (0x 开头，64 位十六进制)

        Returns:
            包含完整交易信息的字典:
            {
                "chain_id": int,
                "tx_hash": str,
                "alert_data": { ... },       # 标准告警数据
                "attacked_address": str|None, # 推断的被攻击地址
                "exploiter_address": str|None,# 推断的攻击者地址
                "title": str,                # 自动生成的标题
                "tx_explorer_url": str,      # 区块浏览器链接
            }

        Raises:
            ValueError: tx_hash 格式无效或链不支持
            RuntimeError: 链上数据获取失败
        """
        # ── 1. 参数校验与规范化 ──
        tx_hash = self._normalize_tx_hash(tx_hash)
        self._validate_chain_id(chain_id)

        logger.info(
            f"[TxFetcher] Fetching tx {tx_hash[:16]}... on chain {chain_id}"
        )

        # ── 2. 并行获取链上数据 ──
        import asyncio
        tx_detail, receipt = await asyncio.gather(
            self._rpc.get_transaction_by_hash(tx_hash, chain_id),
            self._rpc.get_transaction_receipt(tx_hash, chain_id),
            return_exceptions=True,
        )

        # 处理异常
        if isinstance(tx_detail, Exception):
            raise RuntimeError(
                f"获取交易详情失败 (chain={chain_id}, tx={tx_hash[:16]}...): "
                f"{tx_detail}"
            ) from tx_detail
        if isinstance(receipt, Exception):
            raise RuntimeError(
                f"获取交易收据失败 (chain={chain_id}, tx={tx_hash[:16]}...): "
                f"{receipt}"
            ) from receipt

        if not tx_detail:
            raise RuntimeError(
                f"交易不存在或尚未上链 (chain={chain_id}, tx={tx_hash[:16]}...)"
            )

        # ── 2.5 确保收据数据有效 (重试机制) ──
        # RPC 节点可能返回 HTTP 200 + null（非异常），需要应用层重试
        # 参考: detectors/trace/analyzer.py _ensure_valid_data
        receipt = await self._ensure_valid_data(
            receipt, "receipt", tx_hash, chain_id,
            lambda: self._rpc.get_transaction_receipt(tx_hash, chain_id),
        )

        # ── 3. 解析交易详情 ──
        from_addr = tx_detail.get("from", "")
        to_addr = tx_detail.get("to", "")
        value_hex = tx_detail.get("value", "0x0")
        gas_price_hex = tx_detail.get("gasPrice", "0x0")
        gas_hex = tx_detail.get("gas", "0x0")
        nonce_hex = tx_detail.get("nonce", "0x0")
        input_data = tx_detail.get("input", "0x")
        block_number_hex = tx_detail.get("blockNumber", "0x0")

        # ── 4. 解析收据 ──
        gas_used_hex = "0x0"
        status = True
        receipt_logs: list[dict] = []

        if receipt and isinstance(receipt, dict):
            gas_used_hex = receipt.get("gasUsed", "0x0")
            status_hex = receipt.get("status", "0x1")
            status = int(status_hex, 16) == 1 if isinstance(status_hex, str) else bool(status_hex)
            receipt_logs = receipt.get("logs", [])
        else:
            logger.warning(
                f"[TxFetcher] Receipt is still empty after retries "
                f"(chain={chain_id}, tx={tx_hash[:16]}...)"
            )

        # ── 5. 解析 Transfer 事件 ──
        transfers = self._parse_transfer_events(receipt_logs)

        # ── 6. 推断攻击者/被攻击地址 ──
        attacked_address, exploiter_address = self._infer_addresses(
            from_addr, to_addr, transfers
        )

        # ── 7. 构建标准 alert_data ──
        chain_name = CHAIN_META.get(chain_id, {}).get("name", f"Chain-{chain_id}")
        explorer_base = CHAIN_META.get(chain_id, {}).get("explorer", "")

        value_wei = int(value_hex, 16) if isinstance(value_hex, str) else value_hex
        gas_price_wei = int(gas_price_hex, 16) if isinstance(gas_price_hex, str) else gas_price_hex
        gas_limit = int(gas_hex, 16) if isinstance(gas_hex, str) else gas_hex
        gas_used = int(gas_used_hex, 16) if isinstance(gas_used_hex, str) else gas_used_hex
        block_number = int(block_number_hex, 16) if isinstance(block_number_hex, str) else block_number_hex
        nonce = int(nonce_hex, 16) if isinstance(nonce_hex, str) else nonce_hex

        alert_data = {
            "chain_id": chain_id,
            "tx_hash": tx_hash,
            "from_address": from_addr,
            "to_address": to_addr,
            "value_wei": value_wei,
            "value_eth": value_wei / 1e18 if value_wei else 0,
            "gas_price_wei": gas_price_wei,
            "gas_limit": gas_limit,
            "gas_used": gas_used,
            "nonce": nonce,
            "block_number": block_number,
            "status": "success" if status else "reverted",
            "input_data": input_data,
            "transfers": transfers,
            "log_count": len(receipt_logs),
        }

        # ── 8. 构建标题 ──
        title = self._generate_title(
            chain_name=chain_name,
            from_addr=from_addr,
            to_addr=to_addr,
            value_wei=value_wei,
            status=status,
        )

        return {
            "chain_id": chain_id,
            "tx_hash": tx_hash,
            "alert_data": alert_data,
            "attacked_address": attacked_address,
            "exploiter_address": exploiter_address,
            "title": title,
            "tx_explorer_url": f"{explorer_base}{tx_hash}" if explorer_base else None,
        }

    # ────────────────────────────────────────
    # 私有方法
    # ────────────────────────────────────────

    async def _ensure_valid_data(
        self,
        first_result: Any,
        label: str,
        tx_hash: str,
        chain_id: int,
        fetch_fn,
        max_retries: int = 5,
    ) -> Any:
        """
        确保 RPC 返回有效数据（非 None / 非 Exception）。

        RPC 内核层 (apipool-server) 只在网络错误/限流时切换节点，
        但 HTTP 200 + null 响应被视为"成功"，不触发节点轮换。
        本方法在应用层补充重试逻辑：首次结果无效时重新调用 fetch_fn，
        每次调用都会触发内核层的 key 轮换，直到拿到有效数据或达到上限。

        参考: detectors/trace/analyzer.py _ensure_valid_data

        Args:
            first_result: asyncio.gather 的首次返回值
            label: 日志标签，如 "receipt"
            tx_hash: 交易哈希（用于日志）
            chain_id: 链 ID
            fetch_fn: 无参异步函数，用于重新获取数据
            max_retries: 最大重试次数
        """
        if first_result is not None and first_result is not False:
            return first_result

        logger.warning(
            f"[TxFetcher] {label} is null/empty for {tx_hash[:16]}... "
            f"(chain={chain_id}), retrying up to {max_retries} times..."
        )

        for attempt in range(1, max_retries + 1):
            try:
                result = await fetch_fn()
                if result is not None and result is not False:
                    logger.info(
                        f"[TxFetcher] {label} obtained on attempt {attempt}/{max_retries} "
                        f"for {tx_hash[:16]}... (chain={chain_id})"
                    )
                    return result
                else:
                    logger.debug(
                        f"[TxFetcher] {label} still null on attempt "
                        f"{attempt}/{max_retries} (chain={chain_id})"
                    )
            except Exception as e:
                logger.warning(
                    f"[TxFetcher] {label} retry {attempt}/{max_retries} error: {e}"
                )

        raise RuntimeError(
            f"无法获取有效的 {label} 数据 "
            f"(chain={chain_id}, tx={tx_hash[:16]}...)，"
            f"已重试 {max_retries} 次。RPC 可能不支持或交易尚未上链。"
        )

    @staticmethod
    def _normalize_tx_hash(tx_hash: str) -> str:
        """
        规范化交易哈希:
        - 去除首尾空白
        - 确保以 0x 开头
        - 转为小写
        - 验证长度和格式
        """
        if not tx_hash:
            raise ValueError("交易哈希不能为空")

        tx_hash = tx_hash.strip()

        # 自动补 0x 前缀
        if not tx_hash.startswith("0x") and not tx_hash.startswith("0X"):
            tx_hash = "0x" + tx_hash

        tx_hash = tx_hash.lower()

        # 验证格式: 0x + 64 位十六进制
        hex_part = tx_hash[2:]
        if len(hex_part) != 64:
            raise ValueError(
                f"交易哈希长度无效: 期望 64 位十六进制字符, 实际 {len(hex_part)} 位"
            )
        if not all(c in "0123456789abcdef" for c in hex_part):
            raise ValueError("交易哈希包含非法字符, 仅允许十六进制字符 (0-9, a-f)")

        return tx_hash

    @staticmethod
    def _validate_chain_id(chain_id: int):
        """验证链 ID 是否在支持范围内"""
        if not isinstance(chain_id, int) or chain_id <= 0:
            raise ValueError(f"链 ID 必须为正整数, 收到: {chain_id}")

        # 不强制限制 chain_id 范围, 仅给出警告
        if chain_id not in CHAIN_META:
            logger.warning(
                f"[TxFetcher] Chain {chain_id} 不在已知链列表中, "
                f"可能缺少 RPC 配置。已知链: {list(CHAIN_META.keys())}"
            )

    @staticmethod
    def _parse_transfer_events(logs: list[dict]) -> list[dict[str, Any]]:
        """
        从 receipt logs 中解析 ERC20 Transfer 事件。

        Returns:
            [{"from": "0x...", "to": "0x...", "value": int, "token": "0x..."}, ...]
        """
        transfers: list[dict[str, Any]] = []
        for log in logs:
            topics = log.get("topics", [])
            if not topics:
                continue

            topic0 = topics[0].lower() if isinstance(topics[0], str) else ""

            if topic0 == _TRANSFER_TOPIC and len(topics) >= 3:
                token_address = log.get("address", "")
                # topics[1] = from (indexed), topics[2] = to (indexed)
                from_addr = "0x" + topics[1][-40:] if len(topics[1]) >= 40 else topics[1]
                to_addr = "0x" + topics[2][-40:] if len(topics[2]) >= 40 else topics[2]

                # data = value (非 indexed)
                data = log.get("data", "0x0")
                try:
                    value = int(data, 16) if isinstance(data, str) else data
                except (ValueError, TypeError):
                    value = 0

                transfers.append({
                    "from": from_addr.lower(),
                    "to": to_addr.lower(),
                    "value": value,
                    "token": token_address.lower(),
                })

        return transfers

    @staticmethod
    def _infer_addresses(
        from_addr: str,
        to_addr: str,
        transfers: list[dict[str, Any]],
    ) -> tuple[Optional[str], Optional[str]]:
        """
        启发式推断攻击者与被攻击地址。

        策略:
          - 攻击者 = tx.from (交易发起方)
          - 被攻击 = tx.to 或第一个大额 Transfer 的 to 地址

        注意: 这是简单启发式，实际场景可能需要更复杂的分析。
        """
        if not from_addr:
            return None, None

        exploiter = from_addr

        # 如果有 Transfer 事件，找到最大接收方作为候选被攻击地址
        attacked = to_addr or None

        if transfers:
            # 找到价值最大的 Transfer 接收方
            max_transfer = max(transfers, key=lambda t: t.get("value", 0))
            if max_transfer.get("to") and max_transfer["to"] != from_addr.lower():
                attacked = max_transfer["to"]

        return attacked, exploiter

    @staticmethod
    def _generate_title(
        chain_name: str,
        from_addr: str,
        to_addr: str,
        value_wei: int,
        status: bool,
    ) -> str:
        """生成自动标题"""
        from_short = f"{from_addr[:8]}...{from_addr[-6:]}" if from_addr else "???"
        to_short = f"{to_addr[:8]}...{to_addr[-6:]}" if to_addr else "Contract Create"

        value_eth = value_wei / 1e18 if value_wei else 0
        value_str = f"{value_eth:.4f} ETH" if 0 < value_eth < 100000 else f"{value_wei} wei"

        status_str = "✓" if status else "✗ REVERTED"

        return f"[{chain_name}] {from_short} → {to_short} | {value_str} {status_str}"


# ────────────────────────────────────────────
# 全局单例
# ────────────────────────────────────────────

_global_fetcher: Optional[TxFetcher] = None


def get_tx_fetcher() -> TxFetcher:
    """获取全局 TxFetcher 单例"""
    global _global_fetcher
    if _global_fetcher is None:
        _global_fetcher = TxFetcher()
    return _global_fetcher
