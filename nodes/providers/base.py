"""
Provider 节点基类

ContextProvider 从 ABC 改为继承 BaseNode，成为规则链中的节点。
每个 Provider 节点接收 TransactionContext 输入，输出 TransactionContext（extra 字段填充 Provider 数据）。
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
from nodes.models import TransactionContext


class ProviderInputMixin(TransactionContext):
    """Provider 节点输入 — TransactionContext"""
    pass


class BaseContextProviderNode(BaseNode):
    """
    Provider 节点基类。

    所有 ContextProvider 节点继承此基类。
    输入: TransactionContext（数据传输基础模型）
    输出: TransactionContext（extra 字段中填充 Provider 获取的数据）

    Provider 不输出检测结果，只负责填充上下文数据。
    """

    category: NodeCategory = NodeCategory.PROVIDER

    # 输入输出模型
    InputModel: type[TransactionContext] = ProviderInputMixin

    # Provider 节点的 provides 列表，声明向 extra 注入的字段
    provides: list[str] = []

    @classmethod
    def get_inputs(cls) -> list[PortDef]:
        return [PortDef(key="input", label="输入", data_type="context", required=True)]

    @classmethod
    def get_outputs(cls) -> list[PortDef]:
        return [PortDef(key="output", label="输出", data_type="context")]

    async def execute(
        self,
        context: dict[str, Any],
        inputs: dict[str, list[NodeOutput]],
    ) -> NodeOutput:
        """执行 Provider 节点：获取上游输入，从 context 提取字段，调用 fetch() 获取额外数据"""
        upstream = self._first_input(inputs)

        # 从 context dict 构建 TransactionContext
        if upstream:
            merged = {**context, **upstream.context}
        else:
            merged = dict(context)

        # 创建 TransactionContext
        tx_context = TransactionContext.from_dict(merged)

        # 调用子类 fetch 填充 extra
        extra_data = await self.fetch(tx_context)

        # 将 extra_data 合并到 extra 中
        if extra_data:
            tx_context.extra.update(extra_data)

        # 输出 NodeOutput，context 中包含完整的 TransactionContext 数据
        return NodeOutput(
            node_id=self.node_id,
            node_type=self.category.value,
            score=0.0,  # Provider 不计算评分
            passed=True,
            context=tx_context.to_dict(),
        )

    async def fetch(self, tx_context: TransactionContext) -> dict[str, Any]:
        """
        子类实现：获取额外上下文数据。

        Args:
            tx_context: 当前交易上下文

        Returns:
            要注入到 extra 中的字段字典
        """
        raise NotImplementedError(f"{self.__class__.__name__}.fetch() not implemented")
