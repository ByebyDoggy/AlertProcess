"""tests/nodes/test_detectors/test_arkm_label.py — ARKMLabelDetector 测试"""

import pytest

from nodes.detectors.arkm_label import ARKMLabelDetector
from nodes.base import NodeOutput, NodeCategory


def _make_inputs(context: dict):
    out = NodeOutput(node_id="t1", node_type="input", score=0, passed=True, context=context)
    return {"input": [out]}


class TestARKMLabelDetector:

    @pytest.mark.asyncio
    async def test_blacklisted_entity(self):
        """黑名单实体类型 → 95"""
        det = ARKMLabelDetector(node_id="d1")
        ctx = {"from_address": "0xabc", "entity_type": "hacker", "entity_name": "Bad Actor"}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 95
        assert "BLACKLISTED_ENTITY:hacker" in output.context["detection"]["detected_issues"]

    @pytest.mark.asyncio
    async def test_known_non_blacklisted(self):
        """已知实体但非黑名单 → 20"""
        det = ARKMLabelDetector(node_id="d1")
        ctx = {"from_address": "0xabc", "entity_type": "exchange", "entity_name": "Binance"}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 20
        assert "KNOWN_ENTITY:exchange" in output.context["detection"]["detected_issues"]

    @pytest.mark.asyncio
    async def test_ignored_entity(self):
        """忽略的实体类型 → 5"""
        det = ARKMLabelDetector(node_id="d1", config={"ignored_entity_types": ["exchange"]})
        ctx = {"from_address": "0xabc", "entity_type": "exchange"}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 5
        assert output.context["detection"]["detected_issues"] == []

    @pytest.mark.asyncio
    async def test_no_entity_data(self):
        """无实体数据 → 0"""
        det = ARKMLabelDetector(node_id="d1")
        ctx = {"from_address": "0xabc"}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 0.0
        assert "no entity data" in output.context["detection"]["reason"]

    @pytest.mark.asyncio
    async def test_no_address(self):
        """无地址 → 0"""
        det = ARKMLabelDetector(node_id="d1")
        ctx = {}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 0.0

    @pytest.mark.asyncio
    async def test_custom_blacklist(self):
        """自定义黑名单"""
        det = ARKMLabelDetector(node_id="d1", config={
            "blacklist_entity_types": ["phishing", "scam"],
        })
        ctx = {"from_address": "0xabc", "entity_type": "phishing"}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 95

    @pytest.mark.asyncio
    async def test_uses_exploiter_address(self):
        """优先使用 exploiter_address"""
        det = ARKMLabelDetector(node_id="d1")
        ctx = {"exploiter_address": "0xexploit", "from_address": "0xnormal", "entity_type": "hacker"}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 95

    @pytest.mark.asyncio
    async def test_entity_details_in_output(self):
        """输出包含实体详情"""
        det = ARKMLabelDetector(node_id="d1")
        ctx = {"from_address": "0xabc", "entity_type": "hacker",
               "entity_id": "123", "entity_name": "Bad Actor"}
        output = await det.execute(ctx, _make_inputs(ctx))
        det_info = output.context["detection"]
        assert det_info["entity_type"] == "hacker"
        assert det_info["entity_id"] == "123"
        assert det_info["entity_name"] == "Bad Actor"
        assert det_info["is_blacklisted"] is True

    def test_category(self):
        assert ARKMLabelDetector.category == NodeCategory.DETECTION

    def test_registered(self):
        from nodes.base import NodeRegistry
        assert NodeRegistry.get("arkm_label_detector") is ARKMLabelDetector
