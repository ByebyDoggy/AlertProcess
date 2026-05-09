"""
时序匹配原语

提供事件序列模式匹配功能，用于检测时序攻击模式。
"""

from dataclasses import dataclass
from typing import Any, Callable
from enum import Enum


class EventType(Enum):
    """事件类型枚举"""
    TRANSFER = "transfer"
    SWAP = "swap"
    APPROVAL = "approval"
    BURN = "burn"
    MINT = "mint"


@dataclass
class Event:
    """通用事件数据结构"""
    type: EventType
    log_index: int
    data: Any  # TransferEvent, SwapEvent 等


@dataclass
class EventMatcher:
    """
    事件匹配器

    定义要匹配的事件类型和条件
    """
    type: EventType
    condition: Callable[[Event], bool] | None = None
    within_logs: int | None = None  # 在多少个 log 范围内


@dataclass
class SequencePattern:
    """
    时序模式定义

    定义一个事件序列模式，如 Swap -> Burn -> Transfer
    """
    matchers: list[EventMatcher]
    name: str = ""


@dataclass
class SequenceMatch:
    """
    时序匹配结果

    记录匹配到的事件序列
    """
    pattern: SequencePattern
    events: list[Event]
    start_index: int
    end_index: int


class SequenceMatcher:
    """
    时序模式匹配器

    用于在事件列表中查找符合特定模式的事件序列
    """

    def match(
        self,
        events: list[Event],
        pattern: SequencePattern,
    ) -> list[SequenceMatch]:
        """
        匹配事件序列模式

        Args:
            events: 事件列表（按 log_index 排序）
            pattern: 要匹配的时序模式

        Returns:
            匹配结果列表
        """
        matches = []

        for i in range(len(events)):
            match = self._try_match_from(events, i, pattern)
            if match:
                matches.append(match)

        return matches

    def _try_match_from(
        self,
        events: list[Event],
        start_idx: int,
        pattern: SequencePattern,
    ) -> SequenceMatch | None:
        """
        从指定位置尝试匹配模式

        Args:
            events: 事件列表
            start_idx: 开始匹配的索引
            pattern: 要匹配的模式

        Returns:
            匹配结果，如果不匹配则返回 None
        """
        matched_events = []
        current_idx = start_idx
        matcher_idx = 0

        # 第一个 matcher 必须从 start_idx 开始匹配
        first_matcher = pattern.matchers[0]
        if start_idx >= len(events):
            return None

        first_event = events[start_idx]
        if first_event.type != first_matcher.type:
            return None
        if first_matcher.condition is not None and not first_matcher.condition(first_event):
            return None

        matched_events.append(first_event)
        current_idx = start_idx + 1
        matcher_idx = 1

        # 匹配后续的 matchers
        for matcher in pattern.matchers[1:]:
            # 获取上一个匹配事件的 log_index
            prev_log_index = matched_events[-1].log_index

            # 在范围内查找匹配的事件
            found = False
            for i in range(current_idx, len(events)):
                event = events[i]

                # 检查 within_logs 约束（基于 log_index 差值）
                if matcher.within_logs is not None:
                    log_index_diff = event.log_index - prev_log_index
                    if log_index_diff > matcher.within_logs:
                        # 超出范围，停止搜索
                        break

                # 检查事件类型
                if event.type != matcher.type:
                    continue

                # 检查条件（如果有）
                if matcher.condition is not None:
                    if not matcher.condition(event):
                        continue

                # 匹配成功
                matched_events.append(event)
                current_idx = i + 1
                found = True
                break

            # 如果当前 matcher 没有找到匹配，整个模式匹配失败
            if not found:
                return None

        # 所有 matcher 都匹配成功
        return SequenceMatch(
            pattern=pattern,
            events=matched_events,
            start_index=start_idx,
            end_index=current_idx - 1,
        )
