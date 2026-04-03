"""tests/nodes/test_detectors/test_address_age.py — AddressAgeDetector 测试"""

import pytest

from nodes.detectors.address_age import AddressAgeDetector
from nodes.base import NodeOutput, NodeCategory


def _make_inputs(context: dict):
    out = NodeOutput(node_id="t1", node_type="input", score=0, passed=True, context=context)
    return {"input": [out]}


class TestAddressAgeDetector:

    @pytest.mark.asyncio
    async def test_very_new_address(self):
        """地址创建 < 1 天 → 90"""
        det = AddressAgeDetector(node_id="d1")
        ctx = {"from_address": "0xabc", "address_age_days": 0}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 90
        assert "VERY_NEW_ADDRESS" in output.context["detection"]["detected_issues"]

    @pytest.mark.asyncio
    async def test_new_address(self):
        """地址创建 < 7 天 → 70"""
        det = AddressAgeDetector(node_id="d1")
        ctx = {"from_address": "0xabc", "address_age_days": 3}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 70
        assert "NEW_ADDRESS" in output.context["detection"]["detected_issues"]

    @pytest.mark.asyncio
    async def test_recently_created(self):
        """地址创建 < 14 天 → 40"""
        det = AddressAgeDetector(node_id="d1")
        ctx = {"from_address": "0xabc", "address_age_days": 10}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 40
        assert "RECENTLY_CREATED_ADDRESS" in output.context["detection"]["detected_issues"]

    @pytest.mark.asyncio
    async def test_old_address(self):
        """地址创建很久 → 低分"""
        det = AddressAgeDetector(node_id="d1")
        ctx = {"from_address": "0xabc", "address_age_days": 365}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 10
        assert output.context["detection"]["detected_issues"] == []

    @pytest.mark.asyncio
    async def test_no_address(self):
        """无地址 → 0"""
        det = AddressAgeDetector(node_id="d1")
        ctx = {}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 0.0

    @pytest.mark.asyncio
    async def test_no_age_data(self):
        """有地址但无年龄数据 → 0"""
        det = AddressAgeDetector(node_id="d1")
        ctx = {"from_address": "0xabc"}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 0.0
        assert "no age data" in output.context["detection"]["reason"]

    @pytest.mark.asyncio
    async def test_uses_exploiter_address(self):
        """优先使用 exploiter_address"""
        det = AddressAgeDetector(node_id="d1")
        ctx = {"exploiter_address": "0xexploit", "from_address": "0xnormal", "address_age_days": 0}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 90

    @pytest.mark.asyncio
    async def test_create_time_string(self):
        """使用 address_create_time 字符串"""
        from datetime import datetime, timezone, timedelta
        det = AddressAgeDetector(node_id="d1")
        create_time = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
        ctx = {"from_address": "0xabc", "address_create_time": create_time}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 90  # < 1 day

    @pytest.mark.asyncio
    async def test_custom_threshold_days(self):
        """自定义阈值天数"""
        det = AddressAgeDetector(node_id="d1", config={"new_address_threshold_days": 30})
        ctx = {"from_address": "0xabc", "address_age_days": 20}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 70  # 20 < 30 → NEW_ADDRESS

    def test_category(self):
        assert AddressAgeDetector.category == NodeCategory.DETECTION

    def test_registered(self):
        from nodes.base import NodeRegistry
        assert NodeRegistry.get("address_age_detector") is AddressAgeDetector
