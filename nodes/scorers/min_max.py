"""最值评分器 — 取最小或最大分数"""

from __future__ import annotations

from typing import Any

from nodes.base import NodeRegistry
from nodes.scorers.base import BaseScorer


class MinMaxScorer(BaseScorer):
    """
    最值评分器 — 对所有输入分数取最小值或最大值。
    """

    name: str = "minmax_scorer"
    label: str = "最值评分"
    description: str = "对多个输入分数取最小或最大值"
    icon: str = "\U0001f3c6"
    color: str = "#eab308"

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "threshold": {"type": "number", "minimum": 0, "maximum": 100, "default": 50},
                "mode": {"type": "string", "enum": ["min", "max"], "default": "max"},
            },
        }

    @classmethod
    def get_default_config(cls) -> dict[str, Any]:
        return {"threshold": 50, "mode": "max"}

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors = []
        if config.get("mode", "max") not in ("min", "max"):
            errors.append("mode must be 'min' or 'max'")
        return errors

    async def aggregate(self, scores: list[float]) -> tuple[float, dict[str, Any]]:
        mode = self.config.get("mode", "max")
        result = max(scores) if mode == "max" else min(scores) if scores else 0.0
        return result, {
            "scorer_type": "minmax",
            "mode": mode,
            "count": len(scores),
            "scores": scores,
        }


NodeRegistry.register(MinMaxScorer)
