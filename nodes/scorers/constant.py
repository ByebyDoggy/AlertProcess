"""常量评分节点 — 输出用户定义的固定分数"""

from __future__ import annotations

from typing import Any

from nodes.base import (
    BaseNode,
    NodeCategory,
    NodeOutput,
    PortDef,
    NodeRegistry,
    score_to_severity,
)


class ConstantScorer(BaseNode):
    """
    常量评分节点 — 无需输入，直接输出用户配置的固定分数。

    典型场景：作为比较器或评分器的基准值输入，
    例如与加权评分结果比较时提供阈值参考。

    配置:
    - value: 输出的固定分数 (0-100，默认 50)
    """

    name: str = "constant_scorer"
    label: str = "常量值"
    description: str = "输出用户定义的固定分数，可作为评分器的基准参考"
    icon: str = "\U0001f522"
    color: str = "#06b6d4"
    category: NodeCategory = NodeCategory.SCORING

    @classmethod
    def get_inputs(cls) -> list[PortDef]:
        return []

    @classmethod
    def get_outputs(cls) -> list[PortDef]:
        return [PortDef(key="output", label="常量", data_type="score_output")]

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "value": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 100,
                    "default": 50,
                    "description": "输出的固定分数 (0-100)",
                },
            },
        }

    @classmethod
    def get_default_config(cls) -> dict[str, Any]:
        return {"value": 50}

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors = []
        value = config.get("value")
        if value is not None:
            try:
                v = float(value)
                if v < 0 or v > 100:
                    errors.append("value must be between 0 and 100")
            except (ValueError, TypeError):
                errors.append("value must be a number")
        return errors

    async def execute(
        self,
        context: dict[str, Any],
        inputs: dict[str, list[NodeOutput]],
    ) -> NodeOutput:
        value = float(self.config.get("value", 50))
        value = max(0.0, min(100.0, value))

        return NodeOutput(
            node_id=self.node_id,
            node_type=self.category.value,
            score=value,
            passed=True,
            context={
                "scorer_type": self.name,
                "constant_value": value,
            },
            severity=score_to_severity(value),
        )


NodeRegistry.register(ConstantScorer)
