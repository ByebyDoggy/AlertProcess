"""
经济异常检测器 — 基于 receipt/logs 的通用经济套利攻击检测

检测维度:
  1. ROI 异常: 交易内流出价值 / tx.value 超过阈值
  2. Token 销毁: ERC-20 Transfer(to=0x0)
  3. Token 铸造: ERC-20 Transfer(from=0x0)
  4. 铸造后立即转出: Mint-Then-Transfer 模式
  5. Swap 事件: Uniswap V2/V3 Swap 事件
  6. Swap-Burn-Claim 闭环: Swap → Burn → Drain 时序关联
  7. 零投入+无闪电贷+代币净收益: 无资金投入却获得大量代币
  8. 铸造后转出比例: 铸造代币被大比例转出 (>90%)
  9. 代理铸造者模式: 代理合约铸造代币后转给第三方

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
# 常量: 标准 ERC-20 / DEX 事件 topic
# ---------------------------------------------------------------------------

# ERC-20 Transfer(address indexed from, address indexed to, uint256 value)
ERC20_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# Uniswap V2 Swap(address indexed sender, uint256 amount0In, uint256 amount1In,
#                 uint256 amount0Out, uint256 amount1Out, address indexed to)
UNISWAP_V2_SWAP_TOPIC = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d714"

# Uniswap V3 Swap(address indexed sender, int256 amount0, int256 amount1,
#                 uint160 sqrtPriceX96, uint128 liquidity, int24 tick)
UNISWAP_V3_SWAP_TOPIC = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e7b213eb771"

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

# WETH 地址 → chain_id 映射（WETH 等价于原生 ETH，价格相同）
WETH_ADDRESSES: dict[int, str] = {
    1: "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",       # Ethereum WETH
    56: "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c",       # BSC WBNB
    137: "0x7ceb23fd6bc0add59e62ac25578270cff1b9f219",      # Polygon WETH
    42161: "0x82af49447d8a07e3bd95bd0d56f35241523fbab1",    # Arbitrum WETH
    10: "0x4200000000000000000000000000000000000006",       # Optimism WETH
}
_WETH_TO_CHAIN: dict[str, int] = {v.lower(): k for k, v in WETH_ADDRESSES.items()}


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

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
        # topic 全零或过短，返回零地址
        return "0x" + "0" * 40 if len(h) == 0 else "0x" + h.zfill(40)
    return "0x" + h[-40:]


def _wei_to_eth(wei: int) -> float:
    """wei → ETH 单位"""
    return wei / 10**18


# ---------------------------------------------------------------------------
# 日志解析结构
# ---------------------------------------------------------------------------

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


class SwapEvent:
    """解析后的 DEX Swap 事件"""
    __slots__ = ("log_index", "pool_address", "swap_type", "raw")

    def __init__(self, log_index: int, pool_address: str, swap_type: str, raw: dict):
        self.log_index = log_index
        self.pool_address = pool_address.lower()
        self.swap_type = swap_type  # "uniswap_v2" | "uniswap_v3"
        self.raw = raw


# ---------------------------------------------------------------------------
# 日志扫描器
# ---------------------------------------------------------------------------

def scan_logs(logs: list[dict]) -> tuple[list[TransferEvent], list[SwapEvent]]:
    """
    扫描 logs，提取所有 Transfer 和 Swap 事件。

    Returns:
        (transfers, swaps) 两个列表，均按 log_index 升序排列
    """
    transfers: list[TransferEvent] = []
    swaps: list[SwapEvent] = []

    for log in logs:
        topic0 = _extract_topic0(log)
        log_index = log.get("logIndex", log.get("log_index", 0))
        if isinstance(log_index, str) and log_index.startswith("0x"):
            log_index = int(log_index, 16)

        # ERC-20 Transfer
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

        # Uniswap V2 Swap
        elif topic0 == UNISWAP_V2_SWAP_TOPIC.lower():
            pool_address = (log.get("address") or "").lower()
            swaps.append(SwapEvent(
                log_index=log_index,
                pool_address=pool_address,
                swap_type="uniswap_v2",
                raw=log,
            ))

        # Uniswap V3 Swap
        elif topic0 == UNISWAP_V3_SWAP_TOPIC.lower():
            pool_address = (log.get("address") or "").lower()
            swaps.append(SwapEvent(
                log_index=log_index,
                pool_address=pool_address,
                swap_type="uniswap_v3",
                raw=log,
            ))

    return transfers, swaps


# ---------------------------------------------------------------------------
# 检测逻辑
# ---------------------------------------------------------------------------

def detect_roi_anomaly(
    tx_value_wei: int,
    transfers: list[TransferEvent],
    token_price_cache: Any,
    chain_id: int,
    native_price: float,
    roi_threshold: float,
    min_tx_value_eth: float,
    internal_eth_out_usd: float = 0.0,
) -> tuple[float, dict[str, Any]]:
    """
    特征 A: ROI 异常检测

    计算交易内所有 ERC-20 流出价值（折算 USD）与 tx.value 的比值。
    同时纳入内部 ETH 流出（从 eth_trace 提取的合约内部 ETH 转账）。
    当 tx.value 极小时，用绝对值兜底避免除零。

    Args:
        tx_value_wei: 交易输入的 ETH (wei)
        transfers: 解析后的 Transfer 事件列表
        token_price_cache: TokenPriceCache 全局实例
        chain_id: 链 ID
        native_price: 原生代币价格 (USD)
        roi_threshold: ROI 阈值 (倍数)
        min_tx_value_eth: 最小 tx.value (ETH)，低于此值用绝对流出判断
        internal_eth_out_usd: 从 eth_trace 提取的内部 ETH 流出总额 (USD)

    Returns:
        (score, details)
    """
    tx_value_eth = _wei_to_eth(tx_value_wei)

    # 计算 ERC-20 流出总价值
    total_out_usd = 0.0
    out_details: list[dict] = []

    for t in transfers:
        # 非销毁的转出（from 不是零地址 → 普通 Transfer 或铸造后的转出）
        if t.from_addr != ZERO_ADDRESS:
            # 尝试查价格
            price = None
            decimals = 18

            # WETH 等包装代币 → 使用原生代币价格
            if t.token_address.lower() in _WETH_TO_CHAIN:
                price = native_price
            elif token_price_cache:
                price = token_price_cache.get_price(chain_id, t.token_address)
                if token_price_cache:
                    meta = token_price_cache.get(chain_id, t.token_address)
                    if meta and meta.decimals:
                        decimals = meta.decimals

            if price is not None and price > 0:
                decimals = 18
                if token_price_cache:
                    meta = token_price_cache.get(chain_id, t.token_address)
                    if meta and meta.decimals:
                        decimals = meta.decimals
                value_usd = (t.amount / 10**decimals) * price
                total_out_usd += value_usd
                out_details.append({
                    "token": t.token_address,
                    "amount": t.amount,
                    "price_usd": price,
                    "value_usd": round(value_usd, 2),
                    "decimals": decimals,
                })

    # 加入内部 ETH 流出（如 FeesClaimed 等合约内部 ETH 转出）
    if internal_eth_out_usd > 0:
        total_out_usd += internal_eth_out_usd
        out_details.append({
            "token": "ETH (internal)",
            "amount": 0,
            "price_usd": native_price,
            "value_usd": round(internal_eth_out_usd, 2),
            "decimals": 18,
            "source": "eth_trace",
        })

    # tx.value 对应的 USD
    tx_value_usd = tx_value_eth * native_price

    # ROI 计算
    roi = 0.0
    if tx_value_eth >= min_tx_value_eth and tx_value_usd > 0:
        roi = total_out_usd / tx_value_usd
    elif tx_value_eth < min_tx_value_eth and total_out_usd > 0:
        # tx.value 极小但有大量流出 → 用极高 ROI 标记
        roi = 999.0

    # 评分
    score = 0.0
    if roi >= roi_threshold * 10:
        score = 80.0  # 极高 ROI
    elif roi >= roi_threshold:
        score = 50.0  # 高 ROI
    elif roi >= roi_threshold / 5:
        score = 25.0  # 中等 ROI

    return score, {
        "roi": round(roi, 2),
        "tx_value_eth": round(tx_value_eth, 6),
        "tx_value_usd": round(tx_value_usd, 2),
        "total_out_usd": round(total_out_usd, 2),
        "internal_eth_out_usd": round(internal_eth_out_usd, 2),
        "roi_threshold": roi_threshold,
        "out_details": out_details[:10],  # 限制数量
    }


def detect_burn_events(transfers: list[TransferEvent]) -> tuple[float, list[dict]]:
    """
    特征 B: 代币销毁检测 (Transfer to 0x0)

    Returns:
        (score, burn_details)
    """
    burns = [t for t in transfers if t.is_burn]
    if not burns:
        return 0.0, []

    score = min(30.0, 10.0 * len(burns))  # 每个销毁 +10，上限 30
    details = [{
        "token": t.token_address,
        "amount": t.amount,
        "from": t.from_addr,
        "log_index": t.log_index,
    } for t in burns]

    return score, details


def detect_mint_then_transfer(transfers: list[TransferEvent]) -> tuple[float, list[dict]]:
    """
    特征 D: 铸造后立即转出 (Mint-Then-Transfer)

    检测同一 token 的 from=0x0 Transfer 后紧跟同一 token 的普通 Transfer。
    如果铸造地址 = 后续转出地址的 from，则命中。

    Returns:
        (score, pattern_details)
    """
    # 按 token 分组
    mint_map: dict[str, list[TransferEvent]] = {}  # token → 铸造事件列表
    for t in transfers:
        if t.is_mint:
            mint_map.setdefault(t.token_address, []).append(t)

    if not mint_map:
        return 0.0, []

    patterns: list[dict] = []
    for token, mints in mint_map.items():
        # 收集铸造接收地址
        mint_recipients = {m.to_addr for m in mints}
        # 查找同 token 的后续普通 Transfer（from 为铸造接收者）
        for t in transfers:
            if (t.token_address == token
                    and not t.is_mint
                    and t.from_addr in mint_recipients):
                # 找到铸造 → 转出模式
                # 确保转出在铸造之后
                matching_mint = next(
                    (m for m in mints if m.to_addr == t.from_addr and m.log_index < t.log_index),
                    None
                )
                if matching_mint:
                    patterns.append({
                        "token": token,
                        "mint_to": matching_mint.to_addr,
                        "mint_amount": matching_mint.amount,
                        "mint_log_index": matching_mint.log_index,
                        "transfer_from": t.from_addr,
                        "transfer_to": t.to_addr,
                        "transfer_amount": t.amount,
                        "transfer_log_index": t.log_index,
                    })

    if not patterns:
        return 0.0, []

    score = min(40.0, 15.0 * len(patterns))  # 每个模式 +15，上限 40
    return score, patterns


def detect_swap_burn_claim_loop(
    swaps: list[SwapEvent],
    transfers: list[TransferEvent],
) -> tuple[float, dict[str, Any]]:
    """
    特征 F: Swap-Burn-Claim 闭环检测

    检测同一交易内: Swap 事件 → Token 销毁 → 大额转出/铸造 的时序闭环。

    Returns:
        (score, loop_details)
    """
    if not swaps or not transfers:
        return 0.0, {"detected": False}

    burns = [t for t in transfers if t.is_burn]
    if not burns:
        return 0.0, {"detected": False}

    # 检查时序: Swap(index) < Burn(index) < 后续大额转出/铸造(index)
    swap_indices = [s.log_index for s in swaps]
    burn_indices = [b.log_index for b in burns]

    # 找 Swap 之后出现的 Burn
    swap_before_burn = False
    matched_swap_idx = -1
    matched_burn_idx = -1
    for si in swap_indices:
        for bi in burn_indices:
            if si < bi:
                swap_before_burn = True
                matched_swap_idx = si
                matched_burn_idx = bi
                break
        if swap_before_burn:
            break

    if not swap_before_burn:
        return 0.0, {"detected": False}

    # 检查 Burn 之后是否有大额流出（铸造 or 普通 Transfer）
    post_burn_outflows: list[TransferEvent] = []
    for t in transfers:
        if t.log_index > matched_burn_idx and not t.is_burn:
            post_burn_outflows.append(t)

    # 铸造事件（Burn 后出现的 from=0x0）
    post_burn_mints = [t for t in transfers if t.is_mint and t.log_index > matched_burn_idx]

    loop_detected = len(post_burn_outflows) > 0 or len(post_burn_mints) > 0

    if not loop_detected:
        return 0.0, {"detected": False}

    score = 45.0  # 闭环基础分
    details = {
        "detected": True,
        "swap_log_index": matched_swap_idx,
        "burn_log_index": matched_burn_idx,
        "post_burn_outflows": len(post_burn_outflows),
        "post_burn_mints": len(post_burn_mints),
        "burn_tokens": list({b.token_address for b in burns if b.log_index == matched_burn_idx}),
        "mint_tokens": list({m.token_address for m in post_burn_mints}),
    }

    # 如果有铸造+转出模式，加分
    if post_burn_mints:
        score += 10.0

    return score, details


def detect_burn_then_drain(transfers: list[TransferEvent]) -> tuple[float, list[dict]]:
    """
    特征 C: 销毁触发大额资金释放 (Burn-Then-Drain)

    检测 Burn 事件后紧接大额非零地址转出的模式。

    Returns:
        (score, pattern_details)
    """
    burns = [t for t in transfers if t.is_burn]
    if not burns:
        return 0.0, []

    patterns: list[dict] = []
    for burn in burns:
        # 查找 Burn 之后的大额转出
        for t in transfers:
            if (t.log_index > burn.log_index
                    and not t.is_burn
                    and t.amount > 0
                    and t.token_address != burn.token_address):  # 不同 token 的流出
                patterns.append({
                    "burn_token": burn.token_address,
                    "burn_amount": burn.amount,
                    "burn_log_index": burn.log_index,
                    "drain_token": t.token_address,
                    "drain_amount": t.amount,
                    "drain_from": t.from_addr,
                    "drain_to": t.to_addr,
                    "drain_log_index": t.log_index,
                })

    if not patterns:
        return 0.0, []

    score = min(35.0, 12.0 * len(patterns))  # 每个模式 +12，上限 35
    return score, patterns


def detect_zero_cost_token_gain(
    tx_value_wei: int,
    transfers: list[TransferEvent],
    swaps: list[SwapEvent],
    from_address: str,
    token_price_cache: Any,
    chain_id: int,
    native_price: float,
    min_gain_usd: float = 10000.0,
) -> tuple[float, dict[str, Any]]:
    """
    特征 G: 零投入 + 无闪电贷 + 代币净收益检测

    当 tx.value=0 且无 DEX Swap（无闪电贷的间接指标）且攻击者 ERC-20 余额净增加
    超过阈值时，标记为零投入异常。这是最强的攻击信号之一。

    Args:
        tx_value_wei: 交易输入的原生代币 (wei)
        transfers: 解析后的 Transfer 事件列表
        swaps: 解析后的 Swap 事件列表
        from_address: 交易发起者地址
        token_price_cache: TokenPriceCache 全局实例
        chain_id: 链 ID
        native_price: 原生代币价格 (USD)
        min_gain_usd: 最小净收益阈值 (USD)

    Returns:
        (score, details)
    """
    tx_value_eth = _wei_to_eth(tx_value_wei)
    has_flash_loan_proxy = len(swaps) > 0  # 有 Swap 说明可能有闪电贷

    # 零投入条件: tx.value 极小且无 Swap
    is_zero_cost = tx_value_eth < 0.001 and not has_flash_loan_proxy

    if not is_zero_cost:
        return 0.0, {"detected": False, "reason": "not_zero_cost"}

    # 计算每个地址的 ERC-20 净收益
    from_addr_lower = (from_address or "").lower()
    address_balances: dict[str, dict[str, int]] = {}  # addr → {token → net_change}

    for t in transfers:
        # 忽略铸造和销毁的 from/to
        if t.from_addr != ZERO_ADDRESS:
            addr = t.from_addr
            address_balances.setdefault(addr, {})
            address_balances[addr].setdefault(t.token_address, 0)
            address_balances[addr][t.token_address] -= t.amount
        if t.to_addr != ZERO_ADDRESS:
            addr = t.to_addr
            address_balances.setdefault(addr, {})
            address_balances[addr].setdefault(t.token_address, 0)
            address_balances[addr][t.token_address] += t.amount

    # 计算 from_address 的 ERC-20 净收益
    sender_gains: list[dict] = []
    total_gain_usd = 0.0

    sender_balances = address_balances.get(from_addr_lower, {})
    for token, net_change in sender_balances.items():
        if net_change <= 0:
            continue
        # 查价格
        price = None
        decimals = 18
        if token.lower() in _WETH_TO_CHAIN:
            price = native_price
        elif token_price_cache:
            price = token_price_cache.get_price(chain_id, token)
            meta = token_price_cache.get(chain_id, token)
            if meta and meta.decimals:
                decimals = meta.decimals

        if price and price > 0:
            gain_usd = (net_change / 10**decimals) * price
            total_gain_usd += gain_usd
            sender_gains.append({
                "token": token,
                "amount": net_change,
                "price_usd": price,
                "gain_usd": round(gain_usd, 2),
            })

    if total_gain_usd < min_gain_usd:
        return 0.0, {
            "detected": False,
            "reason": "gain_below_threshold",
            "total_gain_usd": round(total_gain_usd, 2),
            "min_gain_usd": min_gain_usd,
        }

    # 评分: 零投入 + 无闪电贷 + 大量代币净收益
    score = 0.0
    if total_gain_usd >= 1_000_000:
        score = 50.0
    elif total_gain_usd >= 100_000:
        score = 40.0
    elif total_gain_usd >= min_gain_usd:
        score = 30.0

    return score, {
        "detected": True,
        "tx_value_eth": round(tx_value_eth, 6),
        "has_swap": has_flash_loan_proxy,
        "total_gain_usd": round(total_gain_usd, 2),
        "gains": sender_gains[:10],
    }


def detect_mint_transfer_ratio(transfers: list[TransferEvent]) -> tuple[float, list[dict]]:
    """
    特征 H: 铸造后转出比例检测

    检测 Transfer(from=0x0, to=X) 后紧接 Transfer(from=X, to=Y)，
    且转出量/铸造量 > 阈值（如 90%）的异常模式。
    这区分了正常的小额转出和攻击者几乎全部转走的行为。

    Returns:
        (score, pattern_details)
    """
    # 按 token 分组铸造事件
    mint_map: dict[str, list[TransferEvent]] = {}
    for t in transfers:
        if t.is_mint:
            mint_map.setdefault(t.token_address, []).append(t)

    if not mint_map:
        return 0.0, []

    HIGH_RATIO_THRESHOLD = 0.9  # 90% 转出比例
    patterns: list[dict] = []

    for token, mints in mint_map.items():
        mint_recipients = {m.to_addr for m in mints}
        # 按铸造接收者汇总铸造量
        recipient_mint_total: dict[str, int] = {}
        for m in mints:
            recipient_mint_total[m.to_addr] = recipient_mint_total.get(m.to_addr, 0) + m.amount

        # 查找同 token 的后续转出（from=铸造接收者）
        for t in transfers:
            if (t.token_address == token
                    and not t.is_mint
                    and not t.is_burn
                    and t.from_addr in mint_recipients
                    and t.to_addr != ZERO_ADDRESS):
                # 确保转出在铸造之后
                matching_mint = next(
                    (m for m in mints if m.to_addr == t.from_addr and m.log_index < t.log_index),
                    None,
                )
                if matching_mint and matching_mint.amount > 0:
                    ratio = t.amount / matching_mint.amount
                    if ratio >= HIGH_RATIO_THRESHOLD:
                        patterns.append({
                            "token": token,
                            "mint_to": matching_mint.to_addr,
                            "mint_amount": matching_mint.amount,
                            "transfer_to": t.to_addr,
                            "transfer_amount": t.amount,
                            "ratio": round(ratio, 4),
                            "mint_log_index": matching_mint.log_index,
                            "transfer_log_index": t.log_index,
                        })

    if not patterns:
        return 0.0, []

    score = min(25.0, 10.0 * len(patterns))  # 每个模式 +10，上限 25
    return score, patterns


def detect_proxy_mint_pattern(transfers: list[TransferEvent]) -> tuple[float, list[dict]]:
    """
    特征 I: 代理铸造者模式检测

    检测非代币合约的地址（代理铸造者）触发铸造后，将代币转给第三方的模式。
    关键特征: Transfer(from=0x0, to=X) + Transfer(from=X, to=Y)，
    其中 X 是代理铸造者，Y 是非协议标准地址（如 EOA）。

    与 detect_mint_then_transfer 的区别:
    - detect_mint_then_transfer 只检测是否存在铸造后转出模式
    - 本函数额外检查:
      1. 铸造接收者 X 的余额净变化 ≈ 0（几乎全部转出）
      2. 最终接收者 Y 不是零地址或铸造者自身
      3. 转出比例 > 90%

    Returns:
        (score, pattern_details)
    """
    # 按 token 分组铸造事件
    mint_map: dict[str, list[TransferEvent]] = {}
    for t in transfers:
        if t.is_mint:
            mint_map.setdefault(t.token_address, []).append(t)

    if not mint_map:
        return 0.0, []

    PROXY_RATIO_THRESHOLD = 0.9  # 代理铸造者转出 90% 以上
    patterns: list[dict] = []

    for token, mints in mint_map.items():
        for mint in mints:
            proxy_addr = mint.to_addr  # 代理铸造者地址
            if proxy_addr == ZERO_ADDRESS:
                continue

            # 汇总该代理地址在同 token 上的铸造总量
            total_minted = sum(
                m.amount for m in mints
                if m.to_addr == proxy_addr and m.log_index <= mint.log_index + 50
            )

            # 查找该代理地址的转出（from=proxy_addr, to=非自身非零地址）
            total_transferred_out = 0
            transfer_targets: list[dict] = []
            for t in transfers:
                if (t.token_address == token
                        and t.from_addr == proxy_addr
                        and t.to_addr != ZERO_ADDRESS
                        and t.to_addr != proxy_addr
                        and t.log_index > mint.log_index):
                    total_transferred_out += t.amount
                    transfer_targets.append({
                        "to": t.to_addr,
                        "amount": t.amount,
                        "log_index": t.log_index,
                    })

            if total_minted <= 0 or not transfer_targets:
                continue

            ratio = total_transferred_out / total_minted
            if ratio >= PROXY_RATIO_THRESHOLD:
                patterns.append({
                    "token": token,
                    "proxy_minter": proxy_addr,
                    "mint_amount": total_minted,
                    "transferred_out": total_transferred_out,
                    "ratio": round(ratio, 4),
                    "targets": transfer_targets[:5],
                    "mint_log_index": mint.log_index,
                })

    if not patterns:
        return 0.0, []

    score = min(20.0, 10.0 * len(patterns))  # 每个模式 +10，上限 20
    return score, patterns


# ---------------------------------------------------------------------------
# EconomicAnomalyDetector
# ---------------------------------------------------------------------------

class EconomicAnomalyOutput(DetectorOutputMixin):
    """经济异常检测器输出"""
    pass


class EconomicAnomalyDetector(BaseDetector):
    """
    经济异常检测器 — 基于 receipt/logs 的通用经济套利攻击检测。

    检测维度:
      - ROI 异常: 流出价值 / tx.value > 阈值（含内部 ETH 流出）
      - Token 销毁: ERC-20 Transfer(to=0x0)
      - Token 铸造后立即转出: Mint-Then-Transfer
      - Swap-Burn-Claim 闭环: DEX Swap → 销毁 → 流出的时序
      - 销毁触发大额释放: Burn-Then-Drain
      - 零投入+无闪电贷+代币净收益: 无资金投入却获得大量代币
      - 铸造后转出比例: 铸造代币被大比例转出 (>90%)
      - 代理铸造者模式: 代理合约铸造代币后转给第三方

    所有检测仅依赖 ERC-20 Transfer 事件和 DEX Swap 事件，
    不依赖任何特定函数签名，天然具备跨协议通用性。
    同时支持从 eth_trace 提取内部 ETH 流出用于 ROI 计算。
    """

    name: str = "economic_anomaly_detector"
    label: str = "经济异常检测"
    description: str = (
        "[数据需求: Logs + Trace(辅助)] "
        "检测经济套利类攻击：极高 ROI（投入产出比异常）、"
        "Token 销毁信号、铸造后立即转出、Swap-Burn-Claim 闭环、"
        "销毁触发大额资金释放、零投入+无闪电贷代币净收益、"
        "铸造后转出比例异常、代理铸造者模式。"
        "主要依赖标准 ERC-20/DEX 事件，"
        "辅助使用 eth_trace 提取内部 ETH 流出用于 ROI 计算，不依赖函数签名，具备跨协议通用性"
    )
    icon: str = "\U0001f4c8"
    color: str = "#8b5cf6"

    # ── Pydantic 配置模型 ──
    class ConfigModel(DetectorConfigMixin):
        roi_threshold: float = Field(
            default=50.0, ge=1.0,
            description="ROI 阈值（倍数），流出台账/tx.value 超过此值视为异常",
        )
        min_tx_value_eth: float = Field(
            default=0.001, ge=0,
            description="最小 tx.value（ETH），低于此值用绝对流出判断而非 ROI 比值",
        )
        check_erc20_value: bool = Field(
            default=True,
            description="是否查 TokenPriceCache 折算 ERC-20 流出价值（需 MarketDataBase 可用）",
        )

    # ── Pydantic 输出模型 ──
    OutputModel: type = EconomicAnomalyOutput

    def _extract_internal_eth_out_usd(self, tx_context: TransactionContext) -> float:
        """
        从 eth_trace 数据中提取内部 ETH 流出的总 USD 价值。

        内部 ETH 流出是指合约内部通过 CALL 等方式转出的 ETH，
        如 FeesClaimed、withdraw 等，这些不会出现在 ERC-20 Transfer 事件中。

        计算方式:
          1. 遍历 eth_trace 中的所有调用条目
          2. 筛选 value > 0 的调用（排除顶层 tx.value 调用）
          3. 将所有内部 ETH 流出求和，折算 USD

        Returns:
            内部 ETH 流出总额 (USD)，无数据时返回 0.0
        """
        eth_trace = tx_context.get_extra("eth_trace")
        if not eth_trace or not isinstance(eth_trace, dict):
            return 0.0

        traces = eth_trace.get("traces") or []
        if not traces:
            return 0.0

        chain_id = tx_context.chain_id or 1
        native_price = self.token_price_instance.get_price(chain_id, "") or 0.0
        if native_price <= 0:
            return 0.0

        from_addr = (tx_context.from_address or "").lower()
        to_addr = (tx_context.to_address or "").lower()
        tx_value_wei = tx_context.value or 0
        extra_value = tx_context.get_extra("value_wei")
        if extra_value:
            tx_value_wei = _hex_to_int(extra_value)

        total_internal_eth_wei = 0

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
                action_dict = entry.get("action", {})
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

            # 跳过最顶层调用（它就是 tx.value 本身）
            if (call_from == from_addr and call_to == to_addr
                    and value == tx_value_wei):
                continue

            total_internal_eth_wei += value

        if total_internal_eth_wei <= 0:
            return 0.0

        total_internal_eth = total_internal_eth_wei / 10**18
        return total_internal_eth * native_price

    async def process(self, tx_context: TransactionContext) -> EconomicAnomalyOutput:
        chain_id = tx_context.chain_id or 1
        tx_value_wei = tx_context.value or 0
        # 优先从 extra 取 value_wei（某些 Provider 可能覆盖）
        extra_value = tx_context.get_extra("value_wei")
        if extra_value:
            tx_value_wei = _hex_to_int(extra_value)

        logs: list[dict] = tx_context.logs or []

        # ── 从 eth_trace 提取内部 ETH 流出（即使 logs 为空也可用） ──
        internal_eth_out_usd = self._extract_internal_eth_out_usd(tx_context)

        # 当 logs 为空但有内部 ETH 流出数据时，仍然可以进行 ROI 检测
        # 但其他基于 logs 的检测（burn/mint/swap/闭环）需要 logs 数据
        if not logs and internal_eth_out_usd <= 0:
            return EconomicAnomalyOutput(
                score=0.0, passed=True, severity="UNKNOWN", labels=[],
                detection={"reason": "no logs available and no internal ETH outflow detected"},
                logs=["无logs数据且无内部ETH流出，跳过经济异常分析"],
            )

        # ── 1. 扫描日志 ──
        transfers, swaps = scan_logs(logs)

        # ── 2. 获取原生代币价格（通过 TokenPriceCache，含硬编码 fallback） ──
        native_price = self.token_price_instance.get_price(chain_id, "") or 0.0

        # ── 3. 执行各项检测 ──
        signals: list[str] = []
        total_score = 0.0
        detection_data: dict[str, Any] = {}

        # 特征 A: ROI 异常
        roi_score = 0.0
        if self.config.get("check_erc20_value", True) and native_price > 0:
            roi_threshold = self.config.get("roi_threshold", 50.0)
            min_tx_eth = self.config.get("min_tx_value_eth", 0.001)
            cache = self.token_price_instance if self.config.get("check_erc20_value", True) else None
            roi_score, roi_details = detect_roi_anomaly(
                tx_value_wei=tx_value_wei,
                transfers=transfers,
                token_price_cache=cache,
                chain_id=chain_id,
                native_price=native_price,
                roi_threshold=roi_threshold,
                min_tx_value_eth=min_tx_eth,
                internal_eth_out_usd=internal_eth_out_usd,
            )
            if roi_score > 0:
                signals.append("HIGH_ROI")
                detection_data["roi"] = roi_details

        # 特征 B: Token 销毁
        burn_score, burn_details = detect_burn_events(transfers)
        if burn_score > 0:
            signals.append("TOKEN_BURN")
            detection_data["burns"] = burn_details

        # 特征 C: 销毁触发大额释放
        btd_score, btd_details = detect_burn_then_drain(transfers)
        if btd_score > 0:
            signals.append("BURN_THEN_DRAIN")
            detection_data["burn_then_drain"] = btd_details

        # 特征 D: 铸造后立即转出
        mtt_score, mtt_details = detect_mint_then_transfer(transfers)
        if mtt_score > 0:
            signals.append("MINT_THEN_TRANSFER")
            detection_data["mint_then_transfer"] = mtt_details

        # 特征 F: Swap-Burn-Claim 闭环
        sbc_score, sbc_details = detect_swap_burn_claim_loop(swaps, transfers)
        if sbc_details.get("detected"):
            signals.append("SWAP_BURN_CLAIM_LOOP")
            detection_data["swap_burn_claim_loop"] = sbc_details

        # 特征 G: 零投入 + 无闪电贷 + 代币净收益
        zctg_score = 0.0
        zctg_details: dict[str, Any] = {"detected": False}
        if self.config.get("check_erc20_value", True) and native_price > 0:
            from_address = tx_context.from_address or ""
            zctg_score, zctg_details = detect_zero_cost_token_gain(
                tx_value_wei=tx_value_wei,
                transfers=transfers,
                swaps=swaps,
                from_address=from_address,
                token_price_cache=self.token_price_instance if self.config.get("check_erc20_value", True) else None,
                chain_id=chain_id,
                native_price=native_price,
            )
            if zctg_details.get("detected"):
                signals.append("ZERO_COST_TOKEN_GAIN")
                detection_data["zero_cost_token_gain"] = zctg_details

        # 特征 H: 铸造后转出比例
        mtr_score, mtr_details = detect_mint_transfer_ratio(transfers)
        if mtr_score > 0:
            signals.append("HIGH_MINT_TRANSFER_RATIO")
            detection_data["mint_transfer_ratio"] = mtr_details

        # 特征 I: 代理铸造者模式
        pm_score, pm_details = detect_proxy_mint_pattern(transfers)
        if pm_score > 0:
            signals.append("PROXY_MINT_PATTERN")
            detection_data["proxy_mint_pattern"] = pm_details

        # ── 4. 组合评分 ──
        # 基础分 = 各特征分之和
        total_score = roi_score + burn_score + btd_score + mtt_score + sbc_score + zctg_score + mtr_score + pm_score
        scoring_logs: list[str] = []
        scoring_logs.append(f"基础分合计={total_score:.1f}: roi={roi_score:.1f} + burn={burn_score:.1f} + burn_then_drain={btd_score:.1f} + mint_then_transfer={mtt_score:.1f} + swap_burn_claim_loop={sbc_score:.1f} + zero_cost_gain={zctg_score:.1f} + mint_transfer_ratio={mtr_score:.1f} + proxy_mint={pm_score:.1f}")

        # 组合加分: 关键特征联动
        combo_bonus = 0.0
        has_roi = roi_score >= 50
        has_burn = burn_score > 0
        has_loop = sbc_details.get("detected", False)
        has_btd = btd_score > 0
        has_mtt = mtt_score > 0
        has_zctg = zctg_details.get("detected", False)
        has_mtr = mtr_score > 0
        has_pm = pm_score > 0

        # ROI + 闭环 → 强攻击信号
        if has_roi and has_loop:
            combo_bonus += 15.0
            signals.append("ROI_PLUS_LOOP")
            scoring_logs.append("组合加分+15: ROI异常 + Swap-Burn-Claim闭环")

        # ROI + 销毁释放 → 攻击
        if has_roi and has_btd:
            combo_bonus += 10.0
            signals.append("ROI_PLUS_BURN_DRAIN")
            scoring_logs.append("组合加分+10: ROI异常 + 销毁触发释放")

        # 闭环 + 销毁释放 → 确认攻击路径
        if has_loop and has_btd:
            combo_bonus += 8.0
            signals.append("LOOP_PLUS_BURN_DRAIN")
            scoring_logs.append("组合加分+8: 闭环 + 销毁释放")

        # ROI + 铸造转出 → Burn-to-Earn 模式
        if has_roi and has_mtt:
            combo_bonus += 10.0
            signals.append("ROI_PLUS_MINT_TRANSFER")
            scoring_logs.append("组合加分+10: ROI异常 + 铸造后转出(Burn-to-Earn模式)")

        # 零投入 + 铸造 + 转出 → 未授权铸造攻击
        if has_zctg and has_mtt:
            combo_bonus += 20.0
            signals.append("ZERO_COST_MINT_ATTACK")
            scoring_logs.append("组合加分+20: 零投入代币净收益 + 铸造后转出(未授权铸造攻击)")

        # 零投入 + 代理铸造 → 协议逻辑漏洞利用
        if has_zctg and has_pm:
            combo_bonus += 15.0
            signals.append("ZERO_COST_PROXY_MINT")
            scoring_logs.append("组合加分+15: 零投入代币净收益 + 代理铸造者模式(协议逻辑漏洞)")

        # 铸造 + 高转出比例 + 代理铸造 → 铸造后套现闭环
        if has_mtr and has_pm:
            combo_bonus += 12.0
            signals.append("MINT_CASHOUT_LOOP")
            scoring_logs.append("组合加分+12: 铸造后高转出比例 + 代理铸造者(铸造后套现闭环)")

        # 全部命中 → 几乎确定攻击
        if has_roi and has_loop and has_burn:
            combo_bonus += 10.0
            signals.append("FULL_ECONOMIC_ATTACK_PATTERN")
            scoring_logs.append("组合加分+10: ROI + 闭环 + 销毁全部命中(几乎确定攻击)")

        if combo_bonus > 0:
            scoring_logs.append(f"组合加分合计=+{combo_bonus:.1f}")
        else:
            scoring_logs.append("无组合加分: 特征未联动")

        total_score += combo_bonus
        total_score = max(0.0, min(100.0, total_score))

        # ── 5. 生成结果 ──
        threshold = self.config.get("threshold", 50.0)
        passed = total_score >= threshold
        labels = signals if passed else []

        # 补充各特征的日志
        if roi_score > 0:
            roi_detail = detection_data.get("roi", {})
            scoring_logs.append(f"ROI异常: roi={roi_detail.get('roi', 0):.1f}x, tx_value=${roi_detail.get('tx_value_usd', 0):,.2f}, drain=${roi_detail.get('total_out_usd', 0):,.2f}")
        elif not logs:
            scoring_logs.append("ROI检测: 无logs数据")
        else:
            scoring_logs.append("ROI检测: 未达异常阈值或价格不可用")

        if burn_score > 0:
            scoring_logs.append(f"代币销毁: 检测到{len(detection_data.get('burns', []))}个Transfer(to=0x0)事件")
        if btd_score > 0:
            scoring_logs.append(f"销毁触发释放: 检测到{len(detection_data.get('burn_then_drain', []))}个Burn-Then-Drain模式")
        if mtt_score > 0:
            scoring_logs.append(f"铸造后转出: 检测到{len(detection_data.get('mint_then_transfer', []))}个Mint-Then-Transfer模式")
        if sbc_details.get("detected"):
            scoring_logs.append(f"Swap-Burn-Claim闭环: swap_idx={sbc_details.get('swap_log_index')}, burn_idx={sbc_details.get('burn_log_index')}, 后续流出={sbc_details.get('post_burn_outflows', 0)}, 后续铸造={sbc_details.get('post_burn_mints', 0)}")
        if zctg_details.get("detected"):
            scoring_logs.append(f"零投入代币净收益: gain=${zctg_details.get('total_gain_usd', 0):,.2f}, has_swap={zctg_details.get('has_swap')}")
        if mtr_score > 0:
            scoring_logs.append(f"铸造后转出比例异常: 检测到{len(detection_data.get('mint_transfer_ratio', []))}个高转出比例模式(>90%)")
        if pm_score > 0:
            scoring_logs.append(f"代理铸造者模式: 检测到{len(detection_data.get('proxy_mint_pattern', []))}个代理铸造后转出模式")

        scoring_logs.append(f"最终评分={total_score:.1f}, 阈值={threshold}, passed={passed}, severity={score_to_severity(total_score)}")

        detection_data["total_score"] = round(total_score, 2)
        detection_data["combo_bonus"] = round(combo_bonus, 2)
        detection_data["signal_scores"] = {
            "roi": round(roi_score, 2),
            "burn": round(burn_score, 2),
            "burn_then_drain": round(btd_score, 2),
            "mint_then_transfer": round(mtt_score, 2),
            "swap_burn_claim_loop": round(sbc_score, 2),
            "zero_cost_token_gain": round(zctg_score, 2),
            "mint_transfer_ratio": round(mtr_score, 2),
            "proxy_mint_pattern": round(pm_score, 2),
        }
        detection_data["signals"] = signals
        detection_data["transfer_count"] = len(transfers)
        detection_data["swap_count"] = len(swaps)
        detection_data["burn_count"] = len([t for t in transfers if t.is_burn])
        detection_data["mint_count"] = len([t for t in transfers if t.is_mint])

        return EconomicAnomalyOutput(
            score=total_score,
            passed=passed,
            severity=score_to_severity(total_score),
            labels=labels,
            detection=detection_data,
            logs=scoring_logs,
        )


NodeRegistry.register(EconomicAnomalyDetector)
