"""tests/nodes/test_detectors/test_address_graph.py — AddressGraphDetector 测试"""

import pytest

from nodes.detectors.address_graph import AddressGraphDetector
from nodes.base import NodeOutput, NodeCategory


def _make_inputs(context: dict):
    out = NodeOutput(node_id="t1", node_type="input", score=0, passed=True, context=context)
    return {"input": [out]}


BINANCE = "0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be"
EXPLOITER = "0xab7535b4a1b3c2d2c7e7c7c7c7c7c7c7c7c7c7"


class TestAddressGraphDetector:

    @pytest.mark.asyncio
    async def test_exploiter_from_address(self):
        """已知攻击者 from → 95"""
        det = AddressGraphDetector(node_id="d1")
        ctx = {"from_address": EXPLOITER, "to_address": "0xdead", "chain_id": 1}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 95
        issues = output.context["detection"]["detected_issues"]
        assert any("EXPLOITER_ORIGIN" in i for i in issues)

    @pytest.mark.asyncio
    async def test_exploiter_to_address(self):
        """已知攻击者 to → 95"""
        det = AddressGraphDetector(node_id="d1")
        ctx = {"from_address": "0xdead", "to_address": EXPLOITER, "chain_id": 1}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 95
        issues = output.context["detection"]["detected_issues"]
        assert any("EXPLOITER_DESTINATION" in i for i in issues)

    @pytest.mark.asyncio
    async def test_exchange_from_address(self):
        """交易所 from → 40"""
        det = AddressGraphDetector(node_id="d1")
        ctx = {"from_address": BINANCE, "to_address": "0xdead", "chain_id": 1}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 40
        assert "EXCHANGE_ORIGIN:Binance" in output.context["detection"]["detected_issues"]

    @pytest.mark.asyncio
    async def test_exchange_to_address(self):
        """交易所 to → 40"""
        det = AddressGraphDetector(node_id="d1")
        ctx = {"from_address": "0xdead", "to_address": BINANCE, "chain_id": 1}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 40
        assert "EXCHANGE_DESTINATION:Binance" in output.context["detection"]["detected_issues"]

    @pytest.mark.asyncio
    async def test_both_exchange(self):
        """双方都是交易所 → 40（max，不叠加）"""
        det = AddressGraphDetector(node_id="d1")
        KRAKEN = "0x9696f03e6f8ead66a066d010c4ec4a437b41374f"
        ctx = {"from_address": BINANCE, "to_address": KRAKEN, "chain_id": 1}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 40  # max(40, 40) = 40

    @pytest.mark.asyncio
    async def test_normal_addresses(self):
        """普通地址 → 0"""
        det = AddressGraphDetector(node_id="d1")
        ctx = {"from_address": "0xaaa", "to_address": "0xbbb", "chain_id": 1}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 0.0

    @pytest.mark.asyncio
    async def test_default_threshold(self):
        """默认阈值 40 → exchange score=40 应 passed"""
        det = AddressGraphDetector(node_id="d1")
        ctx = {"from_address": BINANCE, "to_address": "0xdead", "chain_id": 1}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.passed is True  # 40 >= 40

    @pytest.mark.asyncio
    async def test_custom_threshold(self):
        """自定义阈值 50 → exchange score=40 不通过"""
        det = AddressGraphDetector(node_id="d1", config={"threshold": 50})
        ctx = {"from_address": BINANCE, "to_address": "0xdead", "chain_id": 1}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.passed is False  # 40 < 50

    def test_category(self):
        assert AddressGraphDetector.category == NodeCategory.DETECTION

    def test_registered(self):
        from nodes.base import NodeRegistry
        assert NodeRegistry.get("address_graph_detector") is AddressGraphDetector
