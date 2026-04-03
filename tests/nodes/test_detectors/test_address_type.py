"""tests/nodes/test_detectors/test_address_type.py — AddressTypeDetector 测试"""

import pytest

from nodes.detectors.address_type import AddressTypeDetector
from nodes.base import NodeOutput, NodeCategory

from nodes.triggers.alert_trigger import AlertTrigger


def _make_inputs(context: dict):
    out = NodeOutput(node_id="t1", node_type="input", score=0, passed=True, context=context)
    return {"input": [out]}


NULL_ADDR = "0x0000000000000000000000000000000000000000"


class TestAddressTypeDetector:

    @pytest.mark.asyncio
    async def test_null_to_address(self):
        """null to 地址 → 检测到"""
        det = AddressTypeDetector(node_id="d1")
        ctx = {"to_address": NULL_ADDR, "from_address": "0xaaa", "value": 0, "input_data": "0x"}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score > 0
        assert "NULL_TO_ADDRESS" in output.context.get("detection", {}).get("detected_issues", [])

    @pytest.mark.asyncio
    async def test_null_from_address(self):
        """null from 地址 → 高分"""
        det = AddressTypeDetector(node_id="d1")
        ctx = {"to_address": "0xbbb", "from_address": NULL_ADDR, "value": 0, "input_data": "0x"}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 90.0
        assert "NULL_FROM_ADDRESS" in output.context.get("detection", {}).get("detected_issues", [])

    @pytest.mark.asyncio
    async def test_contract_creation_with_value(self):
        """null to + value > 0 → 高分"""
        det = AddressTypeDetector(node_id="d1")
        ctx = {"to_address": NULL_ADDR, "from_address": "0xaaa", "value": 1000, "input_data": "0x"}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score >= 85.0

    @pytest.mark.asyncio
    async def test_contract_creation_with_data(self):
        """null to + input_data → 中等分"""
        det = AddressTypeDetector(node_id="d1")
        ctx = {"to_address": NULL_ADDR, "from_address": "0xaaa", "value": 0, "input_data": "0x1234"}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score >= 30.0

    @pytest.mark.asyncio
    async def test_normal_address(self):
        """正常地址 → 0 分"""
        det = AddressTypeDetector(node_id="d1")
        ctx = {"to_address": "0xabc", "from_address": "0xdef", "value": 100, "input_data": "0x"}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 0.0
        assert output.passed is False

    @pytest.mark.asyncio
    async def test_disable_checks(self):
        """禁用检测选项"""
        det = AddressTypeDetector(node_id="d1", config={
            "check_null_to": False,
            "check_null_from": False,
            "check_contract_creation": False,
        })
        ctx = {"to_address": NULL_ADDR, "from_address": NULL_ADDR, "value": 0, "input_data": "0x"}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 0.0

    @pytest.mark.asyncio
    async def test_case_insensitive_null(self):
        """null 地址比较大小写不敏感"""
        det = AddressTypeDetector(node_id="d1")
        ctx = {"to_address": NULL_ADDR.upper(), "from_address": "0xaaa", "value": 0, "input_data": "0x"}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score > 0

    def test_category(self):
        assert AddressTypeDetector.category == NodeCategory.DETECTION

    def test_registered(self):
        from nodes.base import NodeRegistry
        assert NodeRegistry.get("address_type_detector") is AddressTypeDetector
