"""tests/nodes/test_detectors/test_token_anomaly.py — TokenAnomalyDetector 测试"""

import pytest

from nodes.detectors.token_anomaly import TokenAnomalyDetector
from nodes.base import NodeOutput, NodeCategory


def _make_inputs(context: dict):
    out = NodeOutput(node_id="t1", node_type="input", score=0, passed=True, context=context)
    return {"input": [out]}


NULL_ADDR = "0x0000000000000000000000000000000000000000"


def _transfer_data(to: str, amount: int) -> str:
    """构造 transfer(address,uint256) 调用数据"""
    return "0xa9059cbb" + "0" * 24 + to[2:] + format(amount, '064x')


class TestTokenAnomalyDetector:

    @pytest.mark.asyncio
    async def test_large_eth_transfer(self):
        """大额 ETH 转账到 null 地址 → 80"""
        det = TokenAnomalyDetector(node_id="d1", config={
            "large_transfer_threshold": 100,
        })
        # value_eth = 200 ETH > 100 threshold
        value = 200 * 10**18
        ctx = {"to_address": NULL_ADDR, "value": value, "input_data": "0x"}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 80

    @pytest.mark.asyncio
    async def test_large_token_transfer(self):
        """大额 ERC20 转账 → 80"""
        det = TokenAnomalyDetector(node_id="d1", config={
            "large_transfer_threshold": 1000,
        })
        input_data = _transfer_data("0xabc" + "0" * 37, 2000)
        ctx = {"to_address": "0xdead", "value": 0, "input_data": input_data}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 80
        issues = output.context["detection"]["detected_issues"]
        assert any("LARGE_TOKEN_TRANSFER" in i for i in issues)

    @pytest.mark.asyncio
    async def test_new_token_activity(self):
        """新代币活动 → 60"""
        det = TokenAnomalyDetector(node_id="d1", config={
            "new_token_block": {1: 17000000},
        })
        ctx = {"to_address": "0xdead", "value": 0, "input_data": "0x",
               "block_number": 17050000, "chain_id": 1}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 60
        assert "NEW_TOKEN_ACTIVITY" in output.context["detection"]["detected_issues"]

    @pytest.mark.asyncio
    async def test_unusual_contract_interaction(self):
        """异常合约交互 → 30"""
        det = TokenAnomalyDetector(node_id="d1")
        ctx = {"to_address": "0xdead", "value": 0, "input_data": "0x12345678"}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 30
        assert "UNUSUAL_CONTRACT_INTERACTION" in output.context["detection"]["detected_issues"]

    @pytest.mark.asyncio
    async def test_normal_transfer(self):
        """普通交易 → 0"""
        det = TokenAnomalyDetector(node_id="d1")
        ctx = {"to_address": "0xdead", "value": 100, "input_data": "0x"}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 0.0

    @pytest.mark.asyncio
    async def test_null_to_without_large_value(self):
        """null to 但 value 不大 → 不会触发 LARGE_ETH_TRANSFER"""
        det = TokenAnomalyDetector(node_id="d1", config={
            "large_transfer_threshold": 1000000,
        })
        value = 10 * 10**18  # 10 ETH
        ctx = {"to_address": NULL_ADDR, "value": value, "input_data": "0x"}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert "LARGE_ETH_TRANSFER" not in output.context["detection"].get("detected_issues", [])

    @pytest.mark.asyncio
    async def test_block_number_too_old(self):
        """旧区块 → 不会触发 NEW_TOKEN_ACTIVITY"""
        det = TokenAnomalyDetector(node_id="d1", config={
            "new_token_block": {1: 17000000},
        })
        ctx = {"to_address": "0xdead", "value": 0, "input_data": "0x",
               "block_number": 19000000, "chain_id": 1}
        output = await det.execute(ctx, _make_inputs(ctx))
        issues = output.context["detection"].get("detected_issues", [])
        assert "NEW_TOKEN_ACTIVITY" not in issues

    @pytest.mark.asyncio
    async def test_max_score_takes_priority(self):
        """多个检测同时命中时取最高分"""
        det = TokenAnomalyDetector(node_id="d1", config={
            "large_transfer_threshold": 100,
            "new_token_block": {1: 17000000},
        })
        value = 200 * 10**18
        ctx = {"to_address": NULL_ADDR, "value": value, "input_data": "0x",
               "block_number": 17050000, "chain_id": 1}
        output = await det.execute(ctx, _make_inputs(ctx))
        # LARGE_ETH_TRANSFER(80) and NEW_TOKEN_ACTIVITY(60) → max is 80
        assert output.score == 80

    def test_category(self):
        assert TokenAnomalyDetector.category == NodeCategory.DETECTION

    def test_registered(self):
        from nodes.base import NodeRegistry
        assert NodeRegistry.get("token_anomaly_detector") is TokenAnomalyDetector
