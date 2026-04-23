"""tests/nodes/test_detectors/test_address_age.py — AddressAgeDetector 测试"""

import pytest
from datetime import datetime, timezone, timedelta

from nodes.detectors.address_age import AddressAgeDetector, _estimate_age_by_blocks
from nodes.base import NodeOutput, NodeCategory


def _make_inputs(context: dict):
    out = NodeOutput(node_id="t1", node_type="input", score=0, passed=True, context=context)
    return {"input": [out]}


def _days_ago(days: int) -> str:
    """生成 N 天前的 ISO 时间字符串"""
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


class TestAddressAgeDetector:

    @pytest.mark.asyncio
    async def test_very_new_address(self):
        """地址创建 < 1 天 → 90"""
        det = AddressAgeDetector(node_id="d1")
        ctx = {"from_address": "0xabc", "address_create_time": _days_ago(0)}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 90
        assert "VERY_NEW_ADDRESS" in output.context["detection"]["detected_issues"]

    @pytest.mark.asyncio
    async def test_new_address(self):
        """地址创建 < 阈值天数(3天) → 70"""
        det = AddressAgeDetector(node_id="d1")
        ctx = {"from_address": "0xabc", "address_create_time": _days_ago(2)}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 70
        assert "NEW_ADDRESS" in output.context["detection"]["detected_issues"]

    @pytest.mark.asyncio
    async def test_recently_created(self):
        """地址创建 < 2x阈值天数(3天) → 40"""
        det = AddressAgeDetector(node_id="d1")
        ctx = {"from_address": "0xabc", "address_create_time": _days_ago(4)}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 40
        assert "RECENTLY_CREATED_ADDRESS" in output.context["detection"]["detected_issues"]

    @pytest.mark.asyncio
    async def test_old_address(self):
        """地址创建很久 → 低分"""
        det = AddressAgeDetector(node_id="d1")
        ctx = {"from_address": "0xabc", "address_create_time": _days_ago(365)}
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
        ctx = {
            "exploiter_address": "0xexploit",
            "from_address": "0xnormal",
            "address_create_time": _days_ago(0),
        }
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 90

    @pytest.mark.asyncio
    async def test_create_time_string(self):
        """使用 address_create_time 字符串"""
        det = AddressAgeDetector(node_id="d1")
        create_time = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
        ctx = {"from_address": "0xabc", "address_create_time": create_time}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 90  # < 1 day

    @pytest.mark.asyncio
    async def test_custom_threshold_days(self):
        """自定义阈值天数"""
        det = AddressAgeDetector(node_id="d1", config={"new_address_threshold_days": 30})
        ctx = {"from_address": "0xabc", "address_create_time": _days_ago(20)}
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 70  # 20 < 30 → NEW_ADDRESS

    @pytest.mark.asyncio
    async def test_backtest_with_tx_timestamp(self):
        """回测模式: 使用 tx_timestamp 作为参考时间计算年龄"""
        from datetime import datetime, timezone, timedelta
        det = AddressAgeDetector(node_id="d1", config={"new_address_threshold_days": 7})

        # 假设交易发生在 2025-01-01，地址创建于 2024-12-27（5天前 < 阈值7）
        tx_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
        addr_created = (tx_time - timedelta(days=5)).isoformat()

        ctx = {
            "from_address": "0xabc",
            "address_create_time": addr_created,
            "tx_timestamp": tx_time.timestamp(),
        }
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 70  # 5 < 7 → NEW_ADDRESS

    @pytest.mark.asyncio
    async def test_block_estimate_priority(self):
        """区块估算优先于时间戳计算"""
        det = AddressAgeDetector(node_id="d1")

        ctx = {
            "from_address": "0xabc",
            "chain_id": 1,
            "block_number": 20000000,
            "first_block_number": 19995000,   # 差5000块 * 12s/块 = 60000s ≈ 0.7天
            "address_create_time": _days_ago(100),  # 时间戳显示100天（应被区块覆盖）
        }
        output = await det.execute(ctx, _make_inputs(ctx))
        # 区块差: 5000 * 12s = 60000s ≈ 0.69天 < 1天 → VERY_NEW
        assert output.score >= 70
        assert output.context["detection"]["age_method"] == "block_estimate"

    @pytest.mark.asyncio
    async def test_fallback_to_time_delta_when_no_blocks(self):
        """无 block_number 时回退到时间戳计算"""
        det = AddressAgeDetector(node_id="d1")
        ctx = {
            "from_address": "0xabc",
            "address_create_time": _days_ago(2),
            # 无 block_number 和 first_block_number
        }
        output = await det.execute(ctx, _make_inputs(ctx))
        assert output.score == 70  # 2 < 3 → NEW_ADDRESS
        assert output.context["detection"]["age_method"] == "time_delta"

    def test_category(self):
        assert AddressAgeDetector.category == NodeCategory.DETECTION

    def test_registered(self):
        from nodes.base import NodeRegistry
        assert NodeRegistry.get("address_age_detector") is AddressAgeDetector


class TestEstimateAgeByBlocks:

    def test_basic_estimate(self):
        ctx = {"chain_id": 1, "block_number": 20000000, "first_block_number": 19990000}
        result = _estimate_age_by_blocks(ctx)
        assert result is not None
        # 1000 blocks * 12s = 12000s / 86400 ≈ 0.14 days → int truncates to 0
        assert result <= 1

    def test_ethereum_30_days(self):
        """ETH 12s/block: 30天 ≈ 216000 blocks"""
        ctx = {"chain_id": 1, "block_number": 19216000, "first_block_number": 19000000}
        result = _estimate_age_by_blocks(ctx)
        # 216000 * 12 = 2592000s ≈ 30 days
        assert result is not None
        assert 29 <= result <= 31

    def test_missing_first_block(self):
        assert _estimate_age_by_blocks({"block_number": 100}) is None

    def test_missing_current_block(self):
        assert _estimate_age_by_blocks({"first_block_number": 100}) is None

    def test_invalid_chain(self):
        # chain_id 不是数字时应回退到默认 ETH (12s)
        ctx = {"chain_id": "bad", "block_number": 1100, "first_block_number": 100}
        result = _estimate_age_by_blocks(ctx)
        assert result is not None

    def test_reverse_order(self):
        """tx_block < first_block → 返回 None"""
        ctx = {"block_number": 100, "first_block_number": 200}
        assert _estimate_age_by_blocks(ctx) is None
