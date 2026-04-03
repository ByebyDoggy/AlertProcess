"""OR 逻辑门 — 任一输入满足时输出 true"""

from __future__ import annotations

from typing import Any

from nodes.base import NodeRegistry
from nodes.logic.base import BaseLogicNode


class OrGate(BaseLogicNode):
    """
    OR 逻辑门 — 任一输入的 passed 为 True 时输出 True。
    """

    name: str = "or_gate"
    label: str = "OR (任一满足)"
    description: str = "任一输入满足条件时输出 true"
    icon: str = "\U0001f503"
    color: str = "#22c55e"

    async def evaluate(self, passed_list: list[bool]) -> tuple[bool, dict[str, Any]]:
        result = any(passed_list)
        return result, {
            "logic_type": "or",
            "matched_count": sum(passed_list),
            "total_count": len(passed_list),
            "any_passed": result,
        }


NodeRegistry.register(OrGate)
