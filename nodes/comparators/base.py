"""
条件比较器基类

所有条件比较器节点继承此基类。
比较器接收 score 输入，输出布尔判定（score=100 或 score=0）。
"""

from __future__ import annotations

from typing import Any

from nodes.base import (
    BaseNode,
    NodeCategory,
    NodeOutput,
    PortDef,
)


class BaseComparator(BaseNode):
    """
    条件比较器基类。

    - 输入: 多端口 "input_0", "input_1", ...，接收 detection_output 或 score_output
    - 输出: 双端口 "true" / "false"，data_type="comparison_output"
    """

    category: NodeCategory = NodeCategory.COMPARISON

    @classmethod
    def get_inputs(cls) -> list[PortDef]:
        return [
            PortDef(key="input_0", label="输入 1", data_type="detection_output", required=True),
            PortDef(key="input_1", label="输入 2", data_type="detection_output", required=False),
        ]

    @classmethod
    def get_outputs(cls) -> list[PortDef]:
        return [
            PortDef(key="true", label="满足", data_type="comparison_output"),
            PortDef(key="false", label="不满足", data_type="comparison_output"),
        ]

    async def execute(
        self,
        context: dict[str, Any],
        inputs: dict[str, list[NodeOutput]],
    ) -> NodeOutput:
        # 收集所有输入端口的 score
        scores: list[float] = []
        for port_key in sorted(inputs.keys()):
            for inp in inputs[port_key]:
                scores.append(inp.score)

        if not scores:
            # 无输入时不通过
            return NodeOutput(
                node_id=self.node_id,
                node_type=self.category.value,
                score=0.0,
                passed=False,
                context={"comparator_type": self.name, "result": False, "error": "no inputs"},
            )

        result, details = await self.compare(scores)
        details.setdefault("comparator_type", self.name)
        details["result"] = result

        return NodeOutput(
            node_id=self.node_id,
            node_type=self.category.value,
            score=100.0 if result else 0.0,
            passed=result,
            context=details,
        )

    async def compare(self, scores: list[float]) -> tuple[bool, dict[str, Any]]:
        """
        执行比较逻辑（子类实现）。

        Args:
            scores: 上游输入的 score 列表

        Returns:
            (result, details): 比较结果 + 详细信息
        """
        raise NotImplementedError(f"{self.__class__.__name__}.compare() not implemented")
