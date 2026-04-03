"""tests/nodes/test_detectors/test_flash_loan.py — FlashLoanDetector 测试"""

import pytest

from nodes.detectors.flash_loan import FlashLoanDetector
from nodes.base import NodeOutput, NodeCategory


def _make_inputs(context: dict):
    out = NodeOutput(node_id="t1", node_type="input", score=0, passed=True, context=context)
    return {"input": [out]}


AAVE_V2 = "0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9"


class TestFlashLoanDetector:

    @pytest.mark.asyncio
    async def test_large_flash_loan_attack(self):
        """已知协议 + 大额交易 → 95"""
        det = FlashLoanDetector(node_id="d1", config={
            "large_flash_loan_threshold_usd": 10000,
            "chain_id_to_native_token_price": {1: 2000},
        })
        value = int(200000 / 2000 * 10**18)  # 200K USD
        ctx = {"to_address": AAVE_V2, "value": value, "input_data": "0x", "chain_id": 1}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 95

    @pytest.mark.asyncio
    async def test_flash_loan_protocol_method(self):
        """已知协议 + 闪电贷方法签名 → 80"""
        det = FlashLoanDetector(node_id="d1", config={
            "large_flash_loan_threshold_usd": 100000,
        })
        ctx = {
            "to_address": AAVE_V2,
            "value": 0,
            "input_data": "0x0906f8c8000000000000000000000",  # flash()
            "chain_id": 1,
        }
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 80

    @pytest.mark.asyncio
    async def test_flash_loan_protocol_only(self):
        """已知协议交互（无方法签名）→ 70"""
        det = FlashLoanDetector(node_id="d1")
        ctx = {"to_address": AAVE_V2, "value": 0, "input_data": "0x12345678", "chain_id": 1}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 70

    @pytest.mark.asyncio
    async def test_flash_loan_method_only(self):
        """闪电贷方法签名（非已知协议）→ 60"""
        det = FlashLoanDetector(node_id="d1")
        ctx = {
            "to_address": "0xdeadbeef",
            "value": 0,
            "input_data": "0x5c7d2920",  # flashLoan
            "chain_id": 1,
        }
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 60

    @pytest.mark.asyncio
    async def test_large_transfer(self):
        """大额交易（非闪电贷协议）→ 50"""
        det = FlashLoanDetector(node_id="d1", config={
            "large_flash_loan_threshold_usd": 10000,
            "chain_id_to_native_token_price": {1: 2000},
        })
        value = int(50000 / 2000 * 10**18)
        ctx = {"to_address": "0xdeadbeef", "value": value, "input_data": "0x", "chain_id": 1}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 50

    @pytest.mark.asyncio
    async def test_normal_transaction(self):
        """普通交易 → 0"""
        det = FlashLoanDetector(node_id="d1")
        ctx = {"to_address": "0xdeadbeef", "value": 100, "input_data": "0x", "chain_id": 1}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 0.0

    @pytest.mark.asyncio
    async def test_no_input_data(self):
        """无 input_data → 0"""
        det = FlashLoanDetector(node_id="d1")
        ctx = {"to_address": "0xdeadbeef", "chain_id": 1}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 0.0

    def test_category(self):
        assert FlashLoanDetector.category == NodeCategory.DETECTION

    def test_registered(self):
        from nodes.base import NodeRegistry
        assert NodeRegistry.get("flash_loan_detector") is FlashLoanDetector
