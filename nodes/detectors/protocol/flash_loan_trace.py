"""
闪电贷 Trace 增强检测器

基于 eth_trace 调用栈分析，检测闪电贷攻击模式。
相比现有的 FlashLoanDetector（仅基于 to_address + input_data 方法签名），
此检测器通过完整的调用栈分析，可识别:
  - 闪电贷借款 → 操纵 → 还款的完整调用链
  - 闪电贷回调函数（executeOperation 等）的调用
  - 跨合约的闪电贷资金流转路径
  - 复杂的闪电贷组合攻击

前置依赖: ETH-Trace Provider (@require("eth_trace"))
"""

from __future__ import annotations

import logging
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
from nodes.detectors.protocol.signatures import (
    FLASH_LOAN_ATTACK_SEQUENCE,
    FLASH_LOAN_CALLBACK_SIGNATURES,
    FLASH_LOAN_EXPLOIT_SIGNATURES,
    FLASH_LOAN_SIGNATURES,
    lookup_signature,
)
from nodes.models import TransactionContext
from nodes.providers.eth_trace import EthTraceData

KNOWN_FLASH_LOAN_PROTOCOLS: set[str] = {
    "0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9",
}

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 攻击模式定义
# ---------------------------------------------------------------------------

ATTACK_PATTERNS: list[AttackPattern] = [
    AttackPattern(
        name="flash_loan_full_attack",
        description="闪电贷完整攻击: 借款→操纵→还款",
        function_selectors=list(FLASH_LOAN_SIGNATURES.keys()),
        call_sequence=FLASH_LOAN_ATTACK_SEQUENCE,
        score_weight=90.0,
    ),
    AttackPattern(
        name="flash_loan_callback",
        description="闪电贷回调函数被调用，表明攻击者在回调中执行操作",
        function_selectors=list(FLASH_LOAN_CALLBACK_SIGNATURES.keys()),
        score_weight=70.0,
    ),
    AttackPattern(
        name="flash_loan_exploit_action",
        description="闪电贷回调后出现借贷/清算/转账等利用动作",
        function_selectors=list(FLASH_LOAN_EXPLOIT_SIGNATURES.keys()),
        score_weight=55.0,
    ),
    AttackPattern(
        name="flash_loan_borrow_only",
        description="仅检测到闪电贷借款调用",
        function_selectors=list(FLASH_LOAN_SIGNATURES.keys()),
        score_weight=40.0,
    ),
]


class FlashLoanTraceDetector(BaseProtocolAttackDetector):
    """
    闪电贷 Trace 增强检测器 — 基于 eth_trace 调用栈的闪电贷攻击检测。

    检测能力:
    - 闪电贷借款→操纵→还款的完整调用链
    - 闪电贷回调函数调用
    - 大额资金流转（value 字段分析）
    - 跨合约闪电贷组合攻击

    评分策略:
    - 完整攻击链（borrow→callback→repay）: 90+
    - 闪电贷回调被调用: 70+
    - 仅闪电贷借款: 40
    - 交易金额异常大: +10~20
    """

    name: str = "flash_loan_trace_detector"
    label: str = "闪电贷Trace检测"
    description: str = "[数据需求: Trace(必需)] 基于ETH调用栈分析闪电贷攻击：识别借款→操纵→还款完整链路，检测闪电贷回调函数和跨合约资金流转"
    icon: str = "\u26a1"
    color: str = "#dc2626"

    ATTACK_PATTERNS = ATTACK_PATTERNS
    ATTACK_TYPE_LABEL = "flash_loan_attack"

    class ConfigModel(BaseProtocolAttackDetector.ConfigModel):
        large_value_threshold_wei: int = Field(
            default=50 * 10**18,
            description="大额闪电贷阈值（wei），默认 50 ETH",
        )
        exploit_window_size: int = Field(
            default=4,
            ge=1,
            description="闪电贷回调后在多少个调用内出现利用动作视为可疑",
        )

    async def analyze_call_stack(
        self,
        call_stack: list[CallStackEntry],
        trace_data: EthTraceData,
        tx_context: TransactionContext,
    ) -> DetectorOutputMixin:
        """
        闪电贷调用栈分析流程:
        1. 执行模式匹配
        2. 分析资金流转
        3. 计算综合评分
        """
        # 1. 模式匹配
        matches = self._match_patterns(call_stack)

        # 2. 资金流转分析
        large_value_threshold = self.config.get("large_value_threshold_wei", 50 * 10**18)
        large_value_calls = self._find_large_value_calls(call_stack, large_value_threshold)

        # 3. 回调后利用动作检测
        exploit_window_size = self.config.get("exploit_window_size", 4)
        exploit_after_callback = self._check_callback_before_exploit(call_stack, exploit_window_size)
        exploit_actions = self._collect_exploit_actions(call_stack)

        # 4. 调用深度分析
        max_depth = max((e.depth for e in call_stack), default=0)
        has_delegatecall = trace_data.has_delegatecall

        # 5. 计算评分
        score = self._calculate_score(matches, large_value_calls, exploit_after_callback, max_depth)

        # 6. 构建检测结果
        labels = self._build_labels(matches, large_value_calls, exploit_after_callback)
        detection = self._build_detection(
            call_stack, matches, large_value_calls, exploit_actions,
            exploit_after_callback, max_depth, has_delegatecall, trace_data,
        )

        threshold = self.config.get("threshold", 50.0)
        return DetectorOutputMixin(
            score=score,
            passed=score >= threshold,
            severity=score_to_severity(score),
            labels=labels,
            detection=detection,
        )

    def _find_large_value_calls(
        self,
        call_stack: list[CallStackEntry],
        threshold: int,
    ) -> list[CallStackEntry]:
        """查找大额资金调用"""
        result = []
        for entry in call_stack:
            try:
                value = int(entry.value, 16) if entry.value.startswith("0x") else int(entry.value)
                if value >= threshold:
                    result.append(entry)
            except (ValueError, AttributeError):
                continue
        return result

    def _check_callback_before_exploit(
        self,
        call_stack: list[CallStackEntry],
        exploit_window_size: int,
    ) -> bool:
        callback_selectors = set(FLASH_LOAN_CALLBACK_SIGNATURES.keys())
        exploit_selectors = set(FLASH_LOAN_EXPLOIT_SIGNATURES.keys())
        for index, entry in enumerate(call_stack):
            if entry.function_selector not in callback_selectors:
                continue
            for later_entry in call_stack[index + 1:index + 1 + exploit_window_size]:
                if later_entry.function_selector in exploit_selectors:
                    return True
        return False

    def _collect_exploit_actions(self, call_stack: list[CallStackEntry]) -> list[dict[str, Any]]:
        exploit_selectors = set(FLASH_LOAN_EXPLOIT_SIGNATURES.keys())
        actions = []
        for entry in call_stack:
            if entry.function_selector not in exploit_selectors:
                continue
            actions.append({
                "depth": entry.depth,
                "selector": entry.function_selector,
                "signature": lookup_signature(entry.function_selector) or "",
                "to": entry.to_addr,
            })
        return actions

    def _calculate_score(
        self,
        matches: list[PatternMatch],
        large_value_calls: list[CallStackEntry],
        exploit_after_callback: bool,
        max_depth: int,
    ) -> float:
        """计算综合评分"""
        if not matches and not exploit_after_callback:
            if large_value_calls:
                return 25.0
            return 0.0

        max_match_score = max((m.score_contribution for m in matches), default=0.0)
        has_full_sequence = any(m.sequence_matched for m in matches)
        if has_full_sequence:
            max_match_score = min(100.0, max_match_score * 1.2)

        if exploit_after_callback:
            max_match_score = max(max_match_score, 80.0)

        large_value_bonus = min(20.0, len(large_value_calls) * 10.0)
        depth_bonus = min(10.0, max_depth * 1.0)
        exploit_bonus = 15.0 if exploit_after_callback else 0.0

        return min(100.0, max_match_score + large_value_bonus + depth_bonus + exploit_bonus)

    def _build_labels(
        self,
        matches: list[PatternMatch],
        large_value_calls: list[CallStackEntry],
        exploit_after_callback: bool,
    ) -> list[str]:
        """构建检测标签"""
        labels = []
        for m in matches:
            if m.sequence_matched:
                labels.append(f"FLASH_LOAN_SEQUENCE:{m.pattern_name}")
            elif m.matched_selectors:
                for sel in m.matched_selectors:
                    sig = lookup_signature(sel)
                    labels.append(f"FLASH_LOAN_SIG:{sig or sel}")
        if large_value_calls:
            labels.append(f"FLASH_LOAN_LARGE_VALUE:{len(large_value_calls)}")
        if exploit_after_callback:
            labels.append("FLASH_LOAN_CALLBACK_BEFORE_EXPLOIT")
        return labels

    def _build_detection(
        self,
        call_stack: list[CallStackEntry],
        matches: list[PatternMatch],
        large_value_calls: list[CallStackEntry],
        exploit_actions: list[dict[str, Any]],
        exploit_after_callback: bool,
        max_depth: int,
        has_delegatecall: bool,
        trace_data: EthTraceData,
    ) -> dict[str, Any]:
        """构建检测结果字典"""
        # 调用栈摘要（仅保留关键字段）
        call_stack_summary = [
            {
                "depth": e.depth,
                "from": e.from_addr[:10] + "..." if e.from_addr else "",
                "to": e.to_addr[:10] + "..." if e.to_addr else "",
                "selector": e.function_selector,
                "signature": lookup_signature(e.function_selector) or "",
                "call_type": e.call_type,
                "value_wei": e.value,
            }
            for e in call_stack[:30]  # 限制输出长度
        ]

        return {
            "attack_type": self.ATTACK_TYPE_LABEL,
            "trace_count": trace_data.trace_count,
            "max_depth": max_depth,
            "has_delegatecall": has_delegatecall,
            "call_stack_size": len(call_stack),
            "pattern_matches": [m.model_dump() for m in matches],
            "large_value_calls": len(large_value_calls),
            "features": {
                "callback_before_exploit": exploit_after_callback,
            },
            "exploit_actions": exploit_actions,
            "call_stack_summary": call_stack_summary,
        }


class LegacyFlashLoanDetector(FlashLoanTraceDetector):
    name: str = "flash_loan_detector"
    label: str = "闪电贷检测"
    description: str = "基于交易目标、方法签名和大额 value 的兼容闪电贷检测器。"

    async def process(self, tx_context: TransactionContext) -> DetectorOutputMixin:
        trace_output = await super().process(tx_context)
        if trace_output.score > 0 or tx_context.get_extra("eth_trace"):
            return trace_output

        selector = (tx_context.input_data or "")[:10].lower()
        to_address = (tx_context.to_address or "").lower()
        value = tx_context.value or 0
        large_threshold_wei = self.config.get("large_value_threshold_wei")
        if large_threshold_wei is None:
            large_threshold_usd = self.config.get("large_flash_loan_threshold_usd", 100_000.0)
            native_price = self.config.get("chain_id_to_native_token_price", {}).get(tx_context.chain_id)
            if native_price is None:
                native_price = self.token_price_instance.get_price(tx_context.chain_id, "") or 0.0
            large_threshold_wei = int((large_threshold_usd / native_price) * 10**18) if native_price else 50 * 10**18
        is_large = value >= large_threshold_wei
        if selector not in FLASH_LOAN_SIGNATURES and to_address not in KNOWN_FLASH_LOAN_PROTOCOLS and not is_large:
            return trace_output

        score = 70.0 if to_address in KNOWN_FLASH_LOAN_PROTOCOLS else 0.0
        labels = ["FLASH_LOAN"]
        if selector in FLASH_LOAN_SIGNATURES:
            score = max(score, 80.0 if to_address in KNOWN_FLASH_LOAN_PROTOCOLS else 60.0)
        if is_large:
            score = max(score, 95.0 if to_address in KNOWN_FLASH_LOAN_PROTOCOLS or selector in FLASH_LOAN_SIGNATURES else 50.0)
            labels.append("LARGE_FLASH_LOAN_ATTACK")

        detection = {
            "attack_type": "flash_loan_attack",
            "selector": selector,
            "signature": lookup_signature(selector) or "",
            "to_address": to_address,
            "value_wei": value,
            "trace_fallback": True,
        }
        threshold = self.config.get("threshold", 50.0)
        return DetectorOutputMixin(
            score=score,
            passed=score >= threshold,
            severity=score_to_severity(score),
            labels=labels,
            detection=detection,
        )


NodeRegistry.register(LegacyFlashLoanDetector)
NodeRegistry.register(FlashLoanTraceDetector)
