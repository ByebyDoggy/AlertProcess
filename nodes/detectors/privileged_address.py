"""
特权地址监控检测器 — 基于地址标签和高权限调用模式检测私钥泄露攻击

检测维度（基于 Infini 攻击分析的特征 A、D、F）:
  1. 已知特权地址检测 (Known Privileged Address):
     检查交易的 Sender 是否在已知管理员/开发者/团队地址列表中。
     私钥泄露攻击的核心特征：调用者身份异常。

  2. 特权函数调用检测 (Privileged Function Call):
     检查调用的函数签名是否为非标准函数（不在常见 DeFi 函数签名集中）。
     攻击者使用的通常是协议的 privileged 函数，而非标准公开函数。

  3. 零投入资金提取检测 (Zero-Input Fund Extraction):
     tx.value == 0 且有大量资金从协议合约流出的模式。
     Sender 未投入任何资金却从协议中提取大量资产。

  4. 资金流向外部检测 (Funds Flow to External):
     检测交易的大额资金流向是否是非协议合约的外部地址。
     如果是已知特权地址发出的交易，流向外部地址是强信号。

数据源:
  - tx_context.from_address: 交易发送者地址
  - tx_context.to_address: 交易目标合约
  - tx_context.value: 交易的 ETH 输入
  - tx_context.logs: ERC-20 Transfer 事件日志（用于检测资金流出）
  - tx_context.input_data: calldata（用于检测特权函数调用）
  - tx_context.extra["privileged_addresses"]: 可选的已知特权地址列表（覆盖配置）
  - tx_context.extra["known_protocol_addresses"]: 可选的已知协议金库地址列表

评分逻辑（参考 Infini 分析文档）:
  - 已知特权地址调用: +20
  - 每笔大额资金提取: +15
  - 非标准函数调用: +10
  - 资金流向外部地址: +25
  - 零投入: +15（叠加资金提取时额外加分）
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

# ERC-20 Transfer 事件 Topic
ERC20_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

# 常见 DeFi 公开函数签名（第一轮调用），不在该集合中视为 privileged 调用
# 4 字节函数选择器列表
COMMON_FUNCTION_SELECTORS: set[str] = {
    # ERC-20 标准
    "0xa9059cbb",  # transfer(address,uint256)
    "0x23b872dd",  # transferFrom(address,address,uint256)
    "0x095ea7b3",  # approve(address,uint256)
    "0x70a08231",  # balanceOf(address)
    "0x18160ddd",  # totalSupply()
    "0xdd62ed3e",  # allowance(address,address)
    # Uniswap V2
    "0x38ed1739",  # swapExactTokensForTokens
    "0x7ff36ab5",  # swapExactETHForTokens
    "0x4a25d94a",  # swapTokensForExactTokens
    "0x5c11d795",  # swapExactTokensForETH
    "0x18cbafe5",  # swapExactTokensForTokensSupportingFeeOnTransferTokens
    "0xd0e30db0",  # deposit (WETH)
    "0x2e1a7d4d",  # withdraw (WETH)
    # Uniswap V3
    "0x414bf389",  # exactInputSingle
    "0x04e45aaf",  # exactInput
    "0xdb3e2198",  # exactOutputSingle
    "0x09b81346",  # exactOutput
    # Multicall
    "0xac9650d8",  # multicall
    "0xbce38bd7",  # multicall (different)
    "0x5ae401dc",  # multicall (Uniswap)
    "0x1fcd4783",  # multicall (Pancake)
    # Flash Loan (AAVE)
    "0x7ac09bf0",  # flashLoan
    "0xab9c4b5d",  # flashLoanSimple
    # Curve
    "0x3df02124",  # exchange
    "0xa6417ed6",  # add_liquidity
    "0x5b36389c",  # remove_liquidity
    "0x3b3b57de",  # remove_liquidity_one_coin
    "0xf446c1d0",  # remove_liquidity_imbalance
    # Balancer
    "0x945bcec9",  # swap
    "0x52bbbe29",  # batchSwap
    "0x7c16924e",  # joinPool
    "0xbb1420ae",  # exitPool
    # Stargate
    "0xa11001d6",  # swap
    # Lido
    "0xa1903eab",  # submit
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
    """提取 log 的 topic0"""
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


def _extract_function_selector(input_data: str) -> str:
    """从 calldata 中提取 4 字节函数选择器"""
    if not input_data or not input_data.startswith("0x") or len(input_data) < 10:
        return ""
    return input_data[:10].lower()


# ---------------------------------------------------------------------------
# 检测函数
# ---------------------------------------------------------------------------


def detect_privileged_sender(
    from_address: str,
    privileged_addresses: list[str],
) -> tuple[float, dict[str, Any]]:
    """
    检测 Sender 是否为已知特权地址。

    如果 Sender 在已知管理员/开发者/团队地址列表中，返回正分。

    Args:
        from_address: 交易发送者地址
        privileged_addresses: 已知特权地址列表（从小写比较）

    Returns:
        (score, details)
            score: 0 或 20.0
            details: 匹配详情
    """
    addr_lower = from_address.lower()
    matched = [a for a in privileged_addresses if a.lower() == addr_lower]

    if matched:
        return 20.0, {
            "detected": True,
            "privileged_address": from_address,
            "match_count": len(matched),
        }

    return 0.0, {"detected": False}


def detect_privileged_function_call(
    input_data: str,
    known_function_names: dict[str, str] | None = None,
) -> tuple[float, dict[str, Any]]:
    """
    检测调用是否为非标准特权函数。

    如果 calldata 的函数选择器不在常见 DeFi 函数签名集合中，
    且不是空调用（transfer 或普通转账），视为特权函数调用。

    Args:
        input_data: 交易的 calldata
        known_function_names: 可选，已知函数选择器->名称映射（用于日志记录）

    Returns:
        (score, details)
            score: 0 或 10.0
            details: 检测详情
    """
    selector = _extract_function_selector(input_data)

    if not selector:
        # 无 calldata 或数据过短 -> 无法判断
        return 0.0, {"detected": False, "reason": "no_selector"}

    is_unknown = selector not in COMMON_FUNCTION_SELECTORS

    if is_unknown:
        function_name = "unknown"
        if known_function_names and selector in known_function_names:
            function_name = known_function_names[selector]

        return 10.0, {
            "detected": True,
            "selector": selector,
            "function_name": function_name,
        }

    return 0.0, {"detected": False, "selector": selector, "reason": "known_function"}


def detect_large_fund_outflow(
    from_address: str,
    logs: list[dict],
    chain_id: int,
    min_outflow_usd: float = 50000.0,
    known_protocol_addresses: list[str] | None = None,
) -> tuple[float, list[dict], float]:
    """
    检测交易中是否有大额资金从协议合约流出到外部地址。

    遍历所有 ERC-20 Transfer 事件，查找满足以下条件的转账:
    - from 不是交易 Sender（资金从协议合约流出）
    - to 不是零地址（不是销毁）
    - to 不在已知协议金库地址列表中（流出到外部）
    - 金额超过阈值

    Args:
        from_address: 交易 Sender 地址（用于排除 Sender 自转账）
        logs: 交易的事件日志
        chain_id: 链 ID
        min_outflow_usd: 最小流出 USD 阈值
        known_protocol_addresses: 已知协议金库地址列表

    Returns:
        (score, outflow_details, total_outflow_usd)
    """
    known_addrs = [a.lower() for a in (known_protocol_addresses or [])]
    sender_lower = from_address.lower()

    outflows: list[dict] = []
    total_usd = 0.0

    for log in logs:
        topic0 = _extract_topic0(log)
        if topic0 != ERC20_TRANSFER_TOPIC.lower():
            continue

        topics = log.get("topics", [])
        if len(topics) < 3:
            continue

        t_from = _extract_address_from_topic(topics[1])
        t_to = _extract_address_from_topic(topics[2])
        data = log.get("data", "0x")
        amount = _hex_to_int(data) if data else 0
        token_addr = (log.get("address") or "").lower()

        if amount <= 0:
            continue

        # 排除 Sender 自转账
        if t_from == sender_lower:
            continue
        # 排除销毁
        if t_to == ZERO_ADDRESS:
            continue
        # 排除已知协议金库地址
        if t_to.lower() in known_addrs:
            continue
        # 排除零地址来源
        if t_from == ZERO_ADDRESS:
            continue

        # 简单 USD 估算（假设稳定币 1:1），精确估值留给后续检测器
        # 链上多数提取为稳定币，此处用 1 USD 做近似
        decimals = 18
        if token_addr == "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48":  # USDC
            decimals = 6
        elif token_addr == "0xdac17f958d2ee523a2206206994597c13d831ec7":  # USDT
            decimals = 6

        value_usd = amount / 10 ** decimals

        if value_usd >= min_outflow_usd:
            outflows.append({
                "from": t_from,
                "to": t_to,
                "token": token_addr,
                "amount": amount,
                "value_usd": round(value_usd, 2),
                "log_index": log.get("logIndex", log.get("log_index", 0)),
            })
            total_usd += value_usd

    if not outflows:
        return 0.0, [], 0.0

    # 评分: 每笔大额流出 +15，上限 45
    score = min(45.0, 15.0 * len(outflows))

    # 资金流向外部加分: 如果检测到特权地址 + 外部流出，外部流向信号
    # 单独评分，由调用方组合
    external_flow_detected = any(
        o["to"].lower() not in known_addrs and o["to"].lower() != sender_lower
        for o in outflows
    )
    if external_flow_detected:
        score = max(score, 25.0)  # 至少 25 分

    return score, outflows, total_usd


# ---------------------------------------------------------------------------
# PrivilegedAddressMonitor 输出
# ---------------------------------------------------------------------------


class PrivilegedAddressOutput(DetectorOutputMixin):
    """特权地址监控检测器输出"""
    pass


# ---------------------------------------------------------------------------
# PrivilegedAddressMonitor
# ---------------------------------------------------------------------------


class PrivilegedAddressMonitor(BaseDetector):
    """
    特权地址监控检测器 — 基于地址标签和高权限调用模式检测私钥泄露攻击。

    检测维度:
      - 已知特权地址检测: Sender 是否在已知管理员/开发者/团队地址列表
      - 特权函数调用检测: 调用的函数签名是否为非标准函数
      - 零投入资金提取检测: tx.value=0 且有大量资金流出
      - 大额资金流向外部检测: 资金是否流向非协议合约的外部地址

    数据源:
      - tx_context.from_address: 交易发送者地址
      - tx_context.to_address: 交易目标合约
      - tx_context.value: 交易的 ETH 输入
      - tx_context.logs: ERC-20 Transfer 事件日志
      - tx_context.input_data: calldata
      - tx_context.extra["privileged_addresses"]: 已知特权地址列表
      - tx_context.extra["known_protocol_addresses"]: 已知协议金库地址列表

    配置:
      - privileged_addresses: 已知特权地址白名单
      - known_protocol_addresses: 已知协议金库地址（降低误报）
      - min_outflow_usd: 最小资金流出 USD 阈值
      - enable_privileged_sender_check: 是否启用特权地址检测
      - enable_function_check: 是否启用特权函数检测
      - enable_outflow_check: 是否启用资金流出检测
    """

    name: str = "privileged_address_monitor"
    label: str = "特权地址监控"
    description: str = (
        "[数据需求: Logs + InputData] "
        "检测私钥泄露类攻击：检查交易 Sender 是否为已知管理员/开发者地址，"
        "检测非标准特权函数调用，检测零投入下的大额资金流向外部地址。"
        "基于地址标签分析，针对管理员私钥泄露攻击（如 Infini $50M 攻击）设计。"
    )
    icon: str = "\U0001f6e1\ufe0f"
    color: str = "#dc2626"

    # ── Pydantic 配置模型 ──
    class ConfigModel(DetectorConfigMixin):
        privileged_addresses: list[str] = Field(
            default=[],
            description="已知特权地址白名单（管理员/开发者/团队地址），匹配时信号增强",
        )
        known_protocol_addresses: list[str] = Field(
            default=[],
            description="已知协议金库地址列表，资金流向这些地址不计为外部流出",
        )
        min_outflow_usd: float = Field(
            default=50000.0, ge=0,
            description="最小资金流出 USD 阈值，低于此值不计为大额流出",
        )
        admin_drain_min_outflow_usd: float = Field(
            default=100000.0, ge=0,
            description="特权地址主动大额提取的强化阈值",
        )
        enable_privileged_sender_check: bool = Field(
            default=True,
            description="是否启用特权地址检测：Sender 是否在已知特权地址列表中",
        )
        enable_function_check: bool = Field(
            default=True,
            description="是否启用特权函数调用检测：调用是否为非标准函数",
        )
        enable_outflow_check: bool = Field(
            default=True,
            description="是否启用资金流出检测：检测大额资金流向外部地址",
        )

    # ── Pydantic 输出模型 ──
    OutputModel: type = PrivilegedAddressOutput

    async def process(self, tx_context: TransactionContext) -> PrivilegedAddressOutput:
        chain_id = tx_context.chain_id or 1
        from_address = tx_context.from_address or ""
        input_data = tx_context.input_data or ""
        tx_value_wei = _hex_to_int(tx_context.value or 0)

        if not from_address:
            return PrivilegedAddressOutput(
                score=0.0, passed=True, severity="UNKNOWN", labels=[],
                detection={"reason": "no from_address available"},
                logs=["无 from_address 数据，跳过特权地址检测"],
            )

        # ── 读取配置和上下文 ──
        privileged_addrs: list[str] = (
            self.config.get("privileged_addresses", [])
            or tx_context.get_extra("privileged_addresses", [])
        )
        protocol_addrs: list[str] = (
            self.config.get("known_protocol_addresses", [])
            or tx_context.get_extra("known_protocol_addresses", [])
        )
        min_outflow = self.config.get("min_outflow_usd", 50000.0)
        privileged_addr_set = {a.lower() for a in privileged_addrs}
        protocol_addr_set = {a.lower() for a in protocol_addrs}
        role_addresses = {
            addr.lower()
            for addr in (tx_context.get_extra("role_addresses") or tx_context.extra.get("role_addresses") or [])
            if isinstance(addr, str) and addr.startswith("0x")
        }
        control_addresses = {
            addr.lower()
            for addr in (tx_context.get_extra("control_addresses") or tx_context.extra.get("control_addresses") or [])
            if isinstance(addr, str) and addr.startswith("0x")
        }
        sender_is_controlled = from_address.lower() in role_addresses or from_address.lower() in control_addresses

        # ── 各项检测 ──
        signals: list[str] = []
        total_score = 0.0
        detection_data: dict[str, Any] = {}
        scoring_logs: list[str] = []
        has_zero_input = tx_value_wei == 0

        # Feature A-1: 已知特权地址检测
        sender_score = 0.0
        sender_details: dict[str, Any] = {"detected": False}
        if self.config.get("enable_privileged_sender_check", True) and privileged_addrs:
            sender_score, sender_details = detect_privileged_sender(
                from_address=from_address,
                privileged_addresses=privileged_addrs,
            )
            if sender_score > 0:
                signals.append("PRIVILEGED_SENDER")
                detection_data["privileged_sender"] = sender_details
                scoring_logs.append(
                    f"特权地址检测: 评分+{sender_score:.0f}, "
                    f"Sender {from_address[:10]}... 在已知特权地址列表中"
                )

        if not privileged_addrs:
            scoring_logs.append("特权地址检测: 未配置特权地址列表，跳过")
        elif sender_is_controlled:
            detection_data["control_path_sender"] = {
                "detected": True,
                "sender": from_address,
                "sources": [
                    source for source, matched in (
                        ("role_addresses", from_address.lower() in role_addresses),
                        ("control_addresses", from_address.lower() in control_addresses),
                    ) if matched
                ],
            }
            signals.append("CONTROL_PATH_SENDER")
            scoring_logs.append("控制路径检测: Sender 命中 role/control 地址")

        # Feature A-2: 特权函数调用检测
        func_score = 0.0
        func_details: dict[str, Any] = {"detected": False}
        if self.config.get("enable_function_check", True) and input_data:
            known_func_names = tx_context.get_extra("function_names", {})
            func_score, func_details = detect_privileged_function_call(
                input_data=input_data,
                known_function_names=known_func_names,
            )
            if func_score > 0:
                scoring_logs.append(
                    f"特权函数检测: 评分+{func_score:.0f}, "
                    f"选择器={func_details.get('selector', '')}, "
                    f"函数={func_details.get('function_name', 'unknown')}"
                )

        # 大额资金流出检测
        outflow_score = 0.0
        outflow_details: list[dict] = []
        total_outflow_usd = 0.0
        external_flow = False

        if self.config.get("enable_outflow_check", True):
            outflow_score, outflow_details, total_outflow_usd = detect_large_fund_outflow(
                from_address=from_address,
                logs=tx_context.logs or [],
                chain_id=chain_id,
                min_outflow_usd=min_outflow,
                known_protocol_addresses=protocol_addrs,
            )
            if outflow_score > 0 and outflow_details:
                signals.append("LARGE_FUND_OUTFLOW")
                detection_data["fund_outflows"] = outflow_details[:10]
                detection_data["total_outflow_usd"] = round(total_outflow_usd, 2)
                scoring_logs.append(
                    f"资金流出检测: {len(outflow_details)} 笔大额流出, "
                    f"合计 ${total_outflow_usd:,.2f}"
                )

                sender_lower = from_address.lower()
                external_outflows = []
                protocol_outflows = []
                for o in outflow_details:
                    target = o["to"].lower()
                    if target in protocol_addr_set or target == sender_lower:
                        protocol_outflows.append(o)
                    else:
                        external_outflows.append(o)

                external_flow = bool(external_outflows)
                if external_flow:
                    signals.append("FUNDS_TO_EXTERNAL")
                    scoring_logs.append("资金流向外部地址: 强信号")

                if sender_score > 0 and external_flow:
                    admin_drain_threshold = self.config.get("admin_drain_min_outflow_usd", 100000.0)
                    if total_outflow_usd >= admin_drain_threshold:
                        total_score += 10.0
                        signals.append("PRIVILEGED_LARGE_WITHDRAW")
                        detection_data["privileged_large_withdraw"] = {
                            "detected": True,
                            "total_outflow_usd": round(total_outflow_usd, 2),
                            "threshold_usd": round(admin_drain_threshold, 2),
                            "external_outflow_count": len(external_outflows),
                        }
                        scoring_logs.append(
                            f"特权地址主动大额提取加分+10: 总外流 ${total_outflow_usd:,.2f}"
                        )

                detection_data["outflow_breakdown"] = {
                    "external_count": len(external_outflows),
                    "protocol_count": len(protocol_outflows),
                    "external_targets": sorted({item["to"].lower() for item in external_outflows})[:10],
                    "protocol_targets": sorted({item["to"].lower() for item in protocol_outflows})[:10],
                }

        # ── 组合评分 ──
        scoring_logs.insert(
            0,
            f"原始评分: sender={sender_score:.0f} + function={func_score:.0f} + outflow={outflow_score:.0f}"
        )

        total_score += sender_score + outflow_score
        function_boost_allowed = sender_score > 0 or outflow_score > 0 or sender_is_controlled or not privileged_addrs
        if func_score > 0:
            detection_data["privileged_function"] = func_details
            if function_boost_allowed:
                signals.append("PRIVILEGED_FUNCTION_CALL")
                total_score += func_score
            else:
                scoring_logs.append("忽略孤立未知函数: 未与特权身份或资金流出联动")
        elif func_score > 0:
            scoring_logs.append("忽略孤立未知函数: 未与特权身份或资金流出联动")

        # 零投入加分（仅当有资金流出时）
        if has_zero_input and outflow_score > 0:
            total_score += 15.0
            signals.append("ZERO_INPUT_EXTRACTION")
            scoring_logs.append("零投入加分+15: tx.value=0 且有资金流出")

        # 特权地址 + 资金流向外部 → 私钥泄露强信号
        if sender_score > 0 and external_flow:
            total_score += 25.0
            signals.append("ADMIN_TO_EXTERNAL_DRAIN")
            scoring_logs.append("组合加分+25: 特权地址 + 资金流向外部(私钥泄露强信号)")

        # 特权函数 + 资金流出 → 高权限调用 + 资金提取
        if func_score > 0 and outflow_score > 0:
            total_score += 15.0
            signals.append("PRIVILEGED_DRAIN")
            scoring_logs.append("组合加分+15: 特权函数 + 资金流出(权限滥用)")

        # 全部命中 → 极强信号
        all_hit = sender_score > 0 and func_score > 0 and outflow_score > 0
        if all_hit:
            total_score += 10.0
            signals.append("FULL_PRIVILEGED_ATTACK_PATTERN")
            scoring_logs.append("组合加分+10: 全部信号命中(确定攻击)")

        total_score = max(0.0, min(100.0, total_score))

        # ── 生成结果 ──
        threshold = self.config.get("threshold", 50.0)
        passed = total_score >= threshold
        labels = signals if passed else []

        scoring_logs.append(
            f"最终评分={total_score:.1f}, 阈值={threshold}, "
            f"passed={passed}, severity={score_to_severity(total_score)}"
        )

        detection_data["total_score"] = round(total_score, 2)
        detection_data["signal_scores"] = {
            "privileged_sender": round(sender_score, 2),
            "privileged_function": round(func_score, 2),
            "fund_outflow": round(outflow_score, 2),
        }
        detection_data["signals"] = signals
        detection_data["has_zero_input"] = has_zero_input
        detection_data["has_external_flow"] = external_flow
        detection_data["total_outflow_usd"] = round(total_outflow_usd, 2)

        return PrivilegedAddressOutput(
            score=total_score,
            passed=passed,
            severity=score_to_severity(total_score),
            labels=labels,
            detection=detection_data,
            logs=scoring_logs,
        )


NodeRegistry.register(PrivilegedAddressMonitor)
