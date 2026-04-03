"""tests/nodes/test_scorers/test_weighted.py — WeightedScorer 测试"""

import pytest

from nodes.scorers.weighted import WeightedScorer
from nodes.base import NodeOutput, NodeCategory


def _make_multi_input(*scores: float):
    inputs = {}
    for i, s in enumerate(scores):
        key = f"input_{i}" if i > 0 else "input_0"
        inputs.setdefault(key, [])
        inputs[key].append(NodeOutput(node_id=f"d{i}", node_type="detection", score=s))
    return inputs


class TestWeightedScorer:

    @pytest.mark.asyncio
    async def test_equal_weights(self):
        """等权重 → 等价平均"""
        scorer = WeightedScorer(node_id="s1", config={"weights": [1, 1, 1], "normalize": True})
        result = await scorer.execute({}, _make_multi_input(40, 60, 80))
        assert result.score == pytest.approx(60.0)

    @pytest.mark.asyncio
    async def test_custom_weights(self):
        """自定义权重"""
        scorer = WeightedScorer(node_id="s1", config={
            "weights": [0.5, 0.3, 0.2],
            "normalize": True,
        })
        result = await scorer.execute({}, _make_multi_input(100, 50, 0))
        # 100*0.5 + 50*0.3 + 0*0.2 = 50 + 15 = 65
        assert result.score == pytest.approx(65.0)

    @pytest.mark.asyncio
    async def test_no_normalize_clamped(self):
        """不归一化时分数超过 100 被截断"""
        scorer = WeightedScorer(node_id="s1", config={
            "weights": [2, 1],
            "normalize": False,
        })
        result = await scorer.execute({}, _make_multi_input(60, 40))
        # 60*2 + 40*1 = 160, clamped to 100 by base scorer
        assert result.score == 100.0

    @pytest.mark.asyncio
    async def test_default_equal_weights(self):
        """未配置权重时使用等权重"""
        scorer = WeightedScorer(node_id="s1")
        result = await scorer.execute({}, _make_multi_input(50, 100))
        assert result.score == pytest.approx(75.0)

    @pytest.mark.asyncio
    async def test_weights_more_than_scores(self):
        """权重数量多于分数数量 → 截取"""
        scorer = WeightedScorer(node_id="s1", config={
            "weights": [0.5, 0.3, 0.2],
            "normalize": True,
        })
        result = await scorer.execute({}, _make_multi_input(80, 20))
        # 只用前 2 个权重: 80*0.5 + 20*0.3 = 46, / (0.5+0.3) = 57.5
        assert result.score == pytest.approx(57.5)

    @pytest.mark.asyncio
    async def test_weights_less_than_scores(self):
        """权重数量少于分数数量 → 填充 1.0"""
        scorer = WeightedScorer(node_id="s1", config={
            "weights": [2],
            "normalize": True,
        })
        result = await scorer.execute({}, _make_multi_input(30, 15))
        # 权重 [2, 1], 归一化: 30*2 + 15*1 / (2+1) = 75/3 = 25
        assert result.score == pytest.approx(25.0)

    @pytest.mark.asyncio
    async def test_no_inputs(self):
        """无输入 → 0"""
        scorer = WeightedScorer(node_id="s1")
        result = await scorer.execute({}, {})
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_zero_weights(self):
        """零权重 → 0"""
        scorer = WeightedScorer(node_id="s1", config={
            "weights": [0, 0],
            "normalize": True,
        })
        result = await scorer.execute({}, _make_multi_input(80, 20))
        assert result.score == 0.0

    def test_validate_config_ok(self):
        scorer = WeightedScorer()
        assert scorer.validate_config({"weights": [1, 2, 3]}) == []

    def test_validate_config_not_list(self):
        scorer = WeightedScorer()
        errors = scorer.validate_config({"weights": "not_a_list"})
        assert len(errors) > 0

    def test_validate_config_negative_weight(self):
        scorer = WeightedScorer()
        errors = scorer.validate_config({"weights": [1, -1]})
        assert len(errors) > 0

    def test_category(self):
        assert WeightedScorer.category == NodeCategory.SCORING

    def test_registered(self):
        from nodes.base import NodeRegistry
        NodeRegistry.register(WeightedScorer)
        assert NodeRegistry.get("weighted_scorer") is WeightedScorer
