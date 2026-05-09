"""
策略资金提取检测器 — 检测策略份额赎回后资金流出的攻击模式

检测维度（基于 Infini 攻击分析）:
  1. 策略份额赎回检测 (Feature B - Bulk Strategy Redemption):
     检测 Transfer(to=0x0) 事件，识别策略份额代币的销毁（赎回）。
     正常用户很少在单笔交易中赎回策略的全部存款。

  2. 赎回-资金流出模式 (Feature C - Redeem-Then-Drain):
     检测份额销毁后紧随的大额底层资产 Transfer 到外部地址。
     资金流向不是协议金库 → Redeem-Then-Drain 信号。

  3. 零资本提取检测 (Feature F - Zero Capital Extraction):
     检测 tx.value=0、无闪电贷、但有大额稳定币从策略合约/协议金库流出的模式。
     零投入 + 无闪电贷 + 大额 USDC 提取 → 零资本提取信号。

所有检测仅依赖标准 ERC-20 Transfer 事件，
不依赖任何特定函数签名，天然具备跨协议通用性。
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field

from nodes.base import NodeRegistry, score_to_severity
from nodes.detectors.base import BaseDetector, DetectorConfigMixin, DetectorOutputMixin
from nodes.models import TransactionContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# ERC-20 Transfer(address indexed from, address indexed to, uint256 value)
ERC20_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# Uniswap V2 Swap 事件 topic（存在 Swap 意味着可能有闪电贷）
UNISWAP_V2_SWAP_TOPIC = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d714"
UNISWAP_V3_SWAP_TOPIC = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e7b213eb771"

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

# 稳定币地址列表（用于零资本提取检测中的稳定币识别）
STABLECOIN_ADDRESSES: set[str] = {
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",  # USDC
    "0xdac17f958d2ee523a2206206994597c13d831ec7",  # USDT
    "0x6b175474e89094c44da98b954eedeac495271d0f",  # DAI
    "0x4fabb145d64652a948d72533023f6e7a623c7c53",  # BUSD
    "0x57ab1ec28d129707052df4df418d58a2d46d5f51",  # sUSD
    "0x853d955acef822db058eb8505911ed77f175b99e",  # FRAX
    "0xbc6da0fe9ad5f3b0d58160288917aa56653660e9",  # alUSD
    "0x9566b79afb03a3b2c3e92e6d0e385ada8fd8831f",  # LUSD
    "0x8e870d67f660d95d5be530380d0ec0bd388289e1",  # USDP (Paxos)
    "0x0000000000085d4780b731190000000000000000000000000000000000000565f2b9",  # TUSD (truncated placeholder)
}


def _hex_to_int(val: Any) -> int:
    """十六进制/整数值安全转换"""
    if isinstance(val, int):
        return val
    if isinstance(val, str) and val.startswith("0x"):
        try:
            return int(val, 16)
        except ValueError:
            return 0
    return 0


def _extract_topic0(log: dict) -> str:
    """提取 log 的 topic0（事件签名）"""
    topics = log.get("topics", [])
    if not topics:
        return ""
    t = topics[0]
    return (t if isinstance(t, str) else t.hex() if isinstance(t, bytes) else "").lower()


def _extract_address_from_topic(topic: str) -> str:
    """从 32 字节 topic 中提取最后 20 字节地址"""
    h = topic.lstrip("0x").lower()
    if len(h) < 40:
        return "0x" + "0" * 40 if len(h) == 0 else "0x" + h.zfill(40)
    return "0x" + h[-40:]


def _is_stablecoin(token_address: str) -> bool:
    """判断代币地址是否为已知稳定币"""
    return token_address.lower() in {a.lower() for a in STABLECOIN_ADDRESSES}


def _is_protocol_address(address: str, protocol_addresses: list[str]) -> bool:
    """判断地址是否为已知协议地址"""
    addr = address.lower()
    return any(a.lower() == addr for a in protocol_addresses)


# ---------------------------------------------------------------------------
# 转账事件结构
# ---------------------------------------------------------------------------

class TransferEvent:
    """解析后的 ERC-20 Transfer 事件"""
    __slots__ = ("log_index", "token_address", "from_addr", "to_addr", "amount", "contract_address")

    def __init__(self, log_index: int, token_address: str,
                 from_addr: str, to_addr: str, amount: int, contract_address: str = ""):
        self.log_index = log_index
        self.token_address = token_address.lower()
        self.from_addr = from_addr.lower()
        self.to_addr = to_addr.lower()
        self.amount = amount
        self.contract_address = contract_address.lower()  # 事件发出的合约地址

    @property
    def is_burn(self) -> bool:
        return self.to_addr == ZERO_ADDRESS

    @property
    def is_mint(self) -> bool:
        return self.from_addr == ZERO_ADDRESS


# ---------------------------------------------------------------------------
# 日志解析
# ---------------------------------------------------------------------------

def scan_transfers(logs: list[dict]) -> list[TransferEvent]:
    """
    从 logs 中提取所有 ERC-20 Transfer 事件，按 log_index 升序排列。

    Args:
        logs: 交易的 Event Log 列表

    Returns:
        排序后的 TransferEvent 列表
    """
    transfers: list[TransferEvent] = []

    for log in logs:
        topic0 = _extract_topic0(log)
        if topic0 != ERC20_TRANSFER_TOPIC.lower():
            continue

        log_index = log.get("logIndex", log.get("log_index", 0))
        if isinstance(log_index, str) and log_index.startswith("0x"):
            log_index = int(log_index, 16)

        topics = log.get("topics", [])
        if len(topics) < 3:
            continue

        from_addr = _extract_address_from_topic(topics[1]) if len(topics) > 1 else ""
        to_addr = _extract_address_from_topic(topics[2]) if len(topics) > 2 else ""
        data = log.get("data", "0x")
        amount = _hex_to_int(data) if data else 0
        contract_address = (log.get("address") or "").lower()

        if amount > 0:
            transfers.append(TransferEvent(
                log_index=log_index,
                token_address=contract_address,  # 代币地址即合约地址
                from_addr=from_addr,
                to_addr=to_addr,
                amount=amount,
                contract_address=contract_address,
            ))

    # 按 log_index 排序
    transfers.sort(key=lambda x: x.log_index)
    return transfers


def scan_swap_events(logs: list[dict]) -> list[dict]:
    """
    从 logs 中提取所有 DEX Swap 事件（用于判断是否含有闪电贷）。

    Returns:
        Swap 事件列表，每项含 log_index 和 pool_address
    """
    swaps: list[dict] = []

    for log in logs:
        topic0 = _extract_topic0(log)
        if topic0 not in (UNISWAP_V2_SWAP_TOPIC.lower(), UNISWAP_V3_SWAP_TOPIC.lower()):
            continue

        log_index = log.get("logIndex", log.get("log_index", 0))
        if isinstance(log_index, str) and log_index.startswith("0x"):
            log_index = int(log_index, 16)

        swaps.append({
            "log_index": log_index,
            "pool": (log.get("address") or "").lower(),
            "swap_type": "uniswap_v3" if topic0 == UNISWAP_V3_SWAP_TOPIC.lower() else "uniswap_v2",
        })

    return swaps


# ---------------------------------------------------------------------------
# 检测逻辑
# ---------------------------------------------------------------------------

def detect_bulk_strategy_redemption(
    transfers: list[TransferEvent],
    burn_amount_threshold: int = 10**18,  # 默认 1 个代币，由调用方根据代币 decimals 调整
) -> tuple[float, list[dict]]:
    """
    特征 B: 策略份额一次性全部赎回检测 (Bulk Strategy Redemption)

    检测 Transfer(to=0x0) 事件中，大额份额销毁。
    正常用户很少在单笔交易中销毁大量策略份额代币。

    Args:
        transfers: 解析后的 Transfer 事件列表（按 log_index 升序）
        burn_amount_threshold: 销毁量阈值（按 raw amount），超过视为大额销毁

    Returns:
        (score, redeemed_details)
            score: 0.0~40.0
            redeemed_details: 每次大额份额销毁的详细信息
    """
    # 找出所有销毁事件（to=0x0）中金额大于阈值的
    large_burns = [
        t for t in transfers
        if t.is_burn and t.amount >= burn_amount_threshold
    ]

    if not large_burns:
        return 0.0, []

    # 对每个大额销毁，查找是否有对应的底层资产流出
    details: list[dict] = []
    for burn in large_burns:
        # 查找销毁后同一合约发出的 Transfer（from=burn sender, to != ZERO_ADDRESS, token != burn token）
        # 这是份额销毁后对应的底层资产赎回/提取
        subsequent_drains: list[dict] = []
        for t in transfers:
            if (t.log_index > burn.log_index
                    and t.from_addr == burn.from_addr   # 资金从同一合约流出
                    and t.token_address != burn.token_address  # 不同代币（底层资产）
                    and t.to_addr != ZERO_ADDRESS
                    and t.amount > 0):
                subsequent_drains.append({
                    "token": t.token_address,
                    "amount": t.amount,
                    "to": t.to_addr,
                    "log_index": t.log_index,
                })

        details.append({
            "burn_token": burn.token_address,
            "burn_amount": burn.amount,
            "burn_log_index": burn.log_index,
            "burn_contract": burn.contract_address,
            "subsequent_drains": subsequent_drains[:5],  # 最多 5 个后续流出
            "drain_count": len(subsequent_drains),
        })

    # 评分: 每个大额销毁 +15，上限 40
    score = min(40.0, 15.0 * len(large_burns))

    return score, details


def detect_redeem_then_drain(
    transfers: list[TransferEvent],
    drain_usd_threshold: float = 10000.0,
) -> tuple[float, list[dict]]:
    """
    特征 C: 赎回-资金流出模式检测 (Redeem-Then-Drain)

    检测同一个 from_addr（策略合约）的份额销毁事件（Transfer to 0x0）后
    紧随大额底层资产 Transfer 到外部地址的模式。

    不按合约地址 grouping — 因份额代币和底层资产通常由不同 Token 合约发出，
    但它们的 from_addr（策略合约）是相同的。

    核心识别逻辑（不依赖函数签名）:
    1. 找到 Transfer(to=0x0, from=StrategyContract) — 份额销毁
    2. 找到同一 from_addr 的下一笔 Transfer(to=External, token!=销毁代币) — 资金流出
    3. 资金流出目标 != 策略合约自身 → Redeem-Then-Drain 信号

    Args:
        transfers: 解析后的 Transfer 事件列表
        drain_usd_threshold: 资金流出 USD 阈值（纯事件级别暂不折算，用 raw amount 近似）

    Returns:
        (score, pattern_details)
    """
    if not transfers:
        return 0.0, []

    # 按 from_addr（策略/流出者）分组 — 份额代币和底层资产可能由不同 Token 合约发出
    from_groups: dict[str, list[TransferEvent]] = {}
    for t in transfers:
        from_groups.setdefault(t.from_addr, []).append(t)

    patterns: list[dict] = []

    for from_addr, ctransfers in from_groups.items():
        # 按 log_index 排序
        ctransfers.sort(key=lambda x: x.log_index)
        # 查找该 from_addr 发出的所有销毁事件
        burns = [t for t in ctransfers if t.is_burn]

        for burn in burns:
            # 查找销毁后同一 from_addr 发出的 Transfer(to!=0x0 且 != 本合约)
            for t in ctransfers:
                if (t.log_index > burn.log_index
                        and t.token_address != burn.token_address  # 不同代币（底层资产 vs 份额）
                        and t.to_addr != ZERO_ADDRESS
                        and t.to_addr != from_addr  # 流出到外部地址（非自身）
                        and t.amount > 0):
                    patterns.append({
                        "strategy_contract": from_addr,
                        "share_token": burn.token_address,
                        "burn_amount": burn.amount,
                        "burn_log_index": burn.log_index,
                        "drain_token": t.token_address,
                        "drain_amount": t.amount,
                        "drain_to": t.to_addr,
                        "drain_log_index": t.log_index,
                    })
                    break  # 每个销毁只匹配第一个后续流出（最紧密的时序关联）

    if not patterns:
        return 0.0, []

    # 评分: 每个模式 +20，上限 50
    score = min(50.0, 20.0 * len(patterns))

    return score, patterns


def detect_zero_capital_extraction(
    tx_value_wei: int,
    transfers: list[TransferEvent],
    swaps: list[dict],
    chain_id: int,
    token_price_cache: Any,
    min_extraction_usd: float = 50000.0,
    token_prices: dict[str, float] | None = None,
) -> tuple[float, dict[str, Any]]:
    """
    特征 F: 零资本提取检测 (Zero Capital Extraction)

    检测 tx.value == 0、无闪电贷（无 DEX Swap）、
    但有大额稳定币从协议合约流出的模式。

    关键检测信号:
    - tx.value == 0（零投入）
    - 无 DEX Swap 事件（间接说明无闪电贷）
    - 检测到从策略合约/非用户地址流出的稳定币大额 Transfer
    - 资金接收方不是已知协议地址

    Args:
        tx_value_wei: 交易的 ETH 输入 (wei)
        transfers: 解析后的 Transfer 事件列表
        swaps: 检测到的 Swap 事件列表
        chain_id: 链 ID
        token_price_cache: TokenPriceCache 全局实例
        min_extraction_usd: 最小提取价值阈值 (USD)
        token_prices: 可选的 Provider 提供的代币价格字典

    Returns:
        (score, details)
    """
    # 零投入条件
    has_zero_input = tx_value_wei == 0
    has_flash_loan = len(swaps) > 0  # 有 Swap 可能含有闪电贷

    if not has_zero_input or has_flash_loan:
        return 0.0, {
            "detected": False,
            "reason": "not_zero_cost" if not has_zero_input else "has_flash_loan_proxy",
            "has_zero_input": has_zero_input,
            "has_swap": has_flash_loan,
        }

    # 查找大额稳定币流出（from 不是 sender 本人、to 不是零地址的 Transfer）
    # 这些流出的源通常是策略合约或协议合约
    sender_addresses: set[str] = set()
    large_drains: list[dict] = []

    for t in transfers:
        if t.is_burn or t.is_mint:
            continue
        if t.to_addr == ZERO_ADDRESS:
            continue
        # 排除 sender 本人之间的转账
        from_addr_lower = t.from_addr

        # 检查代币是否为稳定币
        if not _is_stablecoin(t.token_address):
            continue

        # 估算 USD 价值
        value_usd = 0.0

        # 优先使用 Provider 提供的价格
        if token_prices and t.token_address.lower() in token_prices:
            price = token_prices[t.token_address.lower()]
            meta = token_price_cache.get(chain_id, t.token_address) if token_price_cache else None
            decimals = meta.decimals if meta and meta.decimals else 18
            if price and price > 0:
                value_usd = (t.amount / 10**decimals) * price
            else:
                # 稳定币固定 1 USD
                value_usd = t.amount / 10**decimals
        elif token_price_cache:
            # 回退到 token_price_cache
            price = token_price_cache.get_price(chain_id, t.token_address)
            meta = token_price_cache.get(chain_id, t.token_address)
            decimals = meta.decimals if meta and meta.decimals else 18
            if price and price > 0:
                value_usd = (t.amount / 10**decimals) * price
            else:
                # 稳定币固定 1 USD
                value_usd = t.amount / 10**decimals

        if value_usd >= min_extraction_usd:
            large_drains.append({
                "from": t.from_addr,
                "to": t.to_addr,
                "token": t.token_address,
                "amount": t.amount,
                "value_usd": round(value_usd, 2),
                "log_index": t.log_index,
            })

    if not large_drains:
        return 0.0, {
            "detected": False,
            "reason": "no_large_drain",
            "has_zero_input": has_zero_input,
            "has_swap": has_flash_loan,
        }

    # 评分: 基于最大一笔流出的 USD 价值
    max_value_usd = max(d["value_usd"] for d in large_drains)

    score = 0.0
    if max_value_usd >= 1_000_000:
        score = 50.0  # 百万级提取
    elif max_value_usd >= 500_000:
        score = 40.0
    elif max_value_usd >= min_extraction_usd:
        score = 30.0

    return score, {
        "detected": True,
        "has_zero_input": has_zero_input,
        "has_swap": has_flash_loan,
        "extraction_count": len(large_drains),
        "max_extraction_usd": round(max_value_usd, 2),
        "total_extraction_usd": round(sum(d["value_usd"] for d in large_drains), 2),
        "large_drains": large_drains[:10],
        "min_threshold_usd": min_extraction_usd,
    }


# ---------------------------------------------------------------------------
# StrategyDrainDetector
# ---------------------------------------------------------------------------

class StrategyDrainOutput(DetectorOutputMixin):
    """策略资金提取检测器输出"""
    pass


class StrategyDrainDetector(BaseDetector):
    """
    策略资金提取检测器 — 检测策略份额赎回后资金流出的攻击模式。

    检测维度（基于 Infini 攻击分析）:
      - 策略份额赎回检测 (Bulk Strategy Redemption):
        检测 Transfer(to=0x0) 销毁事件中，大额份额代币的销毁。
        正常用户很少在单笔交易中赎回策略的全部存款。

      - 赎回-资金流出模式 (Redeem-Then-Drain):
        检测份额销毁后紧随的大额底层资产 Transfer 到外部地址。
        资金流向不是协议金库 → Redeem-Then-Drain 强信号。

      - 零资本提取检测 (Zero Capital Extraction):
        检测 tx.value=0、无闪电贷、但有大额稳定币从策略合约/协议金库流出的模式。

    所有检测仅依赖标准 ERC-20 Transfer 事件，
    不依赖任何特定函数签名，天然具备跨协议通用性。

    数据源:
      - tx_context.logs: 原始 ERC-20 事件日志（必需）
      - tx_context.extra["protocol_addresses"]: 可选的已知协议金库地址列表（降低误报）
    """

    name: str = "strategy_drain_detector"
    label: str = "策略资金提取检测"
    description: str = (
        "[数据需求: Logs] "
        "检测策略份额赎回后的资金流出攻击模式："
        "大额份额代币销毁(Bulk Strategy Redemption)、"
        "份额销毁后底层资产立即流出到外部地址(Redeem-Then-Drain)、"
        "零投入且无闪电贷的大额稳定币提取(Zero Capital Extraction)。"
        "基于标准 ERC-20 Transfer 事件，不依赖函数签名，"
        "天然具备跨协议通用性，适用于管理员私钥泄露类攻击检测。"
    )
    icon: str = "\U0001f3db\ufe0f"
    color: str = "#f59e0b"

    # ── Pydantic 配置模型 ──
    class ConfigModel(DetectorConfigMixin):
        burn_amount_threshold: float = Field(
            default=1.0, ge=0,
            description="大额份额销毁阈值（原始代币数量），超过此值视为大额销毁",
        )
        min_extraction_usd: float = Field(
            default=50000.0, ge=0,
            description="最小零资本提取 USD 阈值",
        )
        enable_bulk_redemption_check: bool = Field(
            default=True,
            description="是否启用策略份额赎回检测",
        )
        enable_redeem_drain_check: bool = Field(
            default=True,
            description="是否启用赎回-资金流出模式检测",
        )
        enable_zero_capital_check: bool = Field(
            default=True,
            description="是否启用零资本提取检测",
        )
        protocol_addresses_field: str = Field(
            default="protocol_addresses",
            description="从 extra 中读取已知协议金库地址列表的字段名",
        )

    # ── Pydantic 输出模型 ──
    OutputModel: type = StrategyDrainOutput

    async def process(self, tx_context: TransactionContext) -> StrategyDrainOutput:
        chain_id = tx_context.chain_id or 1
        tx_value_wei = tx_context.value or 0
        extra_value = tx_context.get_extra("value_wei")
        if extra_value:
            tx_value_wei = _hex_to_int(extra_value)

        logs: list[dict] = tx_context.logs or []

        if not logs:
            return StrategyDrainOutput(
                score=0.0, passed=True, severity="UNKNOWN", labels=[],
                detection={"reason": "no logs available"},
                logs=["无logs数据，跳过策略资金提取分析"],
            )

        # ── 1. 解析日志 ──
        transfers = scan_transfers(logs)
        swaps = scan_swap_events(logs)

        if not transfers:
            return StrategyDrainOutput(
                score=0.0, passed=True, severity="UNKNOWN", labels=[],
                detection={"reason": "no transfer events found"},
                logs=["未检测到 ERC-20 Transfer 事件，跳过分析"],
            )

        # ── 2. 获取价格信息（用于 USD 估值） ──
        # 优先使用 TokenPriceProvider 提供的原生代币价格
        token_prices = self.get_token_prices(tx_context)
        native_price = token_prices.get("", 0.0)  # 空字符串 key 表示原生代币

        # 如果 Provider 没有提供原生代币价格，回退到 token_price_instance
        if native_price == 0.0:
            native_price = self.token_price_instance.get_price(chain_id, "") or 0.0

        # ── 3. 读取可选的金库地址列表（降低误报） ──
        protocol_field = self.config.get("protocol_addresses_field", "protocol_addresses")
        known_protocol_addresses: list[str] = tx_context.get_extra(protocol_field, [])

        # ── 4. 执行各项检测 ──
        signals: list[str] = []
        total_score = 0.0
        detection_data: dict[str, Any] = {}
        scoring_logs: list[str] = []

        # Feature B: 策略份额赎回检测
        bulk_score = 0.0
        bulk_details: list[dict] = []
        if self.config.get("enable_bulk_redemption_check", True):
            burn_threshold = int(self.config.get("burn_amount_threshold", 1.0))
            bulk_score, bulk_details = detect_bulk_strategy_redemption(
                transfers=transfers,
                burn_amount_threshold=burn_threshold,
            )
            if bulk_score > 0:
                signals.append("BULK_STRATEGY_REDEMPTION")
                detection_data["bulk_redemption"] = bulk_details
                scoring_logs.append(f"策略份额赎回检测: 评分={bulk_score:.1f}, 检测到{len(bulk_details)}个大额销毁事件")

        # Feature C: 赎回-资金流出模式
        rtd_score = 0.0
        rtd_details: list[dict] = []
        if self.config.get("enable_redeem_drain_check", True):
            rtd_score, rtd_details = detect_redeem_then_drain(transfers=transfers)
            if rtd_score > 0:
                signals.append("REDEEM_THEN_DRAIN")
                detection_data["redeem_then_drain"] = rtd_details
                scoring_logs.append(f"赎回-资金流出模式: 评分={rtd_score:.1f}, 检测到{len(rtd_details)}个模式")

        # Feature F: 零资本提取检测
        zce_score = 0.0
        zce_details: dict[str, Any] = {"detected": False}
        if self.config.get("enable_zero_capital_check", True):
            min_extraction = self.config.get("min_extraction_usd", 50000.0)
            cache = self.token_price_instance
            zce_score, zce_details = detect_zero_capital_extraction(
                tx_value_wei=tx_value_wei,
                transfers=transfers,
                swaps=swaps,
                chain_id=chain_id,
                token_price_cache=cache,
                min_extraction_usd=min_extraction,
                token_prices=token_prices,  # 传递 Provider 提供的价格
            )
            if zce_details.get("detected"):
                signals.append("ZERO_CAPITAL_EXTRACTION")
                detection_data["zero_capital_extraction"] = zce_details
                scoring_logs.append(
                    f"零资本提取检测: 评分={zce_score:.1f}, "
                    f"提取次数={zce_details.get('extraction_count', 0)}, "
                    f"最大提取=${zce_details.get('max_extraction_usd', 0):,.2f}"
                )

        # ── 5. 组合评分 ──
        total_score = bulk_score + rtd_score + zce_score
        scoring_logs.insert(0, f"基础分合计={total_score:.1f}: bulk_redemption={bulk_score:.1f} + redeem_then_drain={rtd_score:.1f} + zero_capital={zce_score:.1f}")

        # 组合加分
        combo_bonus = 0.0
        has_bulk = bulk_score > 0
        has_rtd = rtd_score > 0
        has_zce = zce_details.get("detected", False)

        # B + C: 批量策略赎回 + 赎回后资金流出 → 强赎回套现信号
        if has_bulk and has_rtd:
            combo_bonus += 15.0
            signals.append("BULK_REDEEM_THEN_DRAIN")
            scoring_logs.append("组合加分+15: 批量策略赎回 + 赎回后资金流出(赎回套现攻击)")

        # C + F: 赎回后资金流出 + 零资本 → 确认攻击（零资本+策略提取）
        if has_rtd and has_zce:
            combo_bonus += 20.0
            signals.append("REDEEM_DRAIN_ZERO_COST")
            scoring_logs.append("组合加分+20: 赎回后资金流出 + 零资本提取(确认攻击)")

        # B + C + F: 全部命中 → 几乎确定攻击
        if has_bulk and has_rtd and has_zce:
            combo_bonus += 15.0
            signals.append("FULL_STRATEGY_DRAIN_PATTERN")
            scoring_logs.append("组合加分+15: 全部模式命中(几乎确定策略资金提取攻击)")

        if combo_bonus > 0:
            scoring_logs.append(f"组合加分合计=+{combo_bonus:.1f}")
        else:
            scoring_logs.append("无组合加分")

        total_score += combo_bonus
        total_score = max(0.0, min(100.0, total_score))

        # ── 6. 生成结果 ──
        threshold = self.config.get("threshold", 50.0)
        passed = total_score >= threshold
        labels = signals if passed else []

        # 补充详细日志
        if has_bulk:
            scoring_logs.append(f"策略赎回: {len(bulk_details)}个份额销毁事件")
        if has_rtd:
            scoring_logs.append(f"赎回流出: {len(rtd_details)}个赎回-流出模式")
        if has_zce:
            zce_info = zce_details
            scoring_logs.append(f"零资本提取: total=${zce_info.get('total_extraction_usd', 0):,.2f}, max=${zce_info.get('max_extraction_usd', 0):,.2f}")

        scoring_logs.append(f"最终评分={total_score:.1f}, 阈值={threshold}, passed={passed}, severity={score_to_severity(total_score)}")

        detection_data["total_score"] = round(total_score, 2)
        detection_data["combo_bonus"] = round(combo_bonus, 2)
        detection_data["signal_scores"] = {
            "bulk_redemption": round(bulk_score, 2),
            "redeem_then_drain": round(rtd_score, 2),
            "zero_capital_extraction": round(zce_score, 2),
        }
        detection_data["signals"] = signals
        detection_data["transfer_count"] = len(transfers)
        detection_data["swap_count"] = len(swaps)
        detection_data["burn_count"] = len([t for t in transfers if t.is_burn])

        return StrategyDrainOutput(
            score=total_score,
            passed=passed,
            severity=score_to_severity(total_score),
            labels=labels,
            detection=detection_data,
            logs=scoring_logs,
        )


NodeRegistry.register(StrategyDrainDetector)
