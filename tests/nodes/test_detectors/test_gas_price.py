"""tests/nodes/test_detectors/test_gas_price.py — GasPriceDetector 测试"""

import pytest

from nodes.detectors.gas_price import GasPriceDetector
from nodes.base import NodeOutput, NodeCategory

from nodes.triggers.alert_trigger import AlertTrigger


def _make_inputs(context: dict, score=0, passed=True):
    """构造上游输入"""
    trigger = AlertTrigger(node_id="t1")
    out = NodeOutput(node_id="t1", node_type="input", score=0, passed=True, context=context)
    return {"input": [out]}


class TestGasPriceDetector:

    @pytest.mark.asyncio
    async def test_extreme_gas(self):
        """极端 Gas 费 → 高分"""
        det = GasPriceDetector(node_id="d1", config={
            "high_gas_threshold_usd": 5,
            "extreme_gas_threshold_usd": 20,
            "chain_id_to_native_token_price": {1: 2000},
        })
        # 500 gwei * 21000 * 2000 = 21000 USD → extreme
        ctx = {"gas_price_gwei": 500, "gas_used": 21000, "chain_id": 1}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score >= 90
        assert output.passed is True
        assert "high_gas" in output.labels

    @pytest.mark.asyncio
    async def test_high_gas(self):
        """高 Gas 费 → 中等分"""
        det = GasPriceDetector(node_id="d1", config={
            "high_gas_threshold_usd": 5,
            "extreme_gas_threshold_usd": 20,
            "chain_id_to_native_token_price": {1: 2000},
        })
        # 50 gwei * 21000 * 2000 = 2.1 USD → below high (5)
        ctx = {"gas_price_gwei": 50, "gas_used": 21000, "chain_id": 1}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert 0 <= output.score < 50

    @pytest.mark.asyncio
    async def test_normal_gas(self):
        """正常 Gas → 低分"""
        det = GasPriceDetector(node_id="d1", config={
            "high_gas_threshold_usd": 5,
            "extreme_gas_threshold_usd": 20,
            "chain_id_to_native_token_price": {1: 2000},
        })
        # 5 gwei * 21000 * 2000 = 0.21 USD → very low
        ctx = {"gas_price_gwei": 5, "gas_used": 21000, "chain_id": 1}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score < 20
        assert output.passed is False

    @pytest.mark.asyncio
    async def test_no_gas_price(self):
        """context 中没有 gas_price → 0 分"""
        det = GasPriceDetector(node_id="d1")
        output = await det.execute({}, _make_inputs({}))
        assert output.score == 0.0
        assert output.passed is False

    @pytest.mark.asyncio
    async def test_score_clamped(self):
        """分数应在 0-100 范围内"""
        det = GasPriceDetector(node_id="d1", config={
            "extreme_gas_threshold_usd": 10,
            "chain_id_to_native_token_price": {1: 2000},
        })
        ctx = {"gas_price_gwei": 1000, "gas_used": 21000, "chain_id": 1}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert 0 <= output.score <= 100

    @pytest.mark.asyncio
    async def test_details_contain_gas_info(self):
        """输出应包含 gas 详情"""
        det = GasPriceDetector(node_id="d1", config={
            "chain_id_to_native_token_price": {1: 2000},
        })
        ctx = {"gas_price_gwei": 30, "gas_used": 21000, "chain_id": 1}
        output = await det.execute(ctx, _make_inputs(ctx))
        det_info = output.context.get("detection", {})
        assert "total_gas_usd" in det_info
        assert "gas_price_eth" in det_info

    def test_validate_config_ok(self):
        det = GasPriceDetector()
        assert det.validate_config({"high_gas_threshold_usd": 100, "extreme_gas_threshold_usd": 500}) == []

    def test_validate_config_extreme_le_high(self):
        det = GasPriceDetector()
        errors = det.validate_config({"high_gas_threshold_usd": 500, "extreme_gas_threshold_usd": 100})
        assert len(errors) > 0

    def test_validate_config_negative_threshold(self):
        det = GasPriceDetector()
        errors = det.validate_config({"high_gas_threshold_usd": -1})
        assert len(errors) > 0

    def test_category(self):
        assert GasPriceDetector.category == NodeCategory.DETECTION

    def test_registered(self):
        from nodes.base import NodeRegistry
        assert NodeRegistry.get("gas_price_detector") is GasPriceDetector
