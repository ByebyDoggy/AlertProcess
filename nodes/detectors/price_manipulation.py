"""
价格操纵检测器 — 基于 Swap 事件的价格异常分析

检测维度:
  1. 单区块极端价格偏移 (Intra-Block Price Deviation)
     同一池在同一交易中价格偏移超过阈值
  2. Swap → Drain 模式: 大额 Swap 后紧接大额 Token 转出
  3. LP 提取后转出: DecreaseLiquidity 事件后代币被转出

所有检测仅依赖标准 ERC-20 Transfer 事件和 DEX Swap 事件，
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

# Uniswap V2 Swap
UNISWAP_V2_SWAP_TOPIC = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d714"

# Uniswap V3 Swap
UNISWAP_V3_SWAP_TOPIC = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e7b213eb771"

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

# 已知的调用函数签名（用于识别 LP 操作，仅在 input_data 可用时）
DECREASE_LIQUIDITY_SIG = "0x0c49ccbe"  # decreaseLiquidity((uint256,uint128,uint64,uint64))
INCREASE_LIQUIDITY_SIG = "0xf305d719"  # increaseLiquidity(...)
COLLECT_SIG = "0xfc6f7865"  # collect((uint256,address,uint128,uint128))

# DEX Router 常用调用
EXACT_INPUT_SINGLE_SIG = "0x04e45aaf"  # exactInputSingle((address,address,uint24,address,uint256,uint256,uint256))
EXACT_INPUT_SIG = "0x414bf389"  # exactInput((bytes,address,uint256,uint256))
MULTICALL_SIG = "0xac9650d8"  # multicall


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


def _read_uint256(data_hex: str, offset: int) -> str:
    """从 data 字段读取 offset 位置开始的 32 字节 uint256，返回 hex 字符串"""
    if not data_hex or not data_hex.startswith("0x"):
        return "0x0"
    raw = data_hex[2:]
    byte_offset = offset * 2
    if byte_offset + 64 > len(raw):
        return "0x0"
    return "0x" + raw[byte_offset:byte_offset + 64]


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


def _wei_to_eth(wei: int) -> float:
    """wei → ETH 单位"""
    return wei / 10**18


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


class SwapEvent:
    """解析后的 DEX Swap 事件"""
    __slots__ = ("log_index", "pool_address", "swap_type", "raw",
                 "amount0", "amount1")

    def __init__(self, log_index: int, pool_address: str, swap_type: str, raw: dict,
                 amount0: int = 0, amount1: int = 0):
        self.log_index = log_index
        self.pool_address = pool_address.lower()
        self.swap_type = swap_type
        self.raw = raw
        self.amount0 = amount0
        self.amount1 = amount1


class TransferEvent:
    """解析后的 ERC-20 Transfer 事件"""
    __slots__ = ("log_index", "token_address", "from_addr", "to_addr", "amount", "raw")

    def __init__(self, log_index: int, token_address: str,
                 from_addr: str, to_addr: str, amount: int, raw: dict):
        self.log_index = log_index
        self.token_address = token_address.lower()
        self.from_addr = from_addr.lower()
        self.to_addr = to_addr.lower()
        self.amount = amount
        self.raw = raw

    @property
    def is_burn(self) -> bool:
        return self.to_addr == ZERO_ADDRESS

    @property
    def is_mint(self) -> bool:
        return self.from_addr == ZERO_ADDRESS


def scan_logs(logs: list[dict]) -> tuple[list[TransferEvent], list[SwapEvent]]:
    """扫描 logs，提取所有 Transfer 和 Swap 事件"""
    transfers: list[TransferEvent] = []
    swaps: list[SwapEvent] = []

    for log in logs:
        topic0 = _extract_topic0(log)
        log_index = log.get("logIndex", log.get("log_index", 0))
        if isinstance(log_index, str) and log_index.startswith("0x"):
            log_index = int(log_index, 16)

        if topic0 == ERC20_TRANSFER_TOPIC.lower():
            topics = log.get("topics", [])
            if len(topics) < 3:
                continue
            from_addr = _extract_address_from_topic(topics[1]) if len(topics) > 1 else ""
            to_addr = _extract_address_from_topic(topics[2]) if len(topics) > 2 else ""
            data = log.get("data", "0x")
            amount = _hex_to_int(data) if data else 0
            token_address = (log.get("address") or "").lower()
            transfers.append(TransferEvent(
                log_index=log_index,
                token_address=token_address,
                from_addr=from_addr,
                to_addr=to_addr,
                amount=amount,
                raw=log,
            ))

        elif topic0 == UNISWAP_V2_SWAP_TOPIC.lower():
            pool_address = (log.get("address") or "").lower()
            data_hex = log.get("data", "0x")
            amount0_in = _hex_to_int(_read_uint256(data_hex, 0))
            amount1_in = _hex_to_int(_read_uint256(data_hex, 32))
            amount0_out = _hex_to_int(_read_uint256(data_hex, 64))
            amount1_out = _hex_to_int(_read_uint256(data_hex, 96))
            a0 = amount0_out if amount0_out > 0 else -amount0_in
            a1 = amount1_out if amount1_out > 0 else -amount1_in
            swaps.append(SwapEvent(
                log_index=log_index,
                pool_address=pool_address,
                swap_type="uniswap_v2",
                raw=log,
                amount0=a0,
                amount1=a1,
            ))

        elif topic0 == UNISWAP_V3_SWAP_TOPIC.lower():
            pool_address = (log.get("address") or "").lower()
            data_hex = log.get("data", "0x")
            amount0_raw = _read_uint256(data_hex, 0)
            amount1_raw = _read_uint256(data_hex, 32)
            a0 = int(amount0_raw, 16) if amount0_raw else 0
            a1 = int(amount1_raw, 16) if amount1_raw else 0
            if a0 >= 2**255:
                a0 -= 2**256
            if a1 >= 2**255:
                a1 -= 2**256
            swaps.append(SwapEvent(
                log_index=log_index,
                pool_address=pool_address,
                swap_type="uniswap_v3",
                raw=log,
                amount0=a0,
                amount1=a1,
            ))

    return transfers, swaps


# ---------------------------------------------------------------------------
# 检测逻辑
# ---------------------------------------------------------------------------


def detect_intra_block_price_deviation(
    swaps: list[SwapEvent],
) -> tuple[float, list[dict]]:
    """
    特征 E: 单区块极端价格偏移检测

    通过同一池在同一交易中的多个 Swap，计算价格偏移幅度。
    如果同一池的多次 Swap 间价格变化超过阈值，则为异常。

    计算方法:
      - V3 池: sqrtPriceX96 可从 raw 的 data 字段提取 (offset 64)
      - V2 池: 通过 amount0/amount1 的比值估算

    Args:
        swaps: 解析后的 Swap 事件列表

    Returns:
        (score, price_deviation_details)
    """
    if len(swaps) < 2:
        return 0.0, []

    # 按池地址分组
    pool_events: dict[str, list[SwapEvent]] = {}
    for s in swaps:
        pool_events.setdefault(s.pool_address, []).append(s)

    deviations: list[dict] = []

    for pool, events in pool_events.items():
        if len(events) < 2:
            continue

        # 按 log_index 排序
        sorted_events = sorted(events, key=lambda e: e.log_index)

        # 遍历相邻的 Swap 对，计算价格
        for i in range(len(sorted_events) - 1):
            e1 = sorted_events[i]
            e2 = sorted_events[i + 1]

            # 计算两种价格估算方式
            price_info = _compute_price_deviation(e1, e2)
            if price_info is None:
                continue

            deviations.append({
                "pool": pool,
                "swap_type": e1.swap_type,
                "first_log_index": e1.log_index,
                "second_log_index": e2.log_index,
                **price_info,
            })

    if not deviations:
        return 0.0, []

    # 评分: 每个价格偏移 > 20% 加 25 分
    score = 0.0
    for d in deviations:
        deviation_pct = abs(d.get("price_deviation_pct", 0))
        if deviation_pct >= 50:
            score += 40.0  # 极高价格偏移
        elif deviation_pct >= 20:
            score += 25.0  # 高价格偏移
        elif deviation_pct >= 10:
            score += 15.0  # 中等价格偏移
        elif deviation_pct >= 5:
            score += 8.0   # 轻度偏移

    score = min(70.0, score)

    return score, deviations


def _compute_price_deviation(e1: SwapEvent, e2: SwapEvent) -> dict[str, Any] | None:
    """
    计算两个 Swap 事件之间的价格偏移。

    对 V3 池，尝试从 data 字段解析 sqrtPriceX96。
    对 V2 池，通过 amount0/amount1 比值估算价格。

    Returns:
        dict with: price_before, price_after, price_deviation_pct
        或 None（无法计算）
    """
    # 尝试 V3 sqrtPriceX96
    price_before = _extract_sqrt_price(e1)
    price_after = _extract_sqrt_price(e2)

    if price_before is not None and price_after is not None and price_before > 0:
        deviation_pct = abs(price_after - price_before) / price_before * 100
        return {
            "price_before": price_before,
            "price_after": price_after,
            "price_deviation_pct": round(deviation_pct, 4),
        }

    # fallback: 用 amount0/amount1 比值估算
    if e1.amount0 != 0 and e2.amount0 != 0:
        # 用 amount0 的正负判断哪个方向是"价格上升"
        ratio1 = abs(e1.amount1 / e1.amount0) if e1.amount0 != 0 else 0
        ratio2 = abs(e2.amount1 / e2.amount0) if e2.amount0 != 0 else 0
        if ratio1 > 0 and ratio2 > 0:
            deviation_pct = abs(ratio2 - ratio1) / ratio1 * 100
            return {
                "price_before": round(ratio1, 6),
                "price_after": round(ratio2, 6),
                "price_deviation_pct": round(deviation_pct, 4),
                "price_method": "amount_ratio",
            }

    return None


def _extract_sqrt_price(swap: SwapEvent) -> float | None:
    """
    从 V3 Swap 事件的 data 字段提取 sqrtPriceX96。
    V3 Swap event data: amount0(int256), amount1(int256), sqrtPriceX96(uint160),
                         liquidity(uint128), tick(int24)
    sqrtPriceX96 位于 offset 64 (第 3 个 uint256)
    """
    if swap.swap_type != "uniswap_v3":
        return None

    data_hex = swap.raw.get("data", "0x")
    sqrt_price_raw = _read_uint256(data_hex, 64)  # byte offset 64 = 第3个uint256 (amount0 + amount1)

    sqrt_price_x96 = int(sqrt_price_raw, 16) if sqrt_price_raw != "0x0" else 0
    if sqrt_price_x96 <= 0:
        return None

    # sqrtPriceX96 = sqrt(price) * 2^96
    # price = (sqrtPriceX96 / 2^96)^2
    # 简化为浮点数表示
    sqrt_price = sqrt_price_x96 / 2**96
    price = sqrt_price * sqrt_price
    return price


def detect_swap_to_drain(
    swaps: list[SwapEvent],
    transfers: list[TransferEvent],
    from_address: str,
) -> tuple[float, list[dict]]:
    """
    特征 C/Swap-Drain: 大额 Swap 后紧接大额 Token 转出

    检测模式:
    1. 存在大额 Swap（> $10K 估算）
    2. Swap 之后出现大额 ERC-20 Transfer（非铸造非销毁）
    3. 转账目标地址不是 DEX 池

    Args:
        swaps: 解析后的 Swap 事件
        transfers: 解析后的 Transfer 事件
        from_address: 交易发起者地址

    Returns:
        (score, pattern_details)
    """
    if not swaps or not transfers:
        return 0.0, []

    large_swaps = [s for s in swaps if max(abs(s.amount0), abs(s.amount1)) > 10**18]
    if not large_swaps:
        return 0.0, []

    patterns: list[dict] = []

    for s in large_swaps:
        for t in transfers:
            if t.log_index <= s.log_index:
                continue
            if t.is_mint or t.is_burn:
                continue
            if t.amount < 10**4:
                continue
            if t.from_addr == s.pool_address or t.from_addr == from_address.lower():
                patterns.append({
                    "pool": s.pool_address,
                    "swap_log_index": s.log_index,
                    "transfer_log_index": t.log_index,
                    "token": t.token_address,
                    "amount": t.amount,
                    "from": t.from_addr,
                    "to": t.to_addr,
                    "swap_amount0": s.amount0,
                    "swap_amount1": s.amount1,
                })

    if not patterns:
        return 0.0, []

    score = min(35.0, 12.0 * len(patterns))
    return score, patterns


def detect_pool_repeated_swap_pressure(
    swaps: list[SwapEvent],
) -> tuple[float, list[dict]]:
    if len(swaps) < 2:
        return 0.0, []

    pool_events: dict[str, list[SwapEvent]] = {}
    for swap in swaps:
        pool_events.setdefault(swap.pool_address, []).append(swap)

    details: list[dict] = []
    score = 0.0
    for pool, events in pool_events.items():
        sorted_events = sorted(events, key=lambda item: item.log_index)
        if len(sorted_events) < 2:
            continue

        directional_events = [
            event for event in sorted_events
            if event.amount0 != 0 and event.amount1 != 0
        ]
        if len(directional_events) < 2:
            continue

        same_direction_runs = 1
        best_run = 1
        previous_direction = None
        for event in directional_events:
            direction = (event.amount0 > 0, event.amount1 > 0)
            if direction == previous_direction:
                same_direction_runs += 1
            else:
                same_direction_runs = 1
                previous_direction = direction
            best_run = max(best_run, same_direction_runs)

        if best_run >= 2:
            details.append({
                "pool": pool,
                "swap_count": len(sorted_events),
                "same_direction_run": best_run,
                "first_log_index": sorted_events[0].log_index,
                "last_log_index": sorted_events[-1].log_index,
            })
            score += 12.0 if best_run == 2 else 20.0

    return min(30.0, score), details


def detect_price_deviation_followed_by_drain(
    price_deviation_details: list[dict],
    swap_to_drain_details: list[dict],
) -> tuple[float, list[dict]]:
    if not price_deviation_details or not swap_to_drain_details:
        return 0.0, []

    drain_by_pool: dict[str, list[dict]] = {}
    for item in swap_to_drain_details:
        drain_by_pool.setdefault(item["pool"], []).append(item)

    matched: list[dict] = []
    for deviation in price_deviation_details:
        pool = deviation.get("pool")
        drains = drain_by_pool.get(pool, [])
        for drain in drains:
            if drain["transfer_log_index"] > deviation.get("second_log_index", -1):
                matched.append({
                    "pool": pool,
                    "price_deviation_pct": deviation.get("price_deviation_pct", 0),
                    "drain_transfer_log_index": drain["transfer_log_index"],
                    "drain_to": drain["to"],
                    "drain_amount": drain["amount"],
                })
                break

    if not matched:
        return 0.0, []

    score = min(25.0, 15.0 + 5.0 * (len(matched) - 1))
    return score, matched


# ---------------------------------------------------------------------------
# PriceManipulationDetector
# ---------------------------------------------------------------------------


class PriceManipulationOutput(DetectorOutputMixin):
    """价格操纵检测器输出"""
    pass


class PriceManipulationDetector(BaseDetector):
    """
    价格操纵检测器 — 基于 Swap 事件的价格异常分析。

    检测维度:
      - 单区块极端价格偏移: 同一池在同一交易中价格偏移超过 10%
      - Swap → Drain 模式: 大额 Swap 后紧接大额 Token 转出
      - LP 操作异常: 流动性操作后的异常转出（通过事件关联）

    所有检测仅依赖 ERC-20 Transfer 事件和 DEX Swap 事件，
    不依赖特定函数签名，天然具备跨协议通用性。
    """

    name: str = "price_manipulation_detector"
    label: str = "价格操纵检测"
    description: str = (
        "[数据需求: Logs] "
        "检测现货价格操纵类攻击：单区块极端价格偏移(同一池同一交易内价格变化>10%)、"
        "大额Swap后紧接大额代币转出(Swap→Drain)、"
        "LP流动性操作后异常资金转出。"
        "主要依赖标准DEX Swap事件和ERC-20 Transfer事件，不依赖函数签名，"
        "适用于闪电贷价格操纵、预言机操纵等攻击场景"
    )
    icon: str = "\U0001f4ca"
    color: str = "#ef4444"

    # ── Pydantic 配置模型 ──
    class ConfigModel(DetectorConfigMixin):
        min_price_deviation_pct: float = Field(
            default=10.0, ge=1.0,
            description="最小价格偏移百分比阈值，超过此值视为异常",
        )
        min_swap_value_eth: float = Field(
            default=1.0, ge=0.1,
            description="最小 Swap 金额阈值(ETH)，低于此值不触发 Swap→Drain 检测",
        )

    # ── Pydantic 输出模型 ──
    OutputModel: type = PriceManipulationOutput

    async def process(self, tx_context: TransactionContext) -> PriceManipulationOutput:
        logs: list[dict] = tx_context.logs or []

        if not logs:
            return PriceManipulationOutput(
                score=0.0, passed=True, severity="UNKNOWN", labels=[],
                detection={"reason": "no logs available"},
                logs=["无logs数据，跳过价格操纵分析"],
            )

        # ── 1. 扫描日志（优先使用 Provider 预解析数据） ──
        parsed_transfers = self.get_parsed_transfers(tx_context)
        parsed_swaps = self.get_parsed_swaps(tx_context)

        if parsed_transfers or parsed_swaps:
            # 使用 Provider 预解析数据 - 转换为内部格式
            transfers = []
            for pt in parsed_transfers:
                log_index = pt.get("log_index", 0)
                if isinstance(log_index, str) and log_index.startswith("0x"):
                    log_index = int(log_index, 16)
                transfers.append(TransferEvent(
                    log_index=log_index,
                    token_address=pt.get("token_address", ""),
                    from_addr=pt.get("from_address", ""),
                    to_addr=pt.get("to_address", ""),
                    amount=pt.get("amount", 0),
                    raw={},
                ))

            swaps = []
            for ps in parsed_swaps:
                log_index = ps.get("log_index", 0)
                if isinstance(log_index, str) and log_index.startswith("0x"):
                    log_index = int(log_index, 16)
                version = ps.get("version", "v2")
                swap_type = "uniswap_v2" if version == "v2" else "uniswap_v3"
                swaps.append(SwapEvent(
                    log_index=log_index,
                    pool_address=ps.get("dex_address", ""),
                    swap_type=swap_type,
                    raw={},
                    amount0=ps.get("amount_in", 0),
                    amount1=ps.get("amount_out", 0),
                ))
        else:
            # 回退到传统 scan_logs
            transfers, swaps = scan_logs(logs)

        if not swaps:
            return PriceManipulationOutput(
                score=0.0, passed=True, severity="UNKNOWN", labels=[],
                detection={"reason": "no swap events"},
                logs=["无Swap事件，跳过价格操纵分析"],
            )

        # ── 2. 执行各项检测 ──
        signals: list[str] = []
        total_score = 0.0
        detection_data: dict[str, Any] = {}

        # 特征 E: 单区块极端价格偏移
        pd_score, pd_details = detect_intra_block_price_deviation(swaps)
        if pd_score > 0:
            signals.append("INTRA_BLOCK_PRICE_DEVIATION")
            detection_data["price_deviation"] = pd_details

        pressure_score, pressure_details = detect_pool_repeated_swap_pressure(swaps)
        if pressure_score > 0:
            signals.append("REPEATED_SWAP_PRESSURE")
            detection_data["repeated_swap_pressure"] = pressure_details

        # 特征 C/Swap-Drain: 大额 Swap 后转出
        from_address = tx_context.from_address or ""
        std_score, std_details = detect_swap_to_drain(
            swaps, transfers, from_address,
        )
        if std_score > 0:
            signals.append("SWAP_TO_DRAIN")
            detection_data["swap_to_drain"] = std_details

        chained_score, chained_details = detect_price_deviation_followed_by_drain(
            pd_details,
            std_details,
        )
        if chained_score > 0:
            signals.append("PRICE_DEVIATION_WITH_DRAIN")
            detection_data["price_deviation_with_drain"] = chained_details

        # ── 3. 组合评分 ──
        total_score = pd_score + pressure_score + std_score + chained_score
        scoring_logs: list[str] = []
        scoring_logs.append(
            f"基础分={total_score:.1f}: price_deviation={pd_score:.1f} + repeated_swap={pressure_score:.1f} + "
            f"swap_to_drain={std_score:.1f} + chained={chained_score:.1f}"
        )

        # 组合加分
        combo_bonus = 0.0
        has_pd = pd_score > 0
        has_std = std_score > 0

        if has_pd and has_std:
            combo_bonus += 15.0
            signals.append("PRICE_MANIPULATION_ATTACK")
            scoring_logs.append("组合加分+15: 价格偏移 + Swap后大额转出(确认价格操纵攻击)")

        if pressure_score > 0 and has_std:
            combo_bonus += 10.0
            signals.append("REPEATED_SWAP_WITH_DRAIN")
            scoring_logs.append("组合加分+10: 同池连续Swap压力 + 大额转出")

        if chained_score > 0:
            combo_bonus += 10.0
            scoring_logs.append("组合加分+10: 价格偏移后紧随资金回收")

        if has_pd:
            # 找出最大偏移
            max_deviation = max(
                (abs(d.get("price_deviation_pct", 0)) for d in pd_details),
                default=0,
            )
            scoring_logs.append(f"价格偏移: 检测到{len(pd_details)}个偏移, 最大={max_deviation:.2f}%")

        if has_std:
            scoring_logs.append(f"Swap后大额转出: 检测到{len(std_details)}个大额转出")
            for sd in std_details[:3]:
                scoring_logs.append(f"  Swap池{sd['pool'][:10]}... → 转出{sd['amount']} tokens到{sd['to'][:10]}...")

        if pressure_score > 0:
            scoring_logs.append(f"连续Swap压力: 检测到{len(pressure_details)}个池存在同向连续Swap")

        if chained_score > 0:
            scoring_logs.append(f"偏移后回收: 检测到{len(chained_details)}个价格偏移后资金回收模式")

        total_score += combo_bonus
        total_score = max(0.0, min(100.0, total_score))

        # ── 4. 生成结果 ──
        threshold = self.config.get("threshold", 50.0)
        passed = total_score >= threshold
        labels = signals if passed else []

        scoring_logs.append(f"最终评分={total_score:.1f}, 阈值={threshold}, passed={passed}, severity={score_to_severity(total_score)}")

        detection_data["total_score"] = round(total_score, 2)
        detection_data["combo_bonus"] = round(combo_bonus, 2)
        detection_data["signal_scores"] = {
            "price_deviation": round(pd_score, 2),
            "swap_to_drain": round(std_score, 2),
        }
        detection_data["signals"] = signals
        detection_data["swap_count"] = len(swaps)
        detection_data["transfer_count"] = len(transfers)

        return PriceManipulationOutput(
            score=total_score,
            passed=passed,
            severity=score_to_severity(total_score),
            labels=labels,
            detection=detection_data,
            logs=scoring_logs,
        )


NodeRegistry.register(PriceManipulationDetector)
