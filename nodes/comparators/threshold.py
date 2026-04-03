"""阈值比较器 — 支持 > / < / >= / <= / == / != 操作符"""

from __future__ import annotations

from typing import Any

from nodes.base import NodeRegistry
from nodes.comparators.base import BaseComparator


class ThresholdComparator(BaseComparator):
    """
    阈值比较器 — 对第一个输入的 score 与配置阈值进行比较。

    支持 6 种操作符: gt, lt, gte, lte, eq, neq
    """

    name: str = "threshold_comparator"
    label: str = "阈值比较"
    description: str = "将分数与阈值进行比较"
    icon: str = "\u2696"
    color: str = "#06b6d4"

    OPERATORS = {
        "gt": lambda a, b: a > b,
        "lt": lambda a, b: a < b,
        "gte": lambda a, b: a >= b,
        "lte": lambda a, b: a <= b,
        "eq": lambda a, b: a == b,
        "neq": lambda a, b: a != b,
    }

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operator": {
                    "type": "string",
                    "enum": ["gt", "lt", "gte", "lte", "eq", "neq"],
                    "default": "gte",
                    "description": "比较操作符"
                },
                "value": {
                    "type": "number",
                    "minimum": 0, "maximum": 100,
                    "default": 50,
                    "description": "阈值"
                },
            },
        }

    @classmethod
    def get_default_config(cls) -> dict[str, Any]:
        return {"operator": "gte", "value": 50}

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors = []
        op = config.get("operator", "gte")
        if op not in self.OPERATORS:
            errors.append(f"Unknown operator: '{op}'. Valid: {list(self.OPERATORS.keys())}")
        value = config.get("value", 50)
        if not (0 <= value <= 100):
            errors.append("value must be between 0 and 100")
        return errors

    async def compare(self, scores: list[float]) -> tuple[bool, dict[str, Any]]:
        score = scores[0]
        op = self.config.get("operator", "gte")
        threshold = self.config.get("value", 50)

        op_fn = self.OPERATORS.get(op, lambda a, b: a >= b)
        result = op_fn(score, threshold)

        return result, {
            "comparator_type": "threshold",
            "score": score,
            "threshold": threshold,
            "operator": op,
        }


NodeRegistry.register(ThresholdComparator)
