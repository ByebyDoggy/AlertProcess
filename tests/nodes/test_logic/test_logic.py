"""tests/nodes/test_logic/test_logic.py — AND / OR Gate 测试"""

import pytest

from nodes.logic.and_gate import AndGate
from nodes.logic.or_gate import OrGate
from nodes.base import NodeOutput, NodeCategory


def _make_logic_inputs(*passed_values: bool):
    """构造多个布尔型输入"""
    inputs: dict[str, list[NodeOutput]] = {}
    for i, p in enumerate(passed_values):
        key = f"input_{i}"
        inputs[key] = [NodeOutput(
            node_id=f"up_{i}", node_type="comparison",
            score=100 if p else 0, passed=p,
        )]
    return inputs


class TestAndGate:

    @pytest.mark.asyncio
    async def test_all_true(self):
        gate = AndGate(node_id="and1")
        result = await gate.execute({}, _make_logic_inputs(True, True, True))
        assert result.passed is True
        assert result.score == 100.0

    @pytest.mark.asyncio
    async def test_one_false(self):
        gate = AndGate(node_id="and1")
        result = await gate.execute({}, _make_logic_inputs(True, False, True))
        assert result.passed is False
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_all_false(self):
        gate = AndGate(node_id="and1")
        result = await gate.execute({}, _make_logic_inputs(False, False))
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_single_true(self):
        gate = AndGate(node_id="and1")
        result = await gate.execute({}, _make_logic_inputs(True))
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_no_inputs(self):
        gate = AndGate(node_id="and1")
        result = await gate.execute({}, {})
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_details(self):
        gate = AndGate(node_id="and1")
        result = await gate.execute({}, _make_logic_inputs(True, False, True))
        assert result.context["logic_type"] == "and"
        assert result.context["matched_count"] == 2
        assert result.context["total_count"] == 3
        assert result.context["all_passed"] is False

    def test_category(self):
        assert AndGate.category == NodeCategory.LOGIC

    def test_registered(self):
        from nodes.base import NodeRegistry
        assert NodeRegistry.get("and_gate") is AndGate


class TestOrGate:

    @pytest.mark.asyncio
    async def test_all_true(self):
        gate = OrGate(node_id="or1")
        result = await gate.execute({}, _make_logic_inputs(True, True))
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_one_true(self):
        gate = OrGate(node_id="or1")
        result = await gate.execute({}, _make_logic_inputs(False, True, False))
        assert result.passed is True
        assert result.score == 100.0

    @pytest.mark.asyncio
    async def test_all_false(self):
        gate = OrGate(node_id="or1")
        result = await gate.execute({}, _make_logic_inputs(False, False))
        assert result.passed is False
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_no_inputs(self):
        gate = OrGate(node_id="or1")
        result = await gate.execute({}, {})
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_details(self):
        gate = OrGate(node_id="or1")
        result = await gate.execute({}, _make_logic_inputs(False, True, False))
        assert result.context["logic_type"] == "or"
        assert result.context["matched_count"] == 1
        assert result.context["any_passed"] is True

    def test_category(self):
        assert OrGate.category == NodeCategory.LOGIC

    def test_registered(self):
        from nodes.base import NodeRegistry
        assert NodeRegistry.get("or_gate") is OrGate
