"""tests/nodes/test_comparators/test_range.py — RangeComparator 测试"""

import pytest

from nodes.comparators.range import RangeComparator
from nodes.base import NodeOutput, NodeCategory


def _make_input(score: float):
    return {"input_0": [NodeOutput(node_id="d1", node_type="detection", score=score)]}


class TestRangeComparator:

    @pytest.mark.asyncio
    async def test_inside_pass(self):
        comp = RangeComparator(node_id="c1", config={"min_value": 30, "max_value": 70, "mode": "inside"})
        result = await comp.execute({}, _make_input(50))
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_inside_fail_low(self):
        comp = RangeComparator(node_id="c1", config={"min_value": 30, "max_value": 70, "mode": "inside"})
        result = await comp.execute({}, _make_input(10))
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_inside_fail_high(self):
        comp = RangeComparator(node_id="c1", config={"min_value": 30, "max_value": 70, "mode": "inside"})
        result = await comp.execute({}, _make_input(90))
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_outside_pass(self):
        comp = RangeComparator(node_id="c1", config={"min_value": 30, "max_value": 70, "mode": "outside"})
        result = await comp.execute({}, _make_input(10))
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_outside_fail(self):
        comp = RangeComparator(node_id="c1", config={"min_value": 30, "max_value": 70, "mode": "outside"})
        result = await comp.execute({}, _make_input(50))
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_boundary_exact_min(self):
        comp = RangeComparator(node_id="c1", config={"min_value": 30, "max_value": 70})
        result = await comp.execute({}, _make_input(30))
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_boundary_exact_max(self):
        comp = RangeComparator(node_id="c1", config={"min_value": 30, "max_value": 70})
        result = await comp.execute({}, _make_input(70))
        assert result.passed is True

    def test_validate_config_min_gt_max(self):
        comp = RangeComparator()
        errors = comp.validate_config({"min_value": 100, "max_value": 30})
        assert len(errors) > 0

    def test_category(self):
        assert RangeComparator.category == NodeCategory.COMPARISON

    def test_registered(self):
        from nodes.base import NodeRegistry
        assert NodeRegistry.get("range_comparator") is RangeComparator
