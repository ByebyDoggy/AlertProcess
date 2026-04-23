"""
逻辑表达式基类

所有逻辑表达式节点继承此基类。
逻辑表达式接收多个布尔型输入（passed），输出逻辑运算结果。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from nodes.base import (
    BaseNode,
    NodeCategory,
    NodeOutput,
    PortDef,
)


# ---------------------------------------------------------------------------
# Pydantic Mixin 类（模块级定义，供子类继承扩展）
# ---------------------------------------------------------------------------

class LogicInputMixin(BaseModel):
    """逻辑门通用输入 — 上游 passed 状态列表"""
    passed_list: list[bool] = Field(description="上游各输入的 passed 状态列表")


class LogicOutputMixin(BaseModel):
    """逻辑门通用输出 Mixin"""
    score: float = Field(description="100=逻辑真, 0=逻辑假")
    passed: bool = Field(description="逻辑表达式求值结果")
    severity: str = Field(default="UNKNOWN", description="严重级别")
    detection: dict[str, Any] = Field(default_factory=dict, description="逻辑运算详情")


# ---------------------------------------------------------------------------
# BaseLogicNode — 逻辑表达式节点基类
# ---------------------------------------------------------------------------

class BaseLogicNode(BaseNode):
    """
    逻辑表达式基类。

    - 输入: 多端口 "input_0", "input_1", ...，接收 comparison_output 或 logic_output
    - 输出: 双端口 "true" / "false"，data_type="logic_output"
    """

    category: NodeCategory = NodeCategory.LOGIC

    # ── Pydantic 输出/输入模型 ──
    OutputModel: type[BaseModel] = LogicOutputMixin
    InputModel: type[BaseModel] = LogicInputMixin

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

        inp = self.InputModel(passed_list=passed_list)
        output = await self.process(inp)

        result = output.passed
        details = output.detection
        details.setdefault("logic_type", self.name)
        details["result"] = result

        return NodeOutput(
            node_id=self.node_id,
            node_type=self.category.value,
            score=output.score,
            passed=result,
            context=details,
        )

    async def process(self, input: LogicInputMixin) -> LogicOutputMixin:
        """
        评估逻辑表达式（子类实现）。

        Args:
            input: 逻辑门输入模型，含上游 passed 状态列表

        Returns:
            逻辑门输出模型（score, passed, severity, detection）
        """
        raise NotImplementedError(f"{self.__class__.__name__}.process() not implemented")
