"""tests/nodes/test_scorers/test_average.py — AverageScorer 测试"""

import pytest

from nodes.scorers.average import AverageScorer
from nodes.base import NodeOutput, NodeCategory


def _make_multi_input(*scores: float):
    inputs = {}
    for i, s in enumerate(scores):
        inputs[f"input_0"] = inputs.get("input_0", [])
        inputs["input_0"].append(NodeOutput(node_id=f"d{i}", node_type="detection", score=s))
    return inputs


class TestAverageScorer:

    @pytest.mark.asyncio
    async def test_three_scores(self):
        scorer = AverageScorer(node_id="s1")
        result = await scorer.execute({}, _make_multi_input(60, 80, 100))
        assert result.score == pytest.approx(80.0)

    @pytest.mark.asyncio
    async def test_single_score(self):
        scorer = AverageScorer(node_id="s1")
        result = await scorer.execute({}, _make_multi_input(75))
        assert result.score == 75.0

    @pytest.mark.asyncio
    async def test_zero_scores(self):
        scorer = AverageScorer(node_id="s1")
        result = await scorer.execute({}, _make_multi_input(0, 0, 0))
        assert result.score == 0.0
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_no_inputs(self):
        scorer = AverageScorer(node_id="s1")
        result = await scorer.execute({}, {})
        assert result.score == 0.0
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_passed_with_custom_threshold(self):
        scorer = AverageScorer(node_id="s1", config={"threshold": 30})
        result = await scorer.execute({}, _make_multi_input(20, 40))
        assert result.score == 30.0
        assert result.passed is True  # 30 >= 30

    def test_category(self):
        assert AverageScorer.category == NodeCategory.SCORING

    def test_registered(self):
        from nodes.base import NodeRegistry
        NodeRegistry.register(AverageScorer)
        assert NodeRegistry.get("average_scorer") is AverageScorer
