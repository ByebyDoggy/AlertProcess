"""
SwapBurnClaimDetector - 示例时序检测器

检测 Swap -> Transfer -> Transfer 模式（简化的攻击模式）
用于验证 SequenceDetector 基类的功能
"""

from __future__ import annotations

from nodes.base import NodeRegistry
from nodes.detectors.sequence_base import SequenceDetector, DetectorOutputMixin
from nodes.models import TransactionContext
from nodes.primitives.sequence_matcher import (
    EventType,
    EventMatcher,
    SequencePattern,
    SequenceMatch,
)


@NodeRegistry.register
class SwapBurnClaimDetector(SequenceDetector):
    """
    Swap -> Transfer -> Transfer 模式检测器

    检测模式：
    1. Swap 事件（DEX 交易）
    2. Transfer 事件（代币转移）
    3. Transfer 事件（代币转移）

    评分逻辑：
    - 每匹配一个模式 +30 分
    - 最高 100 分
    """

    name = "swap_burn_claim_detector"
    label = "Swap-Transfer-Transfer 模式检测"
    description = "检测 Swap -> Transfer -> Transfer 时序模式（示例检测器）"
    icon = "🔄"
    color = "#FF5722"

    def define_pattern(self) -> SequencePattern:
        """
        定义时序模式: Swap -> Transfer -> Transfer

        Returns:
            时序模式定义
        """
        return SequencePattern(
            matchers=[
                EventMatcher(type=EventType.SWAP),
                EventMatcher(type=EventType.TRANSFER, within_logs=10),
                EventMatcher(type=EventType.TRANSFER, within_logs=10),
            ],
            name="Swap-Transfer-Transfer",
        )

    async def score_matches(
        self,
        tx_context: TransactionContext,
        matches: list[SequenceMatch],
    ) -> DetectorOutputMixin:
        """
        根据匹配结果计算评分

        Args:
            tx_context: 交易上下文
            matches: 匹配到的时序模式列表

        Returns:
            检测器输出
        """
        # 基础评分
        score = 0.0
        labels = []
        logs = []

        if not matches:
            logs.append("未检测到 Swap-Transfer-Transfer 模式")
            return DetectorOutputMixin(
                score=score,
                passed=False,
                severity="UNKNOWN",
                labels=labels,
                detection={
                    "pattern_matches": 0,
                },
                logs=logs,
            )

        # 每匹配一个模式 +30 分
        match_count = len(matches)
        score = min(100.0, match_count * 30.0)

        labels.append("swap_transfer_transfer_pattern")
        logs.append(f"检测到 {match_count} 个 Swap-Transfer-Transfer 模式")

        # 记录匹配详情
        match_details = []
        for i, match in enumerate(matches):
            swap_event = match.events[0].data
            transfer1_event = match.events[1].data
            transfer2_event = match.events[2].data

            match_details.append({
                "match_index": i,
                "swap_dex": swap_event.get("dex_address"),
                "transfer1_token": transfer1_event.get("token_address"),
                "transfer2_token": transfer2_event.get("token_address"),
                "log_range": f"{match.start_index}-{match.end_index}",
            })

            logs.append(
                f"模式 {i+1}: Swap({swap_event.get('dex_address')[:10]}...) -> "
                f"Transfer({transfer1_event.get('token_address')[:10]}...) -> "
                f"Transfer({transfer2_event.get('token_address')[:10]}...)"
            )

        return DetectorOutputMixin(
            score=score,
            passed=score >= self.config.get("threshold", 50.0),
            severity=self._calculate_severity(score),
            labels=labels,
            detection={
                "pattern_matches": match_count,
                "match_details": match_details,
            },
            logs=logs,
        )

    def _calculate_severity(self, score: float) -> str:
        """计算严重程度"""
        if score >= 80:
            return "CRITICAL"
        elif score >= 60:
            return "HIGH"
        elif score >= 40:
            return "MEDIUM"
        elif score >= 20:
            return "LOW"
        else:
            return "UNKNOWN"
