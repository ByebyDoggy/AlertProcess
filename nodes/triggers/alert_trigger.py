"""
告警触发器节点

接收外部告警数据作为规则链的入口，输出完整的 TransactionContext。
"""

from __future__ import annotations

from typing import Any

from nodes.base import (
    BaseNode,
    NodeCategory,
    NodeOutput,
    PortDef,
    NodeRegistry,
)


class AlertTrigger(BaseNode):
    """
    告警触发器 — 规则链的入口节点。

    接收外部告警数据（链 ID、交易哈希等），将原始数据放入 context 输出。
    """

    name: str = "alert_trigger"
    label: str = "告警触发器"
    description: str = "接收告警数据，作为规则链的入口"
    category: NodeCategory = NodeCategory.INPUT
    icon: str = "\U0001f514"
    color: str = "#22c55e"

    @classmethod
    def get_inputs(cls) -> list[PortDef]:
        return []

    @classmethod
    def get_outputs(cls) -> list[PortDef]:
        return [PortDef(key="output", label="输出", data_type="context")]

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

    async def execute(
        self,
        context: dict[str, Any],
        inputs: dict[str, list[NodeOutput]],
    ) -> NodeOutput:
        return NodeOutput(
            node_id=self.node_id,
            node_type=self.category.value,
            score=0.0,
            passed=True,
            context=dict(context),
        )


NodeRegistry.register(AlertTrigger)
