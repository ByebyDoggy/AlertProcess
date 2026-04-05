"""
动作基类

所有动作节点继承此基类。
动作为终端节点，接收任意上游输入，异步执行副作用。
"""

from __future__ import annotations

from typing import Any

from nodes.base import (
    BaseNode,
    NodeCategory,
    NodeOutput,
    PortDef,
)


class BaseAction(BaseNode):
    """
    动作基类 — 终端节点。

    - 输入: 单端口 "input"，接收任意类型
    - 输出: 无（终端节点）
    """

    category: NodeCategory = NodeCategory.ACTION

    @classmethod
    def get_inputs(cls) -> list[PortDef]:
        return [PortDef(key="input", label="输入", data_type="any", required=True)]

    @classmethod
    def get_outputs(cls) -> list[PortDef]:
        return []  # 终端节点，无输出

    async def execute(
        self,
        context: dict[str, Any],
        inputs: dict[str, list[NodeOutput]],
    ) -> NodeOutput:
        upstream = self._first_input(inputs)
        merged_context = self._merge_context(context, upstream)

        # Dry-run 模式：Action 节点仅模拟，不实际执行副作用
        if context.get("__dry_run__"):
            result = {"dry_run": True, "simulated": True, "action_type": self.name}
        else:
            result = await self.run(merged_context)

        return NodeOutput(
            node_id=self.node_id,
            node_type=self.category.value,
            score=upstream.score if upstream else 0.0,
            passed=upstream.passed if upstream else True,
            context={**merged_context, "action_result": result},
        )

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        执行具体动作（子类实现）。

        如 HTTP 请求、数据库写入等异步 IO 操作。

        Returns:
            执行结果描述字典
        """
        raise NotImplementedError(f"{self.__class__.__name__}.run() not implemented")
