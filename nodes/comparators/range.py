"""区间比较器 — 检查 score 是否在 [min, max] 区间内"""

from __future__ import annotations

from typing import Any

from nodes.base import NodeRegistry
from nodes.comparators.base import BaseComparator


class RangeComparator(BaseComparator):
    """
    区间比较器 — 检查第一个输入的 score 是否在配置的区间范围内。

    支持 'inside' 和 'outside' 两种模式。
    """

    name: str = "range_comparator"
    label: str = "区间比较"
    description: str = "检查分数是否在指定区间范围内"
    icon: str = "\U0001f4cf"
    color: str = "#0891b2"

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "min_value": {
                    "type": "number", "minimum": 0, "maximum": 100,
                    "default": 0, "description": "区间下界"
                },
                "max_value": {
                    "type": "number", "minimum": 0, "maximum": 100,
                    "default": 100, "description": "区间上界"
                },
                "mode": {
                    "type": "string", "enum": ["inside", "outside"],
                    "default": "inside",
                    "description": "inside: 在区间内满足; outside: 在区间外满足"
                },
            },
        }

    @classmethod
    def get_default_config(cls) -> dict[str, Any]:
        return {"min_value": 0, "max_value": 100, "mode": "inside"}

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors = []
        min_v = config.get("min_value", 0)
        max_v = config.get("max_value", 100)
        if min_v > max_v:
            errors.append("min_value must be <= max_value")
        if config.get("mode", "inside") not in ("inside", "outside"):
            errors.append("mode must be 'inside' or 'outside'")
        return errors

    async def compare(self, scores: list[float]) -> tuple[bool, dict[str, Any]]:
        score = scores[0]
        min_v = self.config.get("min_value", 0)
        max_v = self.config.get("max_value", 100)
        mode = self.config.get("mode", "inside")

        in_range = min_v <= score <= max_v
        result = in_range if mode == "inside" else not in_range

        return result, {
            "comparator_type": "range",
            "score": score,
            "min_value": min_v,
            "max_value": max_v,
            "mode": mode,
            "in_range": in_range,
        }


NodeRegistry.register(RangeComparator)
