"""
中间合约代理调用检测器 — 基于调用栈和 logs 的间接层分析

检测特征:
  1. 调用链深度分析: trace 调用链深度 > 阈值
  2. to 地址非核心执行方: 交易的 to 地址在 logs 中从未出现为事件发射者
  3. 纯转发层检测: to 地址在调用栈中只出现在第一层，不参与后续逻辑
  4. delegatecall 代理模式: 检测 delegatecall 调用（代理合约模式）
  5. EIP-2771 元交易转发: 检测已知的元交易转发器模式
  6. 资金级联提取模式 (Feature E): 检测 "Sender → Receiver → Strategy → Vault → External" 模式
  7. 策略合约识别: 通过调用链深度分布识别策略/金库合约角色
  8. 资金汇聚检测: 检测从多个底层合约提取到同一顶层地址

前置依赖: ETH-Trace Provider (@require("eth_trace"))
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from typing import Any

from pydantic import Field

from nodes.base import NodeRegistry, score_to_severity
from nodes.detectors.base import DetectorOutputMixin
from nodes.detectors.protocol.base import (
    AttackPattern,
    BaseProtocolAttackDetector,
    CallStackEntry,
    PatternMatch,
)
from nodes.models import TransactionContext
from nodes.providers.eth_trace import EthTraceData

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 已知的转发器/代理函数签名
# ---------------------------------------------------------------------------

FORWARDER_SIGNATURES: dict[str, str] = {
    # EIP-2771 Meta-Transaction Forwarder
    "0x5a2e7332": "execute(address,uint256,bytes)",
    "0x5b0c4dff": "execute(address,uint256,bytes,address)",  # 通用 execute
    # GSN Forwarder
    "0x3a42c3b9": "registerRequestType(string,string)",
    "0x3a5c0755": "executeCall(address,uint256,bytes)",
    # 通用 proxy/relay
    "0x42842e0e": "safeTransferFrom(address,address,uint256)",
    "0xd0def521": "relayCall(uint256,bytes,bytes)",
}

# EIP-2771 相关: isTrustedForwarder / getChainId
META_TX_INDICATORS: dict[str, str] = {
    "0x572b6c05": "isTrustedForwarder(address)",
    "0x8004d0f4": "getChainId()",
}

# ERC-4626 / 策略相关函数选择器（辅助策略合约识别）
STRATEGY_FUNCTION_SELECTORS: set[str] = {
    "0x4cdad506",  # previewRedeem(uint256)
    "0xba087652",  # redeem(uint256,address,address)
    "0xb460af94",  # withdraw(uint256,address,address)
    "0x07a2d13a",  # deposit(uint256,address)
    "0x6e553f65",  # deposit(uint256,address)
    "0x38d52e0f",  # asset()
    "0x7020d892",  # convertToAssets(uint256)
    "0xc6e6f592",  # convertToShares(uint256)
    "0x3ba0b9a9",  # maxRedeem(address)
    "0x0355fca9",  # maxWithdraw(address)
    "0xce96cb77",  # maxWithdraw(address) [Vault-facing]
    "0xd905777e",  # maxDeposit(address)
    "0xdd62ed3e",  # allowance(address,address)
}


class IndirectionLayerDetector(BaseProtocolAttackDetector):
    """
    中间合约代理调用检测器 — 检测交易中的间接调用层。

    检测能力:
    - 调用链深度异常（多级代理调用）
    - 交易 to 地址与核心执行合约不一致
    - delegatecall 代理模式
    - 已知转发器函数签名匹配
    - to 地址在 logs 中从未出现（纯转发层）
    - [特征 E] 策略合约角色识别（ERC-4626 函数签名匹配）
    - [特征 E] 资金级联提取模式（Sender→Receiver→Strategy→Vault→External）
    - [特征 E] 资金汇聚检测（多底层合约 → 同一顶层接收者）

    评分策略:
    - 高深度 + to 非核心执行: 60+
    - delegatecall 代理模式: 50+
    - 已知转发器签名: 40+
    - to 地址纯转发: 35+
    - 策略合约识别: +15
    - 级联提取模式: +20
    - 资金汇聚检测: +15
    - 组合: 多特征联动加分（策略+级联=+15, 级联+汇聚=+10 等）
    """

    name: str = "indirection_layer_detector"
    label: str = "中间合约代理检测"
    description: str = (
        "[数据需求: Trace(必需)] "
        "检测攻击者通过中间合约代理调用隐藏真实目标："
        "调用链深度异常、delegatecall代理模式、已知转发器签名、"
        "to地址纯转发层检测。增强特征E：策略合约识别、"
        "资金级联提取模式(Sender→Receiver→Strategy→Vault→External)、"
        "资金汇聚检测(多底层合约→同一接收者)。辅助确认攻击行为。"
    )
    icon: str = "\U0001f50d"
    color: str = "#f59e0b"

    ATTACK_TYPE_LABEL = "indirection_layer"

    # 不使用模式匹配框架（本检测器不依赖函数签名模式列表）
    ATTACK_PATTERNS: list[AttackPattern] = []

    class ConfigModel(BaseProtocolAttackDetector.ConfigModel):
        min_call_depth: int = Field(
            default=3, ge=1,
            description="最小调用深度阈值，超过此值视为有间接层",
        )
        check_to_address_in_logs: bool = Field(
            default=True,
            description="是否检查交易的 to 地址在 logs 中是否出现",
        )
        # ── 特征 E: 资金级联提取检测 ──
        enable_cascade_extraction_check: bool = Field(
            default=True,
            description="是否启用资金级联提取模式检测 (Feature E)",
        )
        cascade_min_depth: int = Field(
            default=3, ge=2,
            description="级联提取最小深度阈值，调用链深度 >= 此值视为级联模式",
        )
        cascade_min_layer_count: int = Field(
            default=3, ge=2,
            description="级联提取最少层数，不同深度层 >= 此值视为有级联",
        )
        enable_strategy_contract_check: bool = Field(
            default=True,
            description="是否启用策略合约角色识别",
        )
        enable_fund_convergence_check: bool = Field(
            default=True,
            description="是否启用资金汇聚检测（多底层合约资金流向同一地址）",
        )

    async def analyze_call_stack(
        self,
        call_stack: list[CallStackEntry],
        trace_data: EthTraceData,
        tx_context: TransactionContext,
    ) -> DetectorOutputMixin:
        """
        中间合约代理调用分析（增强版 — 含特征 E: 多层策略提取）:
        1. 调用链深度分析
        2. to 地址在调用栈中的角色分析
        3. 核心执行合约识别
        4. delegatecall 检测
        5. 已知转发器签名匹配
        6. to 地址在 logs 中是否出现
        7. [特征 E] 策略合约角色识别
        8. [特征 E] 资金级联提取模式检测
        9. [特征 E] 资金汇聚检测
        """
        scoring_logs: list[str] = []
        issues: list[str] = []
        score = 0.0
        detection: dict[str, Any] = {
            "attack_type": self.ATTACK_TYPE_LABEL,
            "trace_count": trace_data.trace_count,
            "max_depth": trace_data.max_depth,
            "has_delegatecall": trace_data.has_delegatecall,
        }

        to_addr = (tx_context.to_address or "").lower()
        from_addr = (tx_context.from_address or "").lower()

        # ── 1. 调用链深度分析 ──
        min_call_depth = self.config.get("min_call_depth", 3)
        max_depth = trace_data.max_depth

        if max_depth >= min_call_depth:
            old_score = score
            score += 25.0
            issues.append("DEEP_CALL_CHAIN")
            scoring_logs.append(
                f"调用链深度异常: max_depth={max_depth} >= {min_call_depth}, "
                f"评分 {old_score}→{score}"
            )
        else:
            scoring_logs.append(f"调用链深度正常: max_depth={max_depth} < {min_call_depth}")

        # ── 2. to 地址在调用栈中的角色分析 ──
        # 检查 to 地址是否只在第一层出现（纯转发层）
        to_addr_depths = [e.depth for e in call_stack if e.to_addr == to_addr]
        to_addr_as_from = [e for e in call_stack if e.from_addr == to_addr]
        to_addr_only_top = len(to_addr_depths) > 0 and all(d <= 1 for d in to_addr_depths)

        detection["to_addr"] = to_addr
        detection["to_addr_depths"] = to_addr_depths
        detection["to_addr_as_caller"] = len(to_addr_as_from)

        if to_addr_only_top and len(to_addr_as_from) > 0:
            # to 地址只在顶层被调用，但作为调用方发起了后续调用
            # 这说明它是中间转发层
            old_score = score
            score += 20.0
            issues.append("TO_ADDR_IS_FORWARDER")
            scoring_logs.append(
                f"to地址纯转发: {to_addr[:10]}... 只在depth<=1出现, "
                f"但作为from发起了{len(to_addr_as_from)}个调用, "
                f"评分 {old_score}→{score}"
            )

        # ── 3. 找出核心执行合约（调用栈中最深的 to 地址） ──
        if call_stack:
            deepest = max(call_stack, key=lambda e: e.depth)
            core_contract = deepest.to_addr
            detection["core_execution_contract"] = core_contract

            if core_contract != to_addr and core_contract != from_addr:
                old_score = score
                score += 15.0
                issues.append("CORE_CONTRACT_MISMATCH")
                scoring_logs.append(
                    f"核心执行合约不等于to地址: core={core_contract[:10]}... "
                    f"!= to={to_addr[:10]}..., 评分 {old_score}→{score}"
                )

        # ── 4. delegatecall 检测 ──
        if trace_data.has_delegatecall:
            old_score = score
            score += 20.0
            issues.append("DELEGATECALL_USED")
            scoring_logs.append(
                f"delegatecall代理模式: 检测到delegatecall, "
                f"评分 {old_score}→{score}"
            )

        # ── 5. 已知转发器签名匹配 ──
        matched_forwarder_selectors: list[str] = []
        for entry in call_stack:
            selector = entry.function_selector
            if selector in FORWARDER_SIGNATURES:
                matched_forwarder_selectors.append(selector)
                scoring_logs.append(
                    f"已知转发器签名: {selector}={FORWARDER_SIGNATURES[selector]}, "
                    f"from={entry.from_addr[:10]}..., to={entry.to_addr[:10]}..."
                )

        if matched_forwarder_selectors:
            old_score = score
            score += 25.0
            issues.append("KNOWN_FORWARDER_SIGNATURE")
            scoring_logs.append(
                f"已知转发器签名匹配: {len(matched_forwarder_selectors)}个, "
                f"评分 {old_score}→{score}"
            )

        # 元交易指标（辅助判断，不单独加分）
        meta_tx_matches: list[str] = []
        for entry in call_stack:
            selector = entry.function_selector
            if selector in META_TX_INDICATORS:
                meta_tx_matches.append(selector)

        if meta_tx_matches:
            detection["meta_tx_indicators"] = meta_tx_matches
            scoring_logs.append(f"元交易指标: {len(meta_tx_matches)}个")

        # ── 6. to 地址在 logs 中是否出现（无需 trace，辅助判断） ──
        if self.config.get("check_to_address_in_logs", True) and tx_context.logs:
            log_emitters = {
                (log.get("address") or "").lower()
                for log in tx_context.logs
            }
            to_in_logs = to_addr in log_emitters
            detection["to_addr_in_log_emitters"] = to_in_logs

            if not to_in_logs:
                old_score = score
                score += 15.0
                issues.append("TO_ADDR_NOT_IN_LOGS")
                scoring_logs.append(
                    f"to地址不在logs事件发射者中: {to_addr[:10]}... "
                    f"可能是纯转发层, 评分 {old_score}→{score}"
                )
            else:
                scoring_logs.append(f"to地址在logs中出现了，不是纯转发层")

        # ═══════════════════════════════════════════════════════════════════
        # 特征 E: 资金级联提取检测（Multi-Layer Strategy Drain）
        # ═══════════════════════════════════════════════════════════════════

        # ── 7. 策略合约角色识别 ──
        strategy_contracts: list[str] = []
        if self.config.get("enable_strategy_contract_check", True):
            for entry in call_stack:
                if entry.function_selector in STRATEGY_FUNCTION_SELECTORS:
                    if entry.to_addr not in strategy_contracts:
                        strategy_contracts.append(entry.to_addr)
                        scoring_logs.append(
                            f"策略合约识别: {entry.to_addr[:10]}... "
                            f"调用策略函数 {entry.function_selector}"
                        )

            if strategy_contracts:
                old_score = score
                score += 15.0
                issues.append("STRATEGY_CONTRACT_IDENTIFIED")
                detection["strategy_contracts"] = strategy_contracts
                scoring_logs.append(
                    f"策略合约识别: 检测到{len(strategy_contracts)}个策略合约, "
                    f"评分 {old_score}→{score}"
                )

        # ── 8. 资金级联提取模式检测 ──
        cascade_detected = False
        cascade_info: dict[str, Any] = {}
        if self.config.get("enable_cascade_extraction_check", True):
            cascade_min_depth = self.config.get("cascade_min_depth", 3)
            cascade_min_layers = self.config.get("cascade_min_layer_count", 3)

            # 按深度分组各层的 to_addr（去重）
            depth_contracts: dict[int, set[str]] = defaultdict(set)
            for entry in call_stack:
                if entry.call_type in ("call", "delegatecall"):
                    depth_contracts[entry.depth].add(entry.to_addr)

            depth_layer_count = len(depth_contracts)
            max_call_depth = max(depth_contracts.keys()) if depth_contracts else 0

            # 级联模式判定: 调用链深度 >= 阈值 AND 不同深度层数 >= 最少层数
            if max_call_depth >= cascade_min_depth and depth_layer_count >= cascade_min_layers:
                # 构建层分布摘要
                layer_summary: dict[int, list[str]] = {
                    d: sorted(list(addrs))[:5]  # 每层最多 5 个合约
                    for d, addrs in sorted(depth_contracts.items())
                }

                # 检测资金流向方向: "Sender → 顶层Receiver → 中层Strategy → 底层Vault"
                # 特征: 深度越大越接近底层协议
                cascade_detected = True
                cascade_info = {
                    "max_depth": max_call_depth,
                    "depth_layer_count": depth_layer_count,
                    "layer_contracts": layer_summary,
                    "total_unique_contracts": len(set(
                        addr for addrs in depth_contracts.values() for addr in addrs
                    )),
                }

                old_score = score
                score += 20.0
                issues.append("FUND_CASCADE_EXTRACTION")
                detection["cascade_extraction"] = cascade_info
                scoring_logs.append(
                    f"资金级联提取模式: max_depth={max_call_depth}, "
                    f"layer_count={depth_layer_count}, "
                    f"评分 {old_score}→{score}"
                )

        # ── 9. 资金汇聚检测（多底层合约 → 同一顶层接收者） ──
        convergence_detected = False
        convergence_info: dict[str, Any] = {}
        if self.config.get("enable_fund_convergence_check", True) and call_stack:
            # 找出所有深度 >= 1 的 to 地址（中层/底层合约）
            # 以及深度 0 的 from/to（顶层接收者）
            depth_to_addrs: dict[int, list[str]] = defaultdict(list)
            for entry in call_stack:
                depth_to_addrs[entry.depth].append(entry.to_addr)

            # 统计每个顶层合约被多少个不同底层合约调用
            # 即: 检查深度 n 的 from_addr 在深度 n-1 中出现的次数
            # 简化版: 找出深度 >= 2 的所有 to_addr，看它们是否都汇聚到同一个深度 0-1 的 from_addr
            deep_contracts: set[str] = set()
            top_callers: set[str] = set()

            for entry in call_stack:
                if entry.depth >= 2:
                    deep_contracts.add(entry.to_addr)
                if entry.depth <= 1:
                    top_callers.add(entry.to_addr)

            if len(deep_contracts) >= 2 and len(top_callers) > 0:
                # 检查有多少个底层合约被同一个顶层/中层合约调用
                # 按 from_addr 分组底层合约调用
                from_to_deep: dict[str, list[str]] = defaultdict(list)
                for entry in call_stack:
                    if entry.depth >= 2 and entry.from_addr:
                        from_to_deep[entry.from_addr].append(entry.to_addr)

                convergence_patterns: list[dict] = []
                for caller, callees in from_to_deep.items():
                    unique_callees = list(set(callees))
                    if len(unique_callees) >= 2:
                        convergence_patterns.append({
                            "convergence_address": caller,
                            "underlying_contracts": unique_callees[:10],
                            "underlying_count": len(unique_callees),
                        })

                if convergence_patterns:
                    convergence_detected = True
                    convergence_info = {
                        "total_deep_contracts": len(deep_contracts),
                        "convergence_patterns": convergence_patterns[:5],
                    }

                    old_score = score
                    score += 15.0
                    issues.append("FUND_CONVERGENCE_DETECTED")
                    detection["fund_convergence"] = convergence_info
                    scoring_logs.append(
                        f"资金汇聚检测: {len(convergence_patterns)}个汇聚模式, "
                        f"评分 {old_score}→{score}"
                    )

        # ── 10. 组合加分 ──
        has_deep = "DEEP_CALL_CHAIN" in issues
        has_forwarder = "TO_ADDR_IS_FORWARDER" in issues
        has_mismatch = "CORE_CONTRACT_MISMATCH" in issues
        has_known_sig = "KNOWN_FORWARDER_SIGNATURE" in issues
        has_cascade = "FUND_CASCADE_EXTRACTION" in issues
        has_convergence = "FUND_CONVERGENCE_DETECTED" in issues
        has_strategy = "STRATEGY_CONTRACT_IDENTIFIED" in issues

        if has_deep and has_forwarder:
            old_score = score
            score = min(100.0, score + 10.0)
            issues.append("DEEP_PLUS_FORWARDER")
            scoring_logs.append(f"组合加分+10: 深度+转发, 评分 {old_score}→{score}")

        if has_forwarder and has_known_sig:
            old_score = score
            score = min(100.0, score + 10.0)
            issues.append("FORWARDER_PLUS_KNOWN_SIG")
            scoring_logs.append(f"组合加分+10: 转发+已知签名, 评分 {old_score}→{score}")

        # 特征 E 组合加分
        if has_cascade and has_deep:
            old_score = score
            score = min(100.0, score + 10.0)
            issues.append("CASCADE_PLUS_DEEP")
            scoring_logs.append(f"组合加分+10: 级联提取+深度异常, 评分 {old_score}→{score}")

        if has_cascade and has_convergence:
            old_score = score
            score = min(100.0, score + 10.0)
            issues.append("CASCADE_PLUS_CONVERGENCE")
            scoring_logs.append(f"组合加分+10: 级联提取+资金汇聚, 评分 {old_score}→{score}")

        if has_strategy and has_cascade:
            old_score = score
            score = min(100.0, score + 15.0)
            issues.append("STRATEGY_CASCADE_DRAIN")
            scoring_logs.append(f"组合加分+15: 策略合约+级联提取(多层策略资金提取攻击), 评分 {old_score}→{score}")

        if has_strategy and has_forwarder:
            old_score = score
            score = min(100.0, score + 10.0)
            issues.append("STRATEGY_VIA_FORWARDER")
            scoring_logs.append(f"组合加分+10: 策略合约+转发层, 评分 {old_score}→{score}")

        # ── 11. 构建输出 ──
        detection["issues"] = issues
        detection["call_stack_size"] = len(call_stack)
        detection["matched_forwarder_selectors"] = matched_forwarder_selectors

        # 调用栈摘要（仅保留关键信息）
        detection["call_stack_summary"] = [
            {
                "depth": e.depth,
                "from": e.from_addr[:10] + "..." if e.from_addr else "",
                "to": e.to_addr[:10] + "..." if e.to_addr else "",
                "selector": e.function_selector,
                "call_type": e.call_type,
                "value_wei": e.value,
            }
            for e in call_stack[:30]
        ]

        threshold = self.config.get("threshold", 50.0)
        passed = score >= threshold
        labels = issues if passed else []

        scoring_logs.append(
            f"最终评分={score:.1f}, 阈值={threshold}, "
            f"passed={passed}, severity={score_to_severity(score)}"
        )

        return DetectorOutputMixin(
            score=score,
            passed=passed,
            severity=score_to_severity(score),
            labels=labels,
            detection=detection,
            logs=scoring_logs,
        )


NodeRegistry.register(IndirectionLayerDetector)
