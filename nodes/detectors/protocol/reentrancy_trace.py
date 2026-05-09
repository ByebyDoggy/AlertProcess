from __future__ import annotations

from collections import Counter
from typing import Any

from pydantic import Field

from nodes.base import NodeRegistry, score_to_severity
from nodes.detectors.base import DetectorOutputMixin
from nodes.detectors.protocol.base import AttackPattern, BaseProtocolAttackDetector, CallStackEntry, PatternMatch
from nodes.detectors.protocol.signatures import REENTRANCY_DRAIN_SIGNATURES, lookup_signature
from nodes.models import TransactionContext
from nodes.providers.eth_trace import EthTraceData


REENTRANCY_CALLBACK_PATTERNS: list[AttackPattern] = [
    AttackPattern(
        name="reentrancy_drain_function",
        description="重入常见资金释放函数重复出现在同一调用栈中",
        function_selectors=list(REENTRANCY_DRAIN_SIGNATURES.keys()),
        min_depth=2,
        score_weight=60.0,
    ),
]


class ReentrancyTraceDetector(BaseProtocolAttackDetector):
    name: str = "reentrancy_trace_detector"
    label: str = "重入Trace检测"
    description: str = (
        "[数据需求: Trace(必需)] 基于ETH调用栈识别重入攻击路径："
        "检测同一合约被重复回调、同一资金释放函数递归触发、以及 call stack 中的回边模式。"
    )
    icon: str = "↩️"
    color: str = "#ef4444"

    ATTACK_PATTERNS = REENTRANCY_CALLBACK_PATTERNS
    ATTACK_TYPE_LABEL = "reentrancy_trace"

    class ConfigModel(BaseProtocolAttackDetector.ConfigModel):
        repeated_target_threshold: int = Field(default=2, ge=2, description="同一目标合约重复出现的最小次数")
        repeated_selector_threshold: int = Field(default=2, ge=2, description="同一释放函数重复出现的最小次数")
        recursion_window_size: int = Field(default=6, ge=2, description="向后检查递归回边的调用窗口大小")

    async def analyze_call_stack(
        self,
        call_stack: list[CallStackEntry],
        trace_data: EthTraceData,
        tx_context: TransactionContext,
    ) -> DetectorOutputMixin:
        matches = self._match_patterns(call_stack)
        repeated_targets = self._find_repeated_targets(call_stack)
        repeated_drains = self._find_repeated_drain_selectors(call_stack)
        callback_edges = self._find_callback_edges(call_stack)
        max_depth = max((entry.depth for entry in call_stack), default=0)

        score = self._calculate_score(matches, repeated_targets, repeated_drains, callback_edges, max_depth)
        labels = self._build_labels(matches, repeated_targets, repeated_drains, callback_edges)
        detection = self._build_detection(
            call_stack,
            matches,
            repeated_targets,
            repeated_drains,
            callback_edges,
            max_depth,
            trace_data,
        )

        threshold = self.config.get("threshold", 50.0)
        return DetectorOutputMixin(
            score=score,
            passed=score >= threshold,
            severity=score_to_severity(score),
            labels=labels,
            detection=detection,
        )

    def _find_repeated_targets(self, call_stack: list[CallStackEntry]) -> list[dict[str, Any]]:
        threshold = self.config.get("repeated_target_threshold", 2)
        counter = Counter(entry.to_addr for entry in call_stack if entry.to_addr)
        return [
            {"address": address, "count": count}
            for address, count in counter.most_common()
            if count >= threshold
        ]

    def _find_repeated_drain_selectors(self, call_stack: list[CallStackEntry]) -> list[dict[str, Any]]:
        threshold = self.config.get("repeated_selector_threshold", 2)
        drain_selectors = set(REENTRANCY_DRAIN_SIGNATURES.keys())
        by_target: dict[str, list[CallStackEntry]] = {}
        for entry in call_stack:
            if entry.function_selector not in drain_selectors or not entry.to_addr:
                continue
            by_target.setdefault(entry.to_addr, []).append(entry)

        repeated: list[dict[str, Any]] = []
        for target, entries in by_target.items():
            if len(entries) < threshold:
                continue
            selectors = [entry.function_selector for entry in entries]
            repeated.append({
                "target": target,
                "count": len(entries),
                "selectors": selectors,
                "signatures": [lookup_signature(selector) or "" for selector in selectors],
            })
        return repeated

    def _find_callback_edges(self, call_stack: list[CallStackEntry]) -> list[dict[str, Any]]:
        window_size = self.config.get("recursion_window_size", 6)
        edges: list[dict[str, Any]] = []
        for index, current in enumerate(call_stack):
            if not current.to_addr:
                continue
            for later in call_stack[index + 1:index + 1 + window_size]:
                if later.to_addr != current.to_addr:
                    continue
                if later.depth <= current.depth:
                    edges.append({
                        "address": current.to_addr,
                        "first_depth": current.depth,
                        "second_depth": later.depth,
                        "first_selector": current.function_selector,
                        "second_selector": later.function_selector,
                    })
                    break
        return edges

    def _calculate_score(
        self,
        matches: list[PatternMatch],
        repeated_targets: list[dict[str, Any]],
        repeated_drains: list[dict[str, Any]],
        callback_edges: list[dict[str, Any]],
        max_depth: int,
    ) -> float:
        if not matches and not repeated_targets and not repeated_drains and not callback_edges:
            return 0.0

        score = max((match.score_contribution for match in matches), default=0.0)
        if repeated_targets:
            score = max(score, 55.0)
            score += min(15.0, repeated_targets[0]["count"] * 4.0)
        if repeated_drains:
            score = max(score, 65.0)
            score += min(15.0, repeated_drains[0]["count"] * 5.0)
        if callback_edges:
            score = max(score, 75.0)
            score += min(15.0, len(callback_edges) * 6.0)
        if max_depth >= 4:
            score += min(10.0, (max_depth - 3) * 2.0)
        return min(100.0, score)

    def _build_labels(
        self,
        matches: list[PatternMatch],
        repeated_targets: list[dict[str, Any]],
        repeated_drains: list[dict[str, Any]],
        callback_edges: list[dict[str, Any]],
    ) -> list[str]:
        labels: list[str] = []
        for match in matches:
            for selector in match.matched_selectors[:3]:
                labels.append(f"REENTRANCY_SIG:{lookup_signature(selector) or selector}")
        if repeated_targets:
            labels.append("REENTRANCY_REPEATED_TARGET")
        if repeated_drains:
            labels.append("REENTRANCY_REPEATED_DRAIN")
        if callback_edges:
            labels.append("REENTRANCY_CALLBACK_EDGE")
        return labels

    def _build_detection(
        self,
        call_stack: list[CallStackEntry],
        matches: list[PatternMatch],
        repeated_targets: list[dict[str, Any]],
        repeated_drains: list[dict[str, Any]],
        callback_edges: list[dict[str, Any]],
        max_depth: int,
        trace_data: EthTraceData,
    ) -> dict[str, Any]:
        return {
            "attack_type": self.ATTACK_TYPE_LABEL,
            "trace_count": trace_data.trace_count,
            "max_depth": max_depth,
            "pattern_matches": [match.model_dump() for match in matches],
            "repeated_targets": repeated_targets,
            "repeated_drain_selectors": repeated_drains,
            "callback_edges": callback_edges,
            "call_stack_summary": [
                {
                    "depth": entry.depth,
                    "from": entry.from_addr[:10] + "..." if entry.from_addr else "",
                    "to": entry.to_addr[:10] + "..." if entry.to_addr else "",
                    "selector": entry.function_selector,
                    "signature": lookup_signature(entry.function_selector) or "",
                    "call_type": entry.call_type,
                }
                for entry in call_stack[:30]
            ],
        }


NodeRegistry.register(ReentrancyTraceDetector)
