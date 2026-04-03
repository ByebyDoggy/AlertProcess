"""加权评分器 — 对多个输入分数按权重加权求和"""

from __future__ import annotations

from typing import Any

from nodes.base import NodeRegistry
from nodes.scorers.base import BaseScorer


class WeightedScorer(BaseScorer):
    """
    加权评分器 — 对所有输入分数按配置的权重进行加权求和。

    配置:
    - weights: 权重数组，长度应与输入数量一致
    - normalize: 是否将权重归一化（默认 True）
    """

    name: str = "weighted_scorer"
    label: str = "加权评分"
    description: str = "对多个输入分数按权重加权求和"
    icon: str = "\u2696"
    color: str = "#8b5cf6"

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "threshold": {"type": "number", "minimum": 0, "maximum": 100, "default": 50},
                "weights": {
                    "type": "array",
                    "items": {"type": "number", "minimum": 0},
                    "default": [],
                    "description": "权重数组，长度应与输入数量一致",
                },
                "normalize": {
                    "type": "boolean",
                    "default": True,
                    "description": "是否将权重归一化（权重之和=1）",
                },
            },
        }

    @classmethod
    def get_default_config(cls) -> dict[str, Any]:
        return {"threshold": 50, "weights": [], "normalize": True}

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors = []
        weights = config.get("weights", [])
        if not isinstance(weights, list):
            errors.append("weights must be a list of numbers")
        elif any(not isinstance(w, (int, float)) or w < 0 for w in weights):
            errors.append("weights must contain non-negative numbers")
        return errors

    async def aggregate(self, scores: list[float]) -> tuple[float, dict[str, Any]]:
        weights = self.config.get("weights", [])
        normalize = self.config.get("normalize", True)

        # 如果没有配置权重，使用等权重
        if not weights:
            weights = [1.0] * len(scores)

        # 截取或填充权重以匹配 scores 长度
        weights = list(weights[:len(scores)])
        while len(weights) < len(scores):
            weights.append(1.0)

        total_weight = sum(weights)

        if normalize and total_weight > 0:
            result = sum(s * w for s, w in zip(scores, weights)) / total_weight
        else:
            result = sum(s * w for s, w in zip(scores, weights))

        return result, {
            "scorer_type": "weighted",
            "weights": weights,
            "normalized": normalize,
            "total_weight": total_weight,
            "count": len(scores),
        }


NodeRegistry.register(WeightedScorer)
