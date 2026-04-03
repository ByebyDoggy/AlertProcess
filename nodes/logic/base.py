"""
逻辑表达式基类

所有逻辑表达式节点继承此基类。
逻辑表达式接收多个布尔型输入（passed），输出逻辑运算结果。
"""

from __future__ import annotations

from typing import Any

from nodes.base import (
    BaseNode,
    NodeCategory,
    NodeOutput,
    PortDef,
)


class BaseLogicNode(BaseNode):
    """
    逻辑表达式基类。

    - 输入: 多端口 "input_0", "input_1", ...，接收 comparison_output 或 logic_output
    - 输出: 双端口 "true" / "false"，data_type="logic_output"
    """

    category: NodeCategory = NodeCategory.LOGIC

    @classmethod
    def get_inputs(cls) -> list[PortDef]:
        return [
            PortDef(key="input_0", label="输入 1", data_type="comparison_output", required=True),
            PortDef(key="input_1", label="输入 2", data_type="comparison_output", required=True),
        ]

    @classmethod
    def get_outputs(cls) -> list[PortDef]:
        return [
            PortDef(key="true", label="满足", data_type="logic_output"),
            PortDef(key="false", label="不满足", data_type="logic_output"),
        ]

    async def execute(
        self,
        context: dict[str, Any],
        inputs: dict[str, list[NodeOutput]],
    ) -> NodeOutput:
        # 收集所有输入的 passed 状态
        passed_list: list[bool] = []
        for port_key in sorted(inputs.keys()):
            for inp in inputs[port_key]:
                passed_list.append(inp.passed)

        if not passed_list:
            return NodeOutput(
                node_id=self.node_id,
                node_type=self.category.value,
                score=0.0,
                passed=False,
                context={"logic_type": self.name, "result": False, "error": "no inputs"},
            )

        result, details = await self.evaluate(passed_list)
        details.setdefault("logic_type", self.name)
        details["result"] = result

        return NodeOutput(
            node_id=self.node_id,
            node_type=self.category.value,
            score=100.0 if result else 0.0,
            passed=result,
            context=details,
        )

    async def evaluate(self, passed_list: list[bool]) -> tuple[bool, dict[str, Any]]:
        """
        评估逻辑表达式（子类实现）。

        Args:
            passed_list: 上游各输入的 passed 状态列表

        Returns:
            (result, details)
        """
        raise NotImplementedError(f"{self.__class__.__name__}.evaluate() not implemented")
