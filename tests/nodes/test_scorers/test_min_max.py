"""tests/nodes/test_scorers/test_min_max.py — MinMaxScorer 测试"""

import pytest

from nodes.scorers.min_max import MinMaxScorer
from nodes.base import NodeOutput, NodeCategory


def _make_multi_input(*scores: float):
    inputs = {}
    for i, s in enumerate(scores):
        key = f"input_{i}" if i > 0 else "input_0"
        inputs.setdefault(key, [])
        inputs[key].append(NodeOutput(node_id=f"d{i}", node_type="detection", score=s))
    return inputs


class TestMinMaxScorer:

    @pytest.mark.asyncio
    async def test_max_mode(self):
        """max 模式取最大值"""
        scorer = MinMaxScorer(node_id="s1", config={"mode": "max"})
        result = await scorer.execute({}, _make_multi_input(30, 70, 50))
        assert result.score == 70.0
        assert result.passed is True  # 70 >= 50

    @pytest.mark.asyncio
    async def test_min_mode(self):
        """min 模式取最小值"""
        scorer = MinMaxScorer(node_id="s1", config={"mode": "min"})
        result = await scorer.execute({}, _make_multi_input(30, 70, 50))
        assert result.score == 30.0
        assert result.passed is False  # 30 < 50

    @pytest.mark.asyncio
    async def test_default_mode(self):
        """默认模式是 max"""
        scorer = MinMaxScorer(node_id="s1")
        result = await scorer.execute({}, _make_multi_input(20, 80))
        assert result.score == 80.0

    @pytest.mark.asyncio
    async def test_single_input(self):
        """单个输入"""
        scorer = MinMaxScorer(node_id="s1", config={"mode": "min"})
        result = await scorer.execute({}, _make_multi_input(55))
        assert result.score == 55.0

    @pytest.mark.asyncio
    async def test_all_same_scores(self):
        """所有分数相同"""
        scorer = MinMaxScorer(node_id="s1")
        result = await scorer.execute({}, _make_multi_input(60, 60, 60))
        assert result.score == 60.0

    @pytest.mark.asyncio
    async def test_no_inputs(self):
        """无输入 → 0"""
        scorer = MinMaxScorer(node_id="s1")
        result = await scorer.execute({}, {})
        assert result.score == 0.0
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_custom_threshold(self):
        """自定义阈值"""
        scorer = MinMaxScorer(node_id="s1", config={"mode": "min", "threshold": 30})
        result = await scorer.execute({}, _make_multi_input(30, 70))
        assert result.score == 30.0
        assert result.passed is True  # 30 >= 30

    def test_validate_config_ok(self):
        scorer = MinMaxScorer()
        assert scorer.validate_config({"mode": "min"}) == []
        assert scorer.validate_config({"mode": "max"}) == []

    def test_validate_config_invalid_mode(self):
        scorer = MinMaxScorer()
        errors = scorer.validate_config({"mode": "avg"})
        assert len(errors) > 0

    def test_category(self):
        assert MinMaxScorer.category == NodeCategory.SCORING

    def test_registered(self):
        from nodes.base import NodeRegistry
        NodeRegistry.register(MinMaxScorer)
        assert NodeRegistry.get("minmax_scorer") is MinMaxScorer
