"""
动作基类

所有动作节点继承此基类。
动作为终端节点，接收任意上游输入，异步执行副作用。
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

class ActionInputMixin(BaseModel):
    """动作通用输入 — 合并后的执行上下文"""
    context: dict[str, Any] = Field(default_factory=dict, description="合并后的执行上下文（含上游 score/labels + Provider 注入）")
    upstream_score: float = Field(default=0.0, description="上游节点的风险评分")
    upstream_passed: bool = Field(default=True, description="上游节点的 passed 状态")


class ActionOutputMixin(BaseModel):
    """动作通用输出 Mixin"""
    score: float = Field(ge=0, le=100, description="透传上游节点的风险评分")
    passed: bool = Field(description="透传上游的 passed 状态")
    severity: str = Field(default="UNKNOWN", description="透传上游的严重级别")
    labels: list[str] = Field(default_factory=list, description="标签列表")
    action_result: dict[str, Any] = Field(default_factory=dict, description="动作节点的执行结果详情")


# ---------------------------------------------------------------------------
# BaseAction — 动作节点基类
# ---------------------------------------------------------------------------

class BaseAction(BaseNode):
    """
    动作基类 — 终端节点。

    - 输入: 单端口 "input"，接收任意类型
    - 输出: 无（终端节点）
    """

    category: NodeCategory = NodeCategory.ACTION

    # ── Pydantic 输出/输入模型 ──
    OutputModel: type[BaseModel] = ActionOutputMixin
    InputModel: type[BaseModel] = ActionInputMixin

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
            output = ActionOutputMixin(
                score=upstream.score if upstream else 0.0,
                passed=upstream.passed if upstream else True,
                action_result=result,
            )
            final_context = merged_context
        else:
            inp = self.InputModel(
                context=merged_context,
                upstream_score=upstream.score if upstream else 0.0,
                upstream_passed=upstream.passed if upstream else True,
            )
            output = await self.process(inp)
            # 使用 inp.context 而非 merged_context，因为 process() 可能修改了 context
            final_context = inp.context

        return NodeOutput(
            node_id=self.node_id,
            node_type=self.category.value,
            score=output.score,
            passed=output.passed,
            context={**final_context, "action_result": output.action_result},
            labels=output.labels,
            severity=output.severity,
        )

    async def process(self, input: ActionInputMixin) -> ActionOutputMixin:
        """
        执行具体动作（子类实现）。

        Args:
            input: 动作输入模型，含合并后的上下文

        Returns:
            动作输出模型（score, passed, severity, labels, action_result）
        """
        raise NotImplementedError(f"{self.__class__.__name__}.process() not implemented")
