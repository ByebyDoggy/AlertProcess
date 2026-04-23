"""
告警触发器节点

接收外部告警数据作为规则链的入口，输出完整的 TransactionContext。
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from nodes.base import (
    BaseNode,
    NodeCategory,
    NodeOutput,
    PortDef,
    NodeRegistry,
    NodeOutputMixin,
)
from nodes.models import TransactionContext


class AlertTriggerOutput(TransactionContext):
    """告警触发器输出 — 完整的交易上下文字段（继承 TransactionContext）"""
    pass


class AlertTrigger(BaseNode):
    """
    告警触发器 — 规则链的入口节点。

    接收外部告警数据（链 ID、交易哈希等），将原始数据放入 context 输出。
    """

    name: str = "alert_trigger"
    label: str = "告警触发器"
    description: str = "规则链的入口节点，接收外部告警数据（chain_id、tx_hash、gas_price 等）并传递给下游检测节点。每条规则链必须有且仅有一个触发器。"
    category: NodeCategory = NodeCategory.INPUT
    icon: str = "\U0001f514"
    color: str = "#22c55e"

    # ── Pydantic 输出模型 ──
    OutputModel: type = AlertTriggerOutput

    @classmethod
    def get_inputs(cls) -> list[PortDef]:
        return []

    @classmethod
    def get_outputs(cls) -> list[PortDef]:
        return [PortDef(key="output", label="输出", data_type="context")]

    async def execute(
        self,
        context: dict[str, Any],
        inputs: dict[str, list[NodeOutput]],
    ) -> NodeOutput:
        # 将 context 构建为 TransactionContext 格式
        tx_context = TransactionContext.from_dict(context)
        return NodeOutput(
            node_id=self.node_id,
            node_type=self.category.value,
            score=0.0,
            passed=True,
            context=tx_context.to_dict(),
        )


NodeRegistry.register(AlertTrigger)
