"""
检测器基类

所有检测器节点继承此基类。检测器接收 context 输入，输出 0-100 风险评分。
"""

from __future__ import annotations

from typing import Any

from nodes.base import (
    BaseNode,
    NodeCategory,
    NodeOutput,
    PortDef,
    score_to_severity,
)


class BaseDetector(BaseNode):
    """
    检测器基类。

    - 输入: 单端口 "input"，接收任意上游输出
    - 输出: 单端口 "output"，data_type="detection_output"，携带 score(0-100)
    """

    category: NodeCategory = NodeCategory.DETECTION

    @classmethod
    def get_inputs(cls) -> list[PortDef]:
        return [PortDef(key="input", label="输入", data_type="any", required=True)]

    @classmethod
    def get_outputs(cls) -> list[PortDef]:
        return [PortDef(key="output", label="输出", data_type="detection_output")]

    async def execute(
        self,
        context: dict[str, Any],
        inputs: dict[str, list[NodeOutput]],
    ) -> NodeOutput:
        upstream = self._first_input(inputs)
        merged_context = self._merge_context(context, upstream)

        score, details = await self.detect(merged_context)
        score = max(0.0, min(100.0, score))

        threshold = self.config.get("threshold", 50.0)

        return NodeOutput(
            node_id=self.node_id,
            node_type=self.category.value,
            score=score,
            passed=score >= threshold,
            context={**merged_context, "detection": details},
            labels=details.get("labels", []),
            severity=score_to_severity(score),
        )

    async def detect(self, context: dict[str, Any]) -> tuple[float, dict[str, Any]]:
        """
        执行检测逻辑（子类实现）。

        Returns:
            (score, details): 0-100 分 + 详细信息字典
        """
        raise NotImplementedError(f"{self.__class__.__name__}.detect() not implemented")
