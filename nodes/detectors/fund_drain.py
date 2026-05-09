"""资金外流检测器 — 全地址盈亏分析模式

对交易内所有地址进行 USD 盈亏计算，识别最大获利者和最大亏损者，
以此判断是否存在攻击行为（获利者 ≠ sender 的间接受益场景也能检测）。

核心逻辑:
  1. 全地址盈亏计算: 遍历所有 transfer，按 (地址, token) 聚合净变化量，折算 USD
  2. 识别最大获利者/最大亏损者
  3. 基于获利/亏损 USD 价值判断严重度
  4. 关联检测: 上游 Combiner 注入的关联地址匹配
  5. ROI 计算: 最大获利者的 USD / tx.value(USD)
  6. 销毁-释放关联、Swap-Burn-Claim 闭环

数据源优先级:
  1. tx_context.extra["transfers"]: 已解析的转账列表（推荐，含完整 from/to/value/token）
  2. tx_context.logs: 原始 ERC-20 事件日志（fallback）

所有代币价格统一通过 TokenPriceCache 获取（含硬编码 fallback）。
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from pydantic import Field

from nodes.base import NodeRegistry, score_to_severity
from nodes.detectors.base import BaseDetector, DetectorConfigMixin, DetectorOutputMixin
from nodes.models import TransactionContext


class FundDrainOutput(DetectorOutputMixin):
    """资金外流检测器输出"""
    pass


logger = logging.getLogger(__name__)

# ERC-20 Transfer 事件 Topic
ERC20_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# Uniswap V2/V3 Swap 事件 Topic
UNISWAP_V2_SWAP_TOPIC = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d714"
UNISWAP_V3_SWAP_TOPIC = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e7b213eb771"

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

# 原生代币占位地址（TokenPriceCache 中原生代币用空字符串查询）
NATIVE_TOKEN_ADDRESS = ""

# 已知的 DEX/中间合约地址（不参与盈亏排名）
KNOWN_PROTOCOL_ADDRESSES: set[str] = {
    # Uniswap V2 Router
    "0x7a250d5630b4cf539739df2c5dacb4c659f2488d",
    # Uniswap V3 Router
    "0xe592427a0aece92de3edee1f18e0157c05861564",
    # WETH
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
}

# WETH 地址 → 各链映射（WETH 等价于原生 ETH，价格相同）
WETH_ADDRESSES: dict[int, str] = {
    1: "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",       # Ethereum WETH
    56: "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c",       # BSC WBNB
    137: "0x7ceb23fd6bc0add59e62ac25578270cff1b9f219",      # Polygon WETH
    42161: "0x82af49447d8a07e3bd95bd0d56f35241523fbab1",    # Arbitrum WETH
    10: "0x4200000000000000000000000000000000000006",       # Optimism WETH
}

# 反向映射: WETH 地址 → chain_id（用于快速查找）
_WETH_TO_CHAIN: dict[str, int] = {v.lower(): k for k, v in WETH_ADDRESSES.items()}


def _hex_to_int(val: Any) -> int:
    if isinstance(val, int):
        return val
    if isinstance(val, str) and val.startswith("0x"):
        try:
            return int(val, 16)
        except ValueError:
            return 0
    return 0


def _to_int(val: Any) -> int:
    """将各种格式的数值转为 int（支持科学计数法 float）"""
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    if isinstance(val, str):
        if val.startswith("0x"):
            return _hex_to_int(val)
        try:
            return int(val)
        except (ValueError, TypeError):
            try:
                return int(float(val))
            except (ValueError, TypeError):
                return 0
    return 0


def _extract_topic0(log: dict) -> str:
    topics = log.get("topics", [])
    if not topics:
        return ""
    t = topics[0]
    return (t if isinstance(t, str) else t.hex() if isinstance(t, bytes) else "").lower()


def _extract_address_from_topic(topic: str) -> str:
    h = topic.lstrip("0x").lower()
    if len(h) < 40:
        return "0x" + "0" * 40 if len(h) == 0 else "0x" + h.zfill(40)
    return "0x" + h[-40:]


# ---------------------------------------------------------------------------
# 盈亏计算
# ---------------------------------------------------------------------------

class AddressPnL:
    """单个地址的盈亏记录"""
    __slots__ = ("address", "token_changes", "total_usd")

    def __init__(self, address: str):
        self.address = address
        # token_address → 净变化量 (正=收入, 负=支出)
        self.token_changes: dict[str, int] = defaultdict(int)
        # 总 USD 盈亏（延迟计算）
        self.total_usd: float = 0.0

    def add_incoming(self, token: str, amount: int) -> None:
        self.token_changes[token] += amount

    def add_outgoing(self, token: str, amount: int) -> None:
        self.token_changes[token] -= amount


def compute_all_pnl(transfers: list[dict]) -> dict[str, AddressPnL]:
    """
    从转账列表计算所有地址的盈亏。

    Args:
        transfers: [{"from", "to", "value", "token"}, ...]
            token 为空或不存在时视为原生代币转账

    Returns:
        {address_lower: AddressPnL}
    """
    pnl_map: dict[str, AddressPnL] = {}

    for t in transfers:
        from_addr = (t.get("from") or "").lower()
        to_addr = (t.get("to") or "").lower()
        amount = _to_int(t.get("value", 0))
        token = (t.get("token") or "").lower()

        if amount <= 0 or not from_addr or not to_addr:
            continue

        # 跳过零地址的铸造/销毁对零地址端的影响
        if from_addr == ZERO_ADDRESS and to_addr == ZERO_ADDRESS:
            continue

        # 支出方
        if from_addr != ZERO_ADDRESS:
            if from_addr not in pnl_map:
                pnl_map[from_addr] = AddressPnL(from_addr)
            pnl_map[from_addr].add_outgoing(token, amount)

        # 收入方
        if to_addr != ZERO_ADDRESS:
            if to_addr not in pnl_map:
                pnl_map[to_addr] = AddressPnL(to_addr)
            pnl_map[to_addr].add_incoming(token, amount)

    return pnl_map


# ---------------------------------------------------------------------------
# FundDrainDetector
# ---------------------------------------------------------------------------

class FundDrainDetector(BaseDetector):
    """
    资金外流检测器 — 全地址盈亏分析模式。

    对交易内所有地址进行 USD 盈亏计算，识别最大获利者和最大亏损者，
    以此判断是否存在攻击行为。

    核心改进:
      - 不再只看 sender 的资金流出，而是计算所有地址的净盈亏
      - 攻击者通过中间地址获利的间接场景也能检测
      - 基于最大获利/亏损 USD 价值判断严重度

    数据源:
      - 优先使用 tx_context.extra["transfers"]（已解析的转账列表）
      - 回退到 tx_context.logs（原始 ERC-20 事件日志）
    """

    name: str = "fund_drain_detector"
    label: str = "资金外流检测"
    description: str = (
        "[数据需求: Logs + Trace(辅助)] "
        "全地址盈亏分析：计算交易内所有地址的 USD 净盈亏，"
        "识别最大获利者和最大亏损者，检测攻击行为。"
        "攻击者通过中间地址获利的间接场景也能检测。"
        "支持 ROI 计算、销毁-释放关联、Swap-Burn-Claim 闭环检测。"
        "辅助使用 eth_trace 提取内部 ETH 转账数据。"
    )
    icon: str = "\U0001f4b8"
    color: str = "#ef4444"

    # ── Pydantic 配置模型 ──
    class ConfigModel(DetectorConfigMixin):
        large_threshold_usd: float = Field(
            default=50000.0, ge=0,
            description="大额盈亏 USD 阈值，单地址净盈亏绝对值 >= 此值判定为 large",
        )
        medium_threshold_usd: float = Field(
            default=5000.0, ge=0,
            description="中额盈亏 USD 阈值，单地址净盈亏绝对值 >= 此值判定为 medium",
        )
        correlation_fields: list[str] = Field(
            default=["upgraded_contracts"],
            description="关联检测：从 extra 中读取的地址列表字段名（由 Combiner 注入）",
        )
        multi_asset_min_tokens: int = Field(
            default=2, ge=2,
            description="最大亏损地址涉及多少种流出资产时视为多资产外流",
        )
        receiver_cluster_min_count: int = Field(
            default=2, ge=2,
            description="受害地址向多少个外部接收方集中流出时视为接收方聚合",
        )
        receiver_cluster_min_share: float = Field(
            default=0.6, ge=0, le=1,
            description="接收方聚合检测所需的外流占比阈值",
        )
        # ── ROI 增强配置 ──
        enable_roi_check: bool = Field(default=True, description="是否启用 ROI 异常检测")
        roi_threshold: float = Field(default=50.0, ge=1.0, description="ROI 阈值（倍数），超过此值视为异常")
        min_tx_value_eth: float = Field(
            default=0.001, ge=0,
            description="最小 tx.value（ETH），低于此值用绝对获利判断而非 ROI 比值",
        )
        # ── 销毁-释放关联配置 ──
        enable_burn_drain_check: bool = Field(default=True, description="是否启用销毁-释放关联检测")
        enable_swap_burn_claim_check: bool = Field(default=True, description="是否启用 Swap-Burn-Claim 闭环检测")
        # ── 过滤配置 ──
        exclude_known_protocols: bool = Field(
            default=True,
            description="是否排除已知 DEX/协议地址的盈亏（减少噪音）",
        )

    # ── Pydantic 输出模型 ──
    OutputModel: type = FundDrainOutput

    # ── 价格查询辅助 ──

    def _calc_token_value_usd(
        self, chain_id: int, token_address: str, amount_raw: int,
        native_price: float,
        price_warned_tokens: set[str],
    ) -> tuple[float, float | None, int]:
        """
        计算一笔代币数量的 USD 价值。

        Returns:
            (value_usd, price_usd, decimals)
        """
        # 优先使用 Provider 提供的价格数据
        token_prices = self.get_token_prices(self._current_tx_context)
        cache = self.token_price_instance

        # 原生代币
        if not token_address or token_address == ZERO_ADDRESS:
            decimals = 18
            value = (amount_raw / 10**decimals) * native_price
            return value, native_price if native_price > 0 else None, decimals

        # WETH 等包装代币 → 等价于原生代币
        if token_address.lower() in _WETH_TO_CHAIN:
            decimals = 18
            value = (amount_raw / 10**decimals) * native_price
            return value, native_price if native_price > 0 else None, decimals

        # ERC-20 代币 - 优先使用 Provider 数据
        price = token_prices.get(token_address.lower())

        # 如果 Provider 没有提供价格，回退到 token_price_instance
        if price is None:
            price = cache.get_price(chain_id, token_address)

        meta = cache.get(chain_id, token_address)
        decimals = meta.decimals if meta and meta.decimals else 18

        if price is not None and price > 0:
            value = (amount_raw / 10**decimals) * price
            return value, price, decimals

        # 价格查不到 → warning 并计为 0
        token_key = f"{chain_id}:{token_address}"
        if token_key not in price_warned_tokens:
            logger.warning(
                f"[FundDrainDetector] 代币价格未查到 (chain_id={chain_id}, "
                f"token={token_address})，该代币 USD 价值将计为 0"
            )
            price_warned_tokens.add(token_key)
        return 0.0, None, decimals

    def _compute_address_pnl_usd(
        self,
        pnl: AddressPnL,
        chain_id: int,
        native_price: float,
        price_warned_tokens: set[str],
    ) -> float:
        """计算单个地址的总 USD 盈亏"""
        total_usd = 0.0
        for token, net_amount in pnl.token_changes.items():
            if net_amount == 0:
                continue
            value_usd, _, _ = self._calc_token_value_usd(
                chain_id, token, abs(net_amount), native_price, price_warned_tokens,
            )
            total_usd += value_usd if net_amount > 0 else -value_usd
        pnl.total_usd = total_usd
        return total_usd

    # ── 地址提取 ──

    def _get_correlated_addresses(self, tx_context: TransactionContext) -> set[str]:
        """从 tx_context.extra 中读取关联地址集合"""
        correlation_fields: list[str] = self.config.get("correlation_fields", ["upgraded_contracts"])
        addrs: set[str] = set()
        for field_name in correlation_fields:
            value = tx_context.extra.get(field_name, [])
            if isinstance(value, str):
                value = [value]
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item.startswith("0x"):
                        addrs.add(item.lower())
        return addrs

    # ── 转账数据解析 ──

    def _extract_transfers_from_context(self, tx_context: TransactionContext) -> list[dict]:
        """
        从 tx_context 提取转账列表。

        优先使用 extra["transfers"]（已解析），否则从 logs 解析 ERC-20 Transfer 事件。
        """
        # 优先: 已解析的 transfers
        extra_transfers = tx_context.extra.get("transfers")
        if extra_transfers and isinstance(extra_transfers, list) and len(extra_transfers) > 0:
            return extra_transfers

        # Fallback: 从 logs 解析
        logs: list[dict] = tx_context.logs or []
        if not logs:
            return []

        transfers = []
        for log in logs:
            topic0 = _extract_topic0(log)
            if topic0 != ERC20_TRANSFER_TOPIC.lower():
                continue
            topics = log.get("topics", [])
            if len(topics) < 3:
                continue
            token_from = _extract_address_from_topic(topics[1]) if len(topics) > 1 else ""
            token_to = _extract_address_from_topic(topics[2]) if len(topics) > 2 else ""
            data = log.get("data", "0x")
            amount = _hex_to_int(data) if data else 0
            token_addr = (log.get("address") or "").lower()
            if amount > 0:
                transfers.append({
                    "from": token_from,
                    "to": token_to,
                    "value": amount,
                    "token": token_addr,
                })

        return transfers

    def _extract_burn_mint_swap_from_logs(self, tx_context: TransactionContext):
        """从 logs 中提取 burn/mint/swap 事件（用于关联检测）"""
        logs: list[dict] = tx_context.logs or []
        burn_events, swap_events, all_transfers = [], [], []

        for log in logs:
            topic0 = _extract_topic0(log)
            log_index = log.get("logIndex", log.get("log_index", 0))
            if isinstance(log_index, str) and log_index.startswith("0x"):
                log_index = int(log_index, 16)

            if topic0 == ERC20_TRANSFER_TOPIC.lower():
                topics = log.get("topics", [])
                if len(topics) < 3:
                    continue
                token_from = _extract_address_from_topic(topics[1]) if len(topics) > 1 else ""
                token_to = _extract_address_from_topic(topics[2]) if len(topics) > 2 else ""
                data = log.get("data", "0x")
                amount = _hex_to_int(data) if data else 0
                token_addr = (log.get("address") or "").lower()

                all_transfers.append({
                    "log_index": log_index, "token": token_addr,
                    "from": token_from, "to": token_to, "amount": amount,
                })
                if token_to == ZERO_ADDRESS:
                    burn_events.append({
                        "log_index": log_index, "token": token_addr,
                        "from": token_from, "amount": amount,
                    })

            elif topic0 in (UNISWAP_V2_SWAP_TOPIC.lower(), UNISWAP_V3_SWAP_TOPIC.lower()):
                swap_type = "uniswap_v3" if topic0 == UNISWAP_V3_SWAP_TOPIC.lower() else "uniswap_v2"
                swap_events.append({
                    "log_index": log_index,
                    "pool": (log.get("address") or "").lower(),
                    "swap_type": swap_type,
                })

        return burn_events, swap_events, all_transfers

    def _extract_burn_mint_swap_from_transfers(self, transfers: list[dict]):
        """从 extra["transfers"] 数据中提取 burn/mint/swap 事件（用于关联检测）

        当 logs 为空但 transfers 有数据时，从 transfers 中识别:
        - burn: to == ZERO_ADDRESS
        - mint: from == ZERO_ADDRESS
        - swap: 需要从 logs 识别，transfers 中无 swap 事件标记

        使用数组索引作为 log_index 的替代，保持时序。
        """
        burn_events, all_transfers = [], []

        for idx, t in enumerate(transfers):
            from_addr = (t.get("from") or "").lower()
            to_addr = (t.get("to") or "").lower()
            amount = _to_int(t.get("value", 0))
            token = (t.get("token") or "").lower()

            if amount <= 0:
                continue

            all_transfers.append({
                "log_index": idx,
                "token": token,
                "from": from_addr,
                "to": to_addr,
                "amount": amount,
            })
            if to_addr == ZERO_ADDRESS:
                burn_events.append({
                    "log_index": idx,
                    "token": token,
                    "from": from_addr,
                    "amount": amount,
                })

        # swap_events 无法从 transfers 中提取，返回空
        return burn_events, [], all_transfers

    def _extract_internal_eth_transfers(self, tx_context: TransactionContext) -> list[dict]:
        """
        从 eth_trace 数据中提取内部 ETH 转账（value > 0 的调用）。

        这些是合约内部的 ETH 转出（如 FeesClaimed、withdraw 等），
        不出现在 ERC-20 Transfer 事件中，但对 ROI 计算至关重要。

        Returns:
            [{"from", "to", "value", "token"}, ...]  token="" 表示原生代币
        """
        eth_trace = tx_context.get_extra("eth_trace")
        if not eth_trace or not isinstance(eth_trace, dict):
            return []

        traces = eth_trace.get("traces") or []
        if not traces:
            return []

        internal_transfers: list[dict] = []
        from_addr = (tx_context.from_address or "").lower()
        to_addr = (tx_context.to_address or "").lower()

        for entry in traces:
            # 兼容 dict 和 Pydantic model
            if hasattr(entry, "action"):
                action = entry.action
                action_dict = {
                    "callType": getattr(action, "call_type", "") or getattr(action, "callType", ""),
                    "from": getattr(action, "from_addr", "") or getattr(action, "from", ""),
                    "to": getattr(action, "to_addr", "") or getattr(action, "to", ""),
                    "value": getattr(action, "value", "0x0"),
                }
            elif isinstance(entry, dict):
                action = entry.get("action", {})
                action_dict = action
            else:
                continue

            value_hex = action_dict.get("value", "0x0")
            if isinstance(value_hex, str):
                value = _hex_to_int(value_hex)
            elif isinstance(value_hex, int):
                value = value_hex
            else:
                value = 0

            if value <= 0:
                continue

            call_from = (action_dict.get("from") or "").lower()
            call_to = (action_dict.get("to") or "").lower()

            # 跳过最顶层调用（它就是 tx.value 本身，已在 process() 中添加）
            # 顶层调用的特征: from = tx.from_address, to = tx.to_address, value = tx.value
            if (call_from == from_addr and call_to == to_addr
                    and value == _hex_to_int(tx_context.extra.get("value_wei") or tx_context.value or 0)):
                continue

            internal_transfers.append({
                "from": call_from,
                "to": call_to,
                "value": value,
                "token": "",  # 原生代币
            })

        return internal_transfers

    def _build_outflow_signals(
        self,
        *,
        transfers: list[dict],
        victim_address: str | None,
        chain_id: int,
        native_price: float,
        price_warned_tokens: set[str],
        known_protocol_addresses: set[str],
    ) -> dict[str, Any]:
        if not victim_address:
            return {
                "victim_address": None,
                "loss_tokens": [],
                "receiver_count": 0,
                "known_receiver_count": 0,
                "external_receiver_count": 0,
                "external_outflow_usd": 0.0,
                "external_outflow_share": 0.0,
                "top_external_receivers": [],
                "multi_asset_outflow": False,
                "receiver_cluster": False,
            }

        token_outflows: dict[str, dict[str, Any]] = {}
        receiver_totals: dict[str, float] = defaultdict(float)
        known_receiver_count = 0
        external_receiver_count = 0
        external_outflow_usd = 0.0

        for transfer in transfers:
            from_addr = (transfer.get("from") or "").lower()
            to_addr = (transfer.get("to") or "").lower()
            if from_addr != victim_address or not to_addr or to_addr == ZERO_ADDRESS:
                continue

            token = (transfer.get("token") or "").lower()
            amount_raw = _to_int(transfer.get("value", 0))
            if amount_raw <= 0:
                continue

            value_usd, _, _ = self._calc_token_value_usd(
                chain_id, token, amount_raw, native_price, price_warned_tokens,
            )

            token_stats = token_outflows.setdefault(token, {
                "token": token,
                "amount_raw": 0,
                "outflow_usd": 0.0,
            })
            token_stats["amount_raw"] += amount_raw
            token_stats["outflow_usd"] += value_usd

            receiver_totals[to_addr] += value_usd
            if to_addr in known_protocol_addresses:
                known_receiver_count += 1
            else:
                external_receiver_count += 1
                external_outflow_usd += value_usd

        loss_tokens = [
            {
                "token": token,
                "amount_raw": str(stats["amount_raw"]),
                "outflow_usd": round(stats["outflow_usd"], 2),
            }
            for token, stats in sorted(
                token_outflows.items(),
                key=lambda item: item[1]["outflow_usd"],
                reverse=True,
            )
            if stats["amount_raw"] > 0
        ]

        external_receivers = [
            {
                "address": address,
                "outflow_usd": round(total_usd, 2),
            }
            for address, total_usd in sorted(
                receiver_totals.items(),
                key=lambda item: item[1],
                reverse=True,
            )
            if address not in known_protocol_addresses and total_usd > 0
        ]
        total_receiver_outflow_usd = sum(item["outflow_usd"] for item in external_receivers)
        top_receiver_usd = external_receivers[0]["outflow_usd"] if external_receivers else 0.0
        external_share = (
            top_receiver_usd / total_receiver_outflow_usd
            if total_receiver_outflow_usd > 0 else 0.0
        )

        return {
            "victim_address": victim_address,
            "loss_tokens": loss_tokens,
            "receiver_count": len(receiver_totals),
            "known_receiver_count": known_receiver_count,
            "external_receiver_count": len(external_receivers),
            "external_outflow_usd": round(total_receiver_outflow_usd, 2),
            "external_outflow_share": round(external_share, 4),
            "top_external_receivers": external_receivers[:5],
            "multi_asset_outflow": False,
            "receiver_cluster": False,
        }

    # ── 主逻辑 ──

    async def process(self, tx_context: TransactionContext) -> FundDrainOutput:
        # Store tx_context for use in helper methods
        self._current_tx_context = tx_context

        tx_value_wei = _hex_to_int(tx_context.extra.get("value_wei") or tx_context.value or 0)
        from_addr = (tx_context.from_address or "").lower()
        chain_id = tx_context.chain_id or 1

        large_usd = self.config.get("large_threshold_usd", 50000.0)
        medium_usd = self.config.get("medium_threshold_usd", 5000.0)
        exclude_protocols = self.config.get("exclude_known_protocols", True)

        # 获取原生代币价格 - 优先使用 TokenPriceProvider
        token_prices = self.get_token_prices(tx_context)
        native_price = token_prices.get("", 0.0)  # 空字符串 key 表示原生代币

        # 如果 Provider 没有提供原生代币价格，回退到 token_price_instance
        if native_price == 0.0:
            native_price = self.token_price_instance.get_price(chain_id, "") or 0.0

        _price_warned_tokens: set[str] = set()

        # ── 1. 提取转账数据 ──
        transfers = self._extract_transfers_from_context(tx_context)

        # 加入原生代币转账（tx.value）
        if tx_value_wei > 0 and from_addr:
            transfers.insert(0, {
                "from": from_addr,
                "to": (tx_context.to_address or "").lower(),
                "value": tx_value_wei,
                "token": "",  # 原生代币
            })

        # ── 1.5 从 eth_trace 提取内部 ETH 转账（如 FeesClaimed 等合约内部 ETH 流出） ──
        internal_eth = self._extract_internal_eth_transfers(tx_context)
        if internal_eth:
            transfers.extend(internal_eth)
            logger.info(
                f"[FundDrainDetector] 从 eth_trace 提取到 {len(internal_eth)} 笔内部 ETH 转账"
            )

        if not transfers:
            return FundDrainOutput(
                score=0.0, passed=True, severity="UNKNOWN", labels=[],
                detection={"reason": "no transfer data available"},
                logs=["无转账数据，跳过检测"],
            )

        # ── 2. 计算全地址盈亏 ──
        pnl_map = compute_all_pnl(transfers)

        # 计算每个地址的 USD 盈亏
        for addr, pnl in pnl_map.items():
            self._compute_address_pnl_usd(pnl, chain_id, native_price, _price_warned_tokens)

        # ── 3. 识别最大获利者和最大亏损者 ──
        exclude_set = KNOWN_PROTOCOL_ADDRESSES if exclude_protocols else set()

        max_gainer: AddressPnL | None = None
        max_loser: AddressPnL | None = None

        for addr, pnl in pnl_map.items():
            if addr in exclude_set or addr == ZERO_ADDRESS:
                continue
            if pnl.total_usd > 0:
                if max_gainer is None or pnl.total_usd > max_gainer.total_usd:
                    max_gainer = pnl
            elif pnl.total_usd < 0:
                if max_loser is None or pnl.total_usd < max_loser.total_usd:
                    max_loser = pnl

        outflow_signals = self._build_outflow_signals(
            transfers=transfers,
            victim_address=max_loser.address if max_loser else None,
            chain_id=chain_id,
            native_price=native_price,
            price_warned_tokens=_price_warned_tokens,
            known_protocol_addresses=exclude_set,
        )
        multi_asset_loss_tokens = [
            item for item in outflow_signals["loss_tokens"]
            if item["outflow_usd"] > 0
        ]
        multi_asset_threshold = self.config.get("multi_asset_min_tokens", 2)
        receiver_cluster_min_count = self.config.get("receiver_cluster_min_count", 2)
        receiver_cluster_min_share = self.config.get("receiver_cluster_min_share", 0.6)
        multi_asset_outflow = len(multi_asset_loss_tokens) >= multi_asset_threshold
        receiver_cluster = (
            outflow_signals["external_receiver_count"] >= receiver_cluster_min_count
            and outflow_signals["external_outflow_share"] >= receiver_cluster_min_share
        )
        outflow_signals["multi_asset_outflow"] = multi_asset_outflow
        outflow_signals["receiver_cluster"] = receiver_cluster

        # ── 4. 盈亏严重度判断 ──
        gainer_usd = max_gainer.total_usd if max_gainer else 0.0
        loser_usd = abs(max_loser.total_usd) if max_loser else 0.0
        max_abs_usd = max(gainer_usd, loser_usd)

        severity = (
            "large" if max_abs_usd >= large_usd else
            "medium" if max_abs_usd >= medium_usd else
            "small"
        )

        scoring_logs: list[str] = []
        scoring_logs.append(
            f"全地址盈亏: {len(pnl_map)} 个地址参与, "
            f"最大获利={gainer_usd:,.2f} USD, "
            f"最大亏损={loser_usd:,.2f} USD, "
            f"severity={severity}"
        )

        if max_gainer:
            scoring_logs.append(
                f"最大获利者: {max_gainer.address[:10]}... "
                f"净赚 ${gainer_usd:,.2f} USD"
            )
        if max_loser:
            scoring_logs.append(
                f"最大亏损者: {max_loser.address[:10]}... "
                f"净亏 ${loser_usd:,.2f} USD"
            )
        if multi_asset_outflow:
            scoring_logs.append(
                f"多资产外流: 最大亏损地址涉及 {len(multi_asset_loss_tokens)} 种资产外流"
            )
        if receiver_cluster:
            scoring_logs.append(
                f"接收方聚合: 外部接收方 {outflow_signals['external_receiver_count']} 个, "
                f"最大接收方占比 {outflow_signals['external_outflow_share']:.2%}"
            )

        # ── 5. 关联检测 ──
        correlated_addrs = self._get_correlated_addresses(tx_context)
        correlation_found = False
        correlated_events: list[dict] = []

        if correlated_addrs:
            for addr, pnl in pnl_map.items():
                if addr in correlated_addrs and pnl.total_usd < 0:
                    correlation_found = True
                    correlated_events.append({
                        "address": addr,
                        "loss_usd": round(abs(pnl.total_usd), 2),
                        "correlation_source": "extra",
                    })

        if correlation_found:
            scoring_logs.append(f"关联检测: 匹配到 {len(correlated_events)} 个关联地址亏损")

        # ── 6. ROI 计算 ──
        roi_info: dict[str, Any] = {}
        roi_anomaly = False
        if self.config.get("enable_roi_check", True) and max_gainer:
            roi_threshold = self.config.get("roi_threshold", 50.0)
            min_tx_eth = self.config.get("min_tx_value_eth", 0.001)
            tx_value_eth = tx_value_wei / 10**18
            tx_value_usd = tx_value_eth * native_price

            roi = 0.0
            if tx_value_eth >= min_tx_eth and tx_value_usd > 0:
                roi = gainer_usd / tx_value_usd
            elif tx_value_eth < min_tx_eth and gainer_usd > 0:
                roi = 999.0

            roi_anomaly = roi >= roi_threshold
            roi_info = {
                "roi": round(roi, 2),
                "tx_value_eth": round(tx_value_eth, 6),
                "tx_value_usd": round(tx_value_usd, 2),
                "gainer_usd": round(gainer_usd, 2),
                "roi_threshold": roi_threshold,
                "roi_anomaly": roi_anomaly,
            }

        # ── 7. 销毁-释放关联 & Swap-Burn-Claim ──
        burn_drain_found = False
        burn_drain_details: list[dict] = []
        sbc_loop_found = False
        sbc_details: dict[str, Any] = {}

        # 优先从 logs 提取（含 swap 事件），如果 logs 为空则从 transfers 提取
        burn_events, swap_events, all_log_transfers = self._extract_burn_mint_swap_from_logs(tx_context)

        if not burn_events and not all_log_transfers:
            # logs 为空，尝试从 transfers 数据中提取 burn/mint 模式
            burn_events, swap_events, all_log_transfers = self._extract_burn_mint_swap_from_transfers(transfers)

        if self.config.get("enable_burn_drain_check", True) and burn_events:
            for burn in burn_events:
                for t in all_log_transfers:
                    if (t["log_index"] > burn["log_index"]
                            and t["from"] != ZERO_ADDRESS
                            and t["token"] != burn["token"]
                            and t["amount"] > 0):
                        burn_drain_found = True
                        burn_drain_details.append({
                            "burn_token": burn["token"],
                            "burn_amount": burn["amount"],
                            "burn_log_index": burn["log_index"],
                            "drain_token": t["token"],
                            "drain_amount": t["amount"],
                            "drain_log_index": t["log_index"],
                        })

        if self.config.get("enable_swap_burn_claim_check", True) and swap_events and burn_events:
            for swap in swap_events:
                for burn in burn_events:
                    if swap["log_index"] < burn["log_index"]:
                        for t in all_log_transfers:
                            if (t["log_index"] > burn["log_index"]
                                    and t["from"] != ZERO_ADDRESS
                                    and t["amount"] > 0):
                                sbc_loop_found = True
                                sbc_details = {
                                    "swap_log_index": swap["log_index"],
                                    "swap_pool": swap["pool"],
                                    "burn_log_index": burn["log_index"],
                                    "drain_log_index": t["log_index"],
                                }
                                break
                        if sbc_loop_found:
                            break
                if sbc_loop_found:
                    break

        # ── 8. 评分 ──
        issues: list[str] = []
        score = 0.0

        # 基础评分：基于盈亏规模
        if correlation_found and severity == "large":
            score = 95.0
            issues.append("CORRELATED_LOSS_LARGE")
            scoring_logs.append("基础评分=95: 关联地址大额亏损")
        elif correlation_found and severity == "medium":
            score = 80.0
            issues.append("CORRELATED_LOSS_MEDIUM")
            scoring_logs.append("基础评分=80: 关联地址中额亏损")
        elif severity == "large":
            score = 60.0
            issues.append("LARGE_PNL_ANOMALY")
            scoring_logs.append(f"基础评分=60: 大额盈亏异常(max_abs=${max_abs_usd:,.2f})")
        elif severity == "medium":
            score = 40.0
            issues.append("MEDIUM_PNL_ANOMALY")
            scoring_logs.append(f"基础评分=40: 中额盈亏异常(max_abs=${max_abs_usd:,.2f})")
        else:
            score = 20.0
            issues.append("SMALL_PNL")
            scoring_logs.append(f"基础评分=20: 小额盈亏(max_abs=${max_abs_usd:,.2f})")

        # 获利者 ≠ sender 加分（间接受益模式）
        if max_gainer and max_gainer.address != from_addr and gainer_usd >= medium_usd:
            old_score = score
            score = min(100.0, score + 15.0)
            issues.append("INDIRECT_BENEFICIARY")
            scoring_logs.append(
                f"间接受益加分+15: 最大获利者({max_gainer.address[:10]}...)≠sender({from_addr[:10]}...), "
                f"评分 {old_score}→{score}"
            )

        # ROI 增强
        if roi_anomaly:
            roi_val = roi_info.get("roi", 0)
            if roi_val >= 100:
                old_score = score
                score = max(score, 80.0)
                issues.append("EXTREME_ROI")
                scoring_logs.append(f"ROI增强: roi={roi_val:.1f}x >= 100, 评分 {old_score}→{score}")
            elif roi_val >= 50:
                old_score = score
                score = max(score, 70.0)
                issues.append("HIGH_ROI")
                scoring_logs.append(f"ROI增强: roi={roi_val:.1f}x >= 50, 评分 {old_score}→{score}")
            else:
                old_score = score
                score = max(score, 55.0)
                issues.append("MODERATE_ROI")
                scoring_logs.append(f"ROI增强: roi={roi_val:.1f}x >= 阈值, 评分 {old_score}→{score}")
        elif roi_info:
            scoring_logs.append(f"ROI未达阈值: roi={roi_info.get('roi', 0):.1f}x")

        if multi_asset_outflow:
            old_score = score
            score = min(100.0, score + 10.0)
            issues.append("MULTI_ASSET_DRAIN")
            scoring_logs.append(f"多资产外流加分+10, 评分 {old_score}→{score}")

        if receiver_cluster:
            old_score = score
            score = min(100.0, score + 10.0)
            issues.append("RECEIVER_CLUSTER")
            scoring_logs.append(f"接收方聚合加分+10, 评分 {old_score}→{score}")

        # 销毁-释放关联
        if burn_drain_found:
            old_score = score
            score = min(100.0, score + 15.0)
            issues.append("BURN_THEN_DRAIN")
            scoring_logs.append(f"销毁-释放关联加分+15, 评分 {old_score}→{score}")

        # Swap-Burn-Claim 闭环
        if sbc_loop_found:
            old_score = score
            score = min(100.0, score + 20.0)
            issues.append("SWAP_BURN_CLAIM_LOOP")
            scoring_logs.append(f"Swap-Burn-Claim闭环加分+20, 评分 {old_score}→{score}")

        # 组合加分
        if roi_anomaly and sbc_loop_found:
            old_score = score
            score = min(100.0, score + 10.0)
            issues.append("ROI_PLUS_LOOP")
            scoring_logs.append(f"组合加分+10: ROI + 闭环, 评分 {old_score}→{score}")

        if roi_anomaly and burn_drain_found:
            old_score = score
            score = min(100.0, score + 10.0)
            issues.append("ROI_PLUS_BURN_DRAIN")
            scoring_logs.append(f"组合加分+10: ROI + 销毁释放, 评分 {old_score}→{score}")

        # ── 9. 构建输出 ──
        threshold_cfg = self.config.get("threshold", 50.0)
        passed = score >= threshold_cfg
        labels = issues if passed else []

        # 构建地址盈亏摘要（只保留有意义的）
        address_pnl_summary: list[dict] = []
        for addr, pnl in sorted(pnl_map.items(), key=lambda x: x[1].total_usd, reverse=True):
            if addr in exclude_set or addr == ZERO_ADDRESS:
                continue
            if abs(pnl.total_usd) < 1.0 and all(abs(v) == 0 for v in pnl.token_changes.values()):
                continue
            address_pnl_summary.append({
                "address": addr,
                "total_usd": round(pnl.total_usd, 2),
                "token_changes": {
                    tok: str(val) for tok, val in pnl.token_changes.items() if val != 0
                },
            })

        scoring_logs.append(f"最终评分={score:.1f}, 阈值={threshold_cfg}, passed={passed}, severity={score_to_severity(score)}")

        detection: dict[str, Any] = {
            "detected_issues": issues,
            "labels": labels,
            "max_gainer": {
                "address": max_gainer.address,
                "total_usd": round(max_gainer.total_usd, 2),
                "token_changes": {tok: str(val) for tok, val in max_gainer.token_changes.items() if val != 0},
            } if max_gainer else None,
            "max_loser": {
                "address": max_loser.address,
                "total_usd": round(max_loser.total_usd, 2),
                "token_changes": {tok: str(val) for tok, val in max_loser.token_changes.items() if val != 0},
            } if max_loser else None,
            "severity": severity,
            "correlation_found": correlation_found,
            "correlated_events": correlated_events,
            "address_pnl_summary": address_pnl_summary[:20],  # 最多 20 个
            "total_addresses": len(pnl_map),
            "thresholds": {
                "large_usd": large_usd,
                "medium_usd": medium_usd,
            },
            "outflow_signals": outflow_signals,
        }
        if roi_info:
            detection["roi"] = roi_info
        if burn_drain_details:
            detection["burn_then_drain"] = burn_drain_details
        if sbc_details:
            detection["swap_burn_claim_loop"] = sbc_details

        return FundDrainOutput(
            score=score,
            passed=passed,
            severity=score_to_severity(score),
            labels=labels,
            detection=detection,
            logs=scoring_logs,
        )


NodeRegistry.register(FundDrainDetector)
