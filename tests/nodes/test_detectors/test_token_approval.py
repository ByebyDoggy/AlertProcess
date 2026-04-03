"""tests/nodes/test_detectors/test_token_approval.py — TokenApprovalDetector 测试"""

import pytest

from nodes.detectors.token_approval import TokenApprovalDetector
from nodes.base import NodeOutput, NodeCategory


def _make_inputs(context: dict):
    out = NodeOutput(node_id="t1", node_type="input", score=0, passed=True, context=context)
    return {"input": [out]}


def _approve_data(spender: str, amount: int) -> str:
    """构造 approve(address,uint256) 调用数据"""
    return "0x095ea7b3" + "0" * 24 + spender[2:] + format(amount, '064x')


def _set_approval_for_all(operator: str, approved: bool) -> str:
    """构造 setApprovalForAll(address,bool) 调用数据"""
    return "0xa22cb465" + "0" * 24 + operator[2:] + ("0" * 62 + "01" if approved else "0" * 64)


SPENDER = "0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9"  # Aave V2
UNKNOWN = "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"

# MAX_UINT256 hex (64 chars)
MAX_UINT256_HEX = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"


class TestTokenApprovalDetector:

    @pytest.mark.asyncio
    async def test_infinite_approval(self):
        """无限授权 → 80"""
        det = TokenApprovalDetector(node_id="d1")
        input_data = _approve_data(UNKNOWN, int(MAX_UINT256_HEX, 16))
        ctx = {"input_data": input_data}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score >= 80
        assert "INFINITE_APPROVAL" in output.context["detection"]["detected_issues"]

    @pytest.mark.asyncio
    async def test_approval_to_known_protocol(self):
        """授权给已知协议 → 40"""
        det = TokenApprovalDetector(node_id="d1")
        input_data = _approve_data(SPENDER, 1000)
        ctx = {"input_data": input_data}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 40  # spender is Aave V2 in SUSPICIOUS_APPROVAL_TARGETS

    @pytest.mark.asyncio
    async def test_approval_to_unknown(self):
        """授权给未知地址 → 50"""
        det = TokenApprovalDetector(node_id="d1", config={"check_approval_to_unknown": True})
        input_data = _approve_data(UNKNOWN, 1000)
        ctx = {"input_data": input_data}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 50
        assert "APPROVAL_TO_UNKNOWN_CONTRACT" in output.context["detection"]["detected_issues"]

    @pytest.mark.asyncio
    async def test_set_approval_for_all_approved(self):
        """setApprovalForAll(true) → 60"""
        det = TokenApprovalDetector(node_id="d1")
        input_data = _set_approval_for_all(UNKNOWN, True)
        ctx = {"input_data": input_data}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 60
        assert "APPROVAL_FOR_ALL_UNKNOWN" in output.context["detection"]["detected_issues"]

    @pytest.mark.asyncio
    async def test_set_approval_for_all_known(self):
        """setApprovalForAll to known protocol → 50"""
        det = TokenApprovalDetector(node_id="d1")
        input_data = _set_approval_for_all(SPENDER, True)
        ctx = {"input_data": input_data}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 50

    @pytest.mark.asyncio
    async def test_set_approval_for_all_revoke(self):
        """setApprovalForAll(false) → 0"""
        det = TokenApprovalDetector(node_id="d1")
        input_data = _set_approval_for_all(UNKNOWN, False)
        ctx = {"input_data": input_data}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 0.0

    @pytest.mark.asyncio
    async def test_not_approval_transaction(self):
        """非授权交易 → 0"""
        det = TokenApprovalDetector(node_id="d1")
        ctx = {"input_data": "0x12345678"}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 0.0

    @pytest.mark.asyncio
    async def test_empty_input_data(self):
        """空 input_data → 0"""
        det = TokenApprovalDetector(node_id="d1")
        ctx = {"input_data": "0x"}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 0.0

    @pytest.mark.asyncio
    async def test_check_approval_to_unknown_disabled(self):
        """禁用未知地址检测"""
        det = TokenApprovalDetector(node_id="d1", config={"check_approval_to_unknown": False})
        input_data = _approve_data(UNKNOWN, 1000)
        ctx = {"input_data": input_data}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 0.0  # no check for unknown

    def test_category(self):
        assert TokenApprovalDetector.category == NodeCategory.DETECTION

    def test_registered(self):
        from nodes.base import NodeRegistry
        assert NodeRegistry.get("token_approval_detector") is TokenApprovalDetector
