"""平均评分器 — 对多个输入分数取平均值"""

from __future__ import annotations

from typing import Any

from nodes.base import NodeRegistry
from nodes.scorers.base import BaseScorer


class AverageScorer(BaseScorer):
    """
    平均评分器 — 对所有输入分数取算术平均值。
    """

    name: str = "average_scorer"
    label: str = "平均评分"
    description: str = "对多个输入分数取平均值"
    icon: str = "\U0001f4ca"
    color: str = "#f97316"

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "threshold": {
                    "type": "number", "minimum": 0, "maximum": 100,
                    "default": 50, "description": "passed 阈值"
                },
            },
        }

    @classmethod
    def get_default_config(cls) -> dict[str, Any]:
        return {"threshold": 50}

    async def aggregate(self, scores: list[float]) -> tuple[float, dict[str, Any]]:
        avg = sum(scores) / len(scores) if scores else 0.0
        return avg, {
            "scorer_type": "average",
            "count": len(scores),
            "sum": sum(scores),
            "average": avg,
        }


NodeRegistry.register(AverageScorer)
