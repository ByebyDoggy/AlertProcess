"""tests/nodes/test_comparators/test_threshold.py — ThresholdComparator 测试"""

import pytest

from nodes.comparators.threshold import ThresholdComparator
from nodes.base import NodeOutput, NodeCategory


def _make_input(score: float):
    return {"input_0": [NodeOutput(node_id="d1", node_type="detection", score=score)]}


class TestThresholdComparator:

    @pytest.mark.asyncio
    async def test_gte_passes(self):
        comp = ThresholdComparator(node_id="c1", config={"operator": "gte", "value": 50})
        result = await comp.execute({}, _make_input(75))
        assert result.score == 100.0
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_gte_fails(self):
        comp = ThresholdComparator(node_id="c1", config={"operator": "gte", "value": 50})
        result = await comp.execute({}, _make_input(30))
        assert result.score == 0.0
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_lt_passes(self):
        comp = ThresholdComparator(node_id="c1", config={"operator": "lt", "value": 50})
        result = await comp.execute({}, _make_input(30))
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_lt_fails(self):
        comp = ThresholdComparator(node_id="c1", config={"operator": "lt", "value": 50})
        result = await comp.execute({}, _make_input(75))
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_eq_passes(self):
        comp = ThresholdComparator(node_id="c1", config={"operator": "eq", "value": 50})
        result = await comp.execute({}, _make_input(50))
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_neq_passes(self):
        comp = ThresholdComparator(node_id="c1", config={"operator": "neq", "value": 50})
        result = await comp.execute({}, _make_input(30))
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_no_inputs(self):
        comp = ThresholdComparator(node_id="c1")
        result = await comp.execute({}, {})
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_boundary_exact(self):
        """边界值测试"""
        comp = ThresholdComparator(node_id="c1", config={"operator": "gte", "value": 50})
        result = await comp.execute({}, _make_input(50))
        assert result.passed is True

    def test_validate_config_ok(self):
        comp = ThresholdComparator()
        assert comp.validate_config({"operator": "gte", "value": 50}) == []

    def test_validate_config_invalid_operator(self):
        comp = ThresholdComparator()
        errors = comp.validate_config({"operator": "xyz"})
        assert len(errors) > 0

    def test_validate_config_value_out_of_range(self):
        comp = ThresholdComparator()
        errors = comp.validate_config({"value": 150})
        assert len(errors) > 0

    def test_category(self):
        assert ThresholdComparator.category == NodeCategory.COMPARISON

    def test_registered(self):
        from nodes.base import NodeRegistry
        assert NodeRegistry.get("threshold_comparator") is ThresholdComparator
