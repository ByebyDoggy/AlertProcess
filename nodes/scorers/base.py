"""
评分器基类

所有评分器节点继承此基类。
评分器接收多个 score 输入，聚合输出单一 score。
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


class BaseScorer(BaseNode):
    """
    评分器基类。

    - 输入: 多端口 "input_0", "input_1", ...，接收 detection_output 或 score_output
    - 输出: 单端口 "output"，data_type="score_output"，携带聚合后的 score(0-100)
    """

    category: NodeCategory = NodeCategory.SCORING

    @classmethod
    def get_inputs(cls) -> list[PortDef]:
        return [
            PortDef(key="input_0", label="输入 1", data_type="detection_output",
                     required=True, multi=True),
            PortDef(key="input_1", label="输入 2", data_type="detection_output", required=False),
        ]

    @classmethod
    def get_outputs(cls) -> list[PortDef]:
        return [PortDef(key="output", label="聚合评分", data_type="score_output")]

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
            return NodeOutput(
                node_id=self.node_id,
                node_type=self.category.value,
                score=0.0,
                passed=False,
                context={"scorer_type": self.name, "error": "no inputs"},
            )

        agg_score, details = await self.aggregate(scores)
        agg_score = max(0.0, min(100.0, agg_score))
        details.setdefault("scorer_type", self.name)
        details["input_scores"] = scores

        threshold = self.config.get("threshold", 50.0)

        return NodeOutput(
            node_id=self.node_id,
            node_type=self.category.value,
            score=agg_score,
            passed=agg_score >= threshold,
            context=details,
            severity=score_to_severity(agg_score),
        )

    async def aggregate(self, scores: list[float]) -> tuple[float, dict[str, Any]]:
        """
        聚合多个分数（子类实现）。

        Returns:
            (aggregated_score, details)
        """
        raise NotImplementedError(f"{self.__class__.__name__}.aggregate() not implemented")
