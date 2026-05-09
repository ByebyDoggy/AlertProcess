"""
SequenceDetector - 时序检测器基类

专门处理事件序列模式匹配（如 Swap -> Burn -> Transfer 闭环）
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from nodes.detectors.base import BaseDetector, DetectorOutputMixin
from nodes.models import TransactionContext
from nodes.primitives.sequence_matcher import (
    Event,
    EventType,
    SequenceMatcher,
    SequenceMatch,
    SequencePattern,
)


class SequenceDetector(BaseDetector):
    """
    时序检测器基类

    功能：专门处理事件序列模式匹配（如 Swap -> Burn -> Transfer 闭环）

    子类只需实现：
    1. define_pattern() - 定义要匹配的时序模式
    2. score_matches() - 根据匹配结果计算评分
    """

    async def process(self, tx_context: TransactionContext) -> DetectorOutputMixin:
        """
        执行时序检测逻辑

        Args:
            tx_context: 交易上下文

        Returns:
            检测器输出
        """
        # 1. 从 context 构建事件列表
        events = self._build_events(tx_context)

        # 2. 获取子类定义的时序模式
        pattern = self.define_pattern()

        # 3. 执行模式匹配
        matcher = SequenceMatcher()
        matches = matcher.match(events, pattern)

        # 4. 调用子类评分逻辑
        return await self.score_matches(tx_context, matches)

    def _build_events(self, tx_context: TransactionContext) -> list[Event]:
        """
        从 context 构建事件列表

        从 LogParserProvider 注入的预解析数据中构建统一的事件列表

        Args:
            tx_context: 交易上下文

        Returns:
            事件列表（按 log_index 排序）
        """
        events = []

        # 从预解析数据构建 Transfer 事件
        parsed_transfers = self.get_parsed_transfers(tx_context)
        for transfer in parsed_transfers:
            events.append(
                Event(
                    type=EventType.TRANSFER,
                    log_index=int(transfer["log_index"], 16) if isinstance(transfer["log_index"], str) else transfer["log_index"],
                    data=transfer,
                )
            )

        # 从预解析数据构建 Swap 事件
        parsed_swaps = self.get_parsed_swaps(tx_context)
        for swap in parsed_swaps:
            events.append(
                Event(
                    type=EventType.SWAP,
                    log_index=int(swap["log_index"], 16) if isinstance(swap["log_index"], str) else swap["log_index"],
                    data=swap,
                )
            )

        # 从预解析数据构建 Approval 事件
        parsed_approvals = self.get_parsed_approvals(tx_context)
        for approval in parsed_approvals:
            events.append(
                Event(
                    type=EventType.APPROVAL,
                    log_index=int(approval["log_index"], 16) if isinstance(approval["log_index"], str) else approval["log_index"],
                    data=approval,
                )
            )

        # 按 log_index 排序
        events.sort(key=lambda e: e.log_index)

        return events

    @abstractmethod
    def define_pattern(self) -> SequencePattern:
        """
        定义要匹配的时序模式（子类实现）

        Returns:
            时序模式定义
        """
        raise NotImplementedError(f"{self.__class__.__name__}.define_pattern() not implemented")

    @abstractmethod
    async def score_matches(
        self,
        tx_context: TransactionContext,
        matches: list[SequenceMatch],
    ) -> DetectorOutputMixin:
        """
        根据匹配结果计算评分（子类实现）

        Args:
            tx_context: 交易上下文
            matches: 匹配到的时序模式列表

        Returns:
            检测器输出
        """
        raise NotImplementedError(f"{self.__class__.__name__}.score_matches() not implemented")
