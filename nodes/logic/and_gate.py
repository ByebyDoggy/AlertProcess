"""AND 逻辑门 — 全部输入满足时输出 true"""

from __future__ import annotations

from typing import Any

from nodes.base import NodeRegistry
from nodes.logic.base import BaseLogicNode


class AndGate(BaseLogicNode):
    """
    AND 逻辑门 — 所有输入的 passed 均为 True 时输出 True。
    """

    name: str = "and_gate"
    label: str = "AND (全部满足)"
    description: str = "所有输入均满足条件时输出 true"
    icon: str = "\u26a1"
    color: str = "#ef4444"

    async def evaluate(self, passed_list: list[bool]) -> tuple[bool, dict[str, Any]]:
        result = all(passed_list)
        return result, {
            "logic_type": "and",
            "matched_count": sum(passed_list),
            "total_count": len(passed_list),
            "all_passed": result,
        }


NodeRegistry.register(AndGate)
