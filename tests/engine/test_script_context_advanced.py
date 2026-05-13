"""
高级 ScriptContext API 单元测试
"""

import pytest

from engine.script_context import ScriptContext
from nodes.models import TransactionContext


class TestBalanceChanges:
    """测试余额变化追踪"""

    def test_get_balance_changes_basic(self):
        """测试基础余额变化计算"""
        tx_context = TransactionContext(
            chain_id="1",
            tx_hash="0xabc",
            block_number=100,
            timestamp="1000000",
            from_address="0xsender",
            to_address="0xcontract",
            value="0",
            logs=[],
            extra={
                "parsed_transfers": [
                    {
                        "token_address": "0xtoken1",
                        "from_address": "0xalice",
                        "to_address": "0xbob",
                        "amount": 100.0,
                    },
                    {
                        "token_address": "0xtoken1",
                        "from_address": "0xbob",
                        "to_address": "0xcharlie",
                        "amount": 50.0,
                    },
                ]
            },
        )

        ctx = ScriptContext(tx_context)
        changes = ctx.get_balance_changes()

        assert "0xtoken1" in changes
        assert changes["0xtoken1"]["0xalice"] == -100.0
        assert changes["0xtoken1"]["0xbob"] == 50.0
        assert changes["0xtoken1"]["0xcharlie"] == 50.0

    def test_get_balance_changes_filter_by_address(self):
        """测试按地址过滤余额变化"""
        tx_context = TransactionContext(
            chain_id="1",
            tx_hash="0xabc",
            block_number=100,
            timestamp="1000000",
            from_address="0xsender",
            to_address="0xcontract",
            value="0",
            logs=[],
            extra={
                "parsed_transfers": [
                    {
                        "token_address": "0xtoken1",
                        "from_address": "0xalice",
                        "to_address": "0xbob",
                        "amount": 100.0,
                    },
                ]
            },
        )

        ctx = ScriptContext(tx_context)
        changes = ctx.get_balance_changes(address="0xalice")

        assert "0xtoken1" in changes
        assert "0xalice" in changes["0xtoken1"]
        assert "0xbob" not in changes["0xtoken1"]

    def test_get_balance_changes_filter_by_token(self):
        """测试按代币过滤余额变化"""
        tx_context = TransactionContext(
            chain_id="1",
            tx_hash="0xabc",
            block_number=100,
            timestamp="1000000",
            from_address="0xsender",
            to_address="0xcontract",
            value="0",
            logs=[],
            extra={
                "parsed_transfers": [
                    {
                        "token_address": "0xtoken1",
                        "from_address": "0xalice",
                        "to_address": "0xbob",
                        "amount": 100.0,
                    },
                    {
                        "token_address": "0xtoken2",
                        "from_address": "0xalice",
                        "to_address": "0xbob",
                        "amount": 200.0,
                    },
                ]
            },
        )

        ctx = ScriptContext(tx_context)
        changes = ctx.get_balance_changes(token_address="0xtoken1")

        assert "0xtoken1" in changes
        assert "0xtoken2" not in changes

    def test_get_balance_changes_ignore_zero_address(self):
        """测试忽略零地址"""
        tx_context = TransactionContext(
            chain_id="1",
            tx_hash="0xabc",
            block_number=100,
            timestamp="1000000",
            from_address="0xsender",
            to_address="0xcontract",
            value="0",
            logs=[],
            extra={
                "parsed_transfers": [
                    {
                        "token_address": "0xtoken1",
                        "from_address": "0x0000000000000000000000000000000000000000",
                        "to_address": "0xbob",
                        "amount": 100.0,
                    },
                ]
            },
        )

        ctx = ScriptContext(tx_context)
        changes = ctx.get_balance_changes()

        assert "0xtoken1" in changes
        assert "0x0000000000000000000000000000000000000000" not in changes["0xtoken1"]
        assert changes["0xtoken1"]["0xbob"] == 100.0

    def test_get_balance_changes_caching(self):
        """测试缓存机制"""
        tx_context = TransactionContext(
            chain_id="1",
            tx_hash="0xabc",
            block_number=100,
            timestamp="1000000",
            from_address="0xsender",
            to_address="0xcontract",
            value="0",
            logs=[],
            extra={
                "parsed_transfers": [
                    {
                        "token_address": "0xtoken1",
                        "from_address": "0xalice",
                        "to_address": "0xbob",
                        "amount": 100.0,
                    },
                ]
            },
        )

        ctx = ScriptContext(tx_context)

        changes1 = ctx.get_balance_changes()
        changes2 = ctx.get_balance_changes()

        # 返回的字典是不同对象，但内容相同
        assert changes1 == changes2
        # 缓存的内部数据是同一个对象
        cache1 = ctx._balance_changes_cache
        cache2 = ctx._balance_changes_cache
        assert cache1 is cache2


class TestPriceImpact:
    """测试价格影响计算"""

    def test_calculate_price_impact_basic(self):
        """测试基础价格影响计算"""
        tx_context = TransactionContext(
            chain_id="1",
            tx_hash="0xabc",
            block_number=100,
            timestamp="1000000",
            from_address="0xsender",
            to_address="0xcontract",
            value="0",
            logs=[],
        )

        ctx = ScriptContext(tx_context)

        reserve_in = 1000000.0
        reserve_out = 1000000.0
        amount_in = 10000.0

        impact = ctx.calculate_price_impact(reserve_in, reserve_out, amount_in)

        assert impact < 0
        assert -2.0 < impact < 0.0

    def test_calculate_price_impact_large_trade(self):
        """测试大额交易价格影响"""
        tx_context = TransactionContext(
            chain_id="1",
            tx_hash="0xabc",
            block_number=100,
            timestamp="1000000",
            from_address="0xsender",
            to_address="0xcontract",
            value="0",
            logs=[],
        )

        ctx = ScriptContext(tx_context)

        reserve_in = 1000000.0
        reserve_out = 1000000.0
        amount_in = 100000.0

        impact = ctx.calculate_price_impact(reserve_in, reserve_out, amount_in)

        assert impact < -5.0

    def test_calculate_price_impact_custom_fee(self):
        """测试自定义手续费率"""
        tx_context = TransactionContext(
            chain_id="1",
            tx_hash="0xabc",
            block_number=100,
            timestamp="1000000",
            from_address="0xsender",
            to_address="0xcontract",
            value="0",
            logs=[],
        )

        ctx = ScriptContext(tx_context)

        reserve_in = 1000000.0
        reserve_out = 1000000.0
        amount_in = 10000.0

        impact_default = ctx.calculate_price_impact(reserve_in, reserve_out, amount_in)
        impact_high_fee = ctx.calculate_price_impact(reserve_in, reserve_out, amount_in, fee_rate=0.01)

        # 两者都应该是负值（价格下跌）
        assert impact_default < 0
        assert impact_high_fee < 0
        # 高手续费导致实际进入池子的金额更少，价格影响更小
        assert abs(impact_high_fee) < abs(impact_default)

    def test_calculate_price_impact_zero_reserves(self):
        """测试零储备量"""
        tx_context = TransactionContext(
            chain_id="1",
            tx_hash="0xabc",
            block_number=100,
            timestamp="1000000",
            from_address="0xsender",
            to_address="0xcontract",
            value="0",
            logs=[],
        )

        ctx = ScriptContext(tx_context)

        impact = ctx.calculate_price_impact(0, 1000000.0, 10000.0)
        assert impact == 0.0

        impact = ctx.calculate_price_impact(1000000.0, 0, 10000.0)
        assert impact == 0.0


class TestReentrancyDetection:
    """测试重入检测"""

    def test_detect_reentrancy_basic(self):
        """测试基础重入检测"""
        tx_context = TransactionContext(
            chain_id="1",
            tx_hash="0xabc",
            block_number=100,
            timestamp="1000000",
            from_address="0xsender",
            to_address="0xcontract",
            value="0",
            logs=[],
            extra={
                "eth_trace": {
                    "traces": [
                        {
                            "trace_address": [],
                            "action": {
                                "from_addr": "0xattacker",
                                "to_addr": "0xvictim",
                                "input_data": "0xa9059cbb",
                                "call_type": "call",
                            },
                        },
                        {
                            "trace_address": [0],
                            "action": {
                                "from_addr": "0xvictim",
                                "to_addr": "0xattacker",
                                "input_data": "0x12345678",
                                "call_type": "call",
                            },
                        },
                        {
                            "trace_address": [0, 0],
                            "action": {
                                "from_addr": "0xattacker",
                                "to_addr": "0xvictim",
                                "input_data": "0xa9059cbb",
                                "call_type": "call",
                            },
                        },
                    ]
                }
            },
        )

        ctx = ScriptContext(tx_context)
        patterns = ctx.detect_reentrancy()

        assert len(patterns) > 0
        assert patterns[0]["contract"] == "0xvictim"
        assert patterns[0]["pattern"] == "nested_call"

    def test_detect_reentrancy_target_contract(self):
        """测试指定目标合约的重入检测"""
        tx_context = TransactionContext(
            chain_id="1",
            tx_hash="0xabc",
            block_number=100,
            timestamp="1000000",
            from_address="0xsender",
            to_address="0xcontract",
            value="0",
            logs=[],
            extra={
                "eth_trace": {
                    "traces": [
                        {
                            "trace_address": [],
                            "action": {
                                "from_addr": "0xattacker",
                                "to_addr": "0xvictim",
                                "input_data": "0xa9059cbb",
                                "call_type": "call",
                            },
                        },
                        {
                            "trace_address": [0],
                            "action": {
                                "from_addr": "0xvictim",
                                "to_addr": "0xattacker",
                                "input_data": "0x12345678",
                                "call_type": "call",
                            },
                        },
                        {
                            "trace_address": [0, 0],
                            "action": {
                                "from_addr": "0xattacker",
                                "to_addr": "0xvictim",
                                "input_data": "0xa9059cbb",
                                "call_type": "call",
                            },
                        },
                    ]
                }
            },
        )

        ctx = ScriptContext(tx_context)
        patterns = ctx.detect_reentrancy(target_contract="0xvictim")

        assert len(patterns) > 0
        assert all(p["contract"] == "0xvictim" for p in patterns)

    def test_detect_reentrancy_no_pattern(self):
        """测试无重入模式"""
        tx_context = TransactionContext(
            chain_id="1",
            tx_hash="0xabc",
            block_number=100,
            timestamp="1000000",
            from_address="0xsender",
            to_address="0xcontract",
            value="0",
            logs=[],
            extra={
                "eth_trace": {
                    "traces": [
                        {
                            "trace_address": [],
                            "action": {
                                "from_addr": "0xalice",
                                "to_addr": "0xbob",
                                "input_data": "0xa9059cbb",
                                "call_type": "call",
                            },
                        },
                        {
                            "trace_address": [0],
                            "action": {
                                "from_addr": "0xbob",
                                "to_addr": "0xcharlie",
                                "input_data": "0x12345678",
                                "call_type": "call",
                            },
                        },
                    ]
                }
            },
        )

        ctx = ScriptContext(tx_context)
        patterns = ctx.detect_reentrancy()

        assert len(patterns) == 0

    def test_detect_reentrancy_empty_traces(self):
        """测试空调用栈"""
        tx_context = TransactionContext(
            chain_id="1",
            tx_hash="0xabc",
            block_number=100,
            timestamp="1000000",
            from_address="0xsender",
            to_address="0xcontract",
            value="0",
            logs=[],
        )

        ctx = ScriptContext(tx_context)
        patterns = ctx.detect_reentrancy()

        assert len(patterns) == 0
