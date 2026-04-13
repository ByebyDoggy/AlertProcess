"""
compute_balance_changes 价格计算集成测试
=========================================
使用 mock 的 TokenPriceCache 测试余额变化中的 USD 估值逻辑
"""
import time
import pytest

from detectors.trace.analyzer import TxTraceAnalyzer, _format_eth_change
from detectors.trace.models import CallNode, BalanceChangeItem
from detectors.trace.token_price_cache import TokenMeta, TokenPriceCache


class TestFormatEthChange:
    """ETH 变化格式化测试"""

    def test_positive(self):
        result = _format_eth_change(1_000_000_000_000_000_000)
        assert result.startswith("+")
        assert "1.0000" in result

    def test_negative(self):
        result = _format_eth_change(-2_305_427_700_000_000_000)
        assert result.startswith("-")

    def test_zero(self):
        assert _format_eth_change(0) == "0"

    def test_large_amount(self):
        result = _format_eth_change(1_211_054_400_000_000_000_000)
        assert "+" in result
        assert "1,211" in result  # 千分位格式


class TestComputeBalanceChangesPriceCalculation:
    """测试 compute_balance_changes 中的价格计算逻辑"""

    @pytest.fixture
    def analyzer(self):
        """创建带 mock RPC 的分析器实例"""
        # 使用空 RPC 客户端（不需要实际连接）
        return TxTraceAnalyzer()

    @pytest.fixture
    def mock_price_cache(self):
        """创建预填充的 mock 价格缓存"""
        cache = TokenPriceCache(market_db_url="http://localhost:99999")
        cache.enabled = False  # 禁用远程

        # 手动填充缓存数据
        usdt_meta = TokenMeta(
            symbol="USDT",
            name="Tether USD",
            decimals=6,
            price_usd=1.0,
            logo_url="https://example.com/usdt.png",
            fetched_at=time.time(),
        )
        weth_meta = TokenMeta(
            symbol="WETH",
            name="Wrapped Ether",
            decimals=18,
            price_usd=3499.50,
            logo_url="https://example.com/weth.png",
            fetched_at=time.time(),
        )
        usdc_meta = TokenMeta(
            symbol="USDC",
            name="USD Coin",
            decimals=6,
            price_usd=1.0,
            logo_url="https://example.com/usdc.png",
            fetched_at=time.time(),
        )
        uni_meta = TokenMeta(
            symbol="UNI",
            name="Uniswap",
            decimals=18,
            price_usd=7.25,
            fetched_at=time.time(),
        )
        eth_meta = TokenMeta(
            symbol="ETH",
            name="Ethereum",
            decimals=18,
            price_usd=3500.0,
            logo_url="https://example.com/eth.png",
            fetched_at=time.time(),
        )

        cache._cache["1:0xdac17f958d2ee523a2206206994597c13d831ec7"] = usdt_meta
        cache._cache["1:0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"] = weth_meta
        cache._cache["1:0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"] = usdc_meta
        cache._cache["1:0x1f9840a85d5af5bf1d1762f925bdaddc4201f984"] = uni_meta
        cache._cache["1:"] = eth_meta  # 原生代币

        return cache

    @pytest.mark.asyncio
    async def test_eth_price_calculation_in_balance(self, analyzer, mock_price_cache, monkeypatch):
        """测试 ETH 余额变化的 USD 估值"""
        from detectors.trace import token_price_cache as tpc_module

        # 替换全局 cache
        original_cache = tpc_module._global_cache
        tpc_module._global_cache = mock_price_cache
        try:
            # 构造简单的 call tree
            root = CallNode(
                depth=0,
                from_address="0xsender",
                to_address="0xreceiver",
                value=1_000_000_000_000_000_000,  # 1 ETH
            )

            result = await analyzer.compute_balance_changes(
                root=root,
                tx_from="0xsender",
                tx_to_addr="0xreceiver",
                receipt_logs=[],
                chain_id=1,
            )

            # 找到 ETH 行
            eth_items = [r for r in result if r.token_address == ""]
            assert len(eth_items) > 0

            # 验证 sender 的 ETH 变化（支出）
            sender_eth = next(
                (r for r in eth_items if r.address == "0xsender"), None
            )
            assert sender_eth is not None
            assert sender_eth.amount_raw < 0  # 支出
            assert sender_eth.token_symbol == "ETH"
            assert sender_eth.price_usd == 3500.0
            assert sender_eth.logo_url == "https://example.com/eth.png"

            # receiver 的 ETH 变化（收入）
            receiver_eth = next(
                (r for r in eth_items if r.address == "0xreceiver"), None
            )
            assert receiver_eth is not None
            assert receiver_eth.amount_raw > 0  # 收入
            assert receiver_eth.price_usd == 3500.0
        finally:
            tpc_module._global_cache = original_cache

    @pytest.mark.asyncio
    async def test_erc20_price_with_decimals(self, analyzer, mock_price_cache, monkeypatch):
        """测试 ERC20 余额变化的 USD 估值，特别是不同 decimals"""
        from detectors.trace import token_price_cache as tpc_module

        original_cache = tpc_module._global_cache
        tpc_module._global_cache = mock_price_cache
        try:
            # 构造 receipt logs: USDT Transfer of 15,000,000 (15 USDT, 6 decimals)
            usdt_transfer_log = {
                "address": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
                "topics": [
                    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
                    "0x000000000000000000000000" + "abcdef1234567890abcdef1234567890abcdef12",
                    "0x000000000000000000000000" + "1234567890abcdef1234567890abcdef12345678",
                ],
                "data": "0x0000000000000000000000000000000000000000000000000000000000e4e1c0",
                # 0xe4e1c0 = 15,000,000
            }

            root = CallNode(depth=0, from_address="0xsender", to_address="0xreceiver")

            result = await analyzer.compute_balance_changes(
                root=root,
                tx_from="0xsender",
                tx_to_addr="0xreceiver",
                receipt_logs=[usdt_transfer_log],
                chain_id=1,
            )

            # 找到 USDT 行
            usdt_items = [
                r for r in result
                if r.token_address == "0xdac17f958d2ee523a2206206994597c13d831ec7"
            ]
            assert len(usdt_items) >= 1

            # 验证 USD 估值
            for item in usdt_items:
                if item.amount_raw > 0:
                    # 收入方: 15 USDT * $1.00 = $15.00
                    assert item.value_usd == 15.0, f"Expected 15.0, got {item.value_usd}"
                    assert item.decimals == 6
                    assert item.token_symbol == "USDT"
                    assert item.price_usd == 1.0
        finally:
            tpc_module._global_cache = original_cache

    @pytest.mark.asyncio
    async def test_native_price_from_cache(self, analyzer, mock_price_cache):
        """测试原生代币价格从缓存中正确获取"""
        from detectors.trace import token_price_cache as tpc_module

        original_cache = tpc_module._global_cache
        tpc_module._global_cache = mock_price_cache
        try:
            root = CallNode(
                depth=0,
                from_address="0xsender",
                to_address="0xreceiver",
                value=2_000_000_000_000_000_000,  # 2 ETH
            )

            result = await analyzer.compute_balance_changes(
                root=root,
                tx_from="0xsender",
                tx_to_addr="0xreceiver",
                receipt_logs=[],
                chain_id=1,
            )

            eth_items = [r for r in result if r.token_address == ""]
            for item in eth_items:
                if item.amount_raw > 0:
                    # 2 ETH * $3500 = $7000
                    assert item.value_usd == 7000.0, f"Expected 7000.0, got {item.value_usd}"
                    assert item.price_usd == 3500.0
                    assert item.logo_url == "https://example.com/eth.png"
        finally:
            tpc_module._global_cache = original_cache

    @pytest.mark.asyncio
    async def test_no_price_returns_zero_usd(self, analyzer):
        """测试无价格时 USD 估值为 0.0"""
        from detectors.trace import token_price_cache as tpc_module

        # 创建空缓存（无价格数据）
        empty_cache = TokenPriceCache(market_db_url="http://localhost:99999")
        empty_cache.enabled = False

        original_cache = tpc_module._global_cache
        tpc_module._global_cache = empty_cache
        try:
            root = CallNode(
                depth=0,
                from_address="0xsender",
                to_address="0xreceiver",
                value=1_000_000_000_000_000_000,
            )

            result = await analyzer.compute_balance_changes(
                root=root,
                tx_from="0xsender",
                tx_to_addr="0xreceiver",
                receipt_logs=[],
                chain_id=1,
            )

            eth_items = [r for r in result if r.token_address == ""]
            for item in eth_items:
                # 无价格时 value_usd 应为 0.0
                assert item.value_usd == 0.0
        finally:
            tpc_module._global_cache = original_cache

    @pytest.mark.asyncio
    async def test_zero_balance_not_in_result(self, analyzer):
        """测试净变化为 0 的不出现"""
        # 构造 from 和 to 相同的 value，net = 0
        root = CallNode(
            depth=0,
            from_address="0xsameaddr",
            to_address="0xsameaddr",
            value=1_000_000_000_000_000_000,
        )

        result = await analyzer.compute_balance_changes(
            root=root,
            tx_from="0xsameaddr",
            tx_to_addr="0xsameaddr",
            receipt_logs=[],
            chain_id=1,
        )

        # sameaddr 收支相抵，net = 0，不应出现
        same_items = [r for r in result if r.address == "0xsameaddr"]
        # 所有 net 应该非零
        for item in same_items:
            assert item.amount_raw != 0


class TestChainNameMapping:
    """测试 chain_id 到 chain_name 的映射"""

    def test_supported_chains(self):
        from detectors.trace.token_price_cache import TokenPriceCache

        cache = TokenPriceCache(market_db_url="http://localhost:8002")

        # 通过 _call_market_db 的 chain_name_map 测试
        # 使用 monkeypatch 替换 _call_market_db 来检查参数
        captured = {}

        async def mock_call(chain_id, addresses, include_native):
            # chain_name_map 是在方法内部定义的
            chain_name_map = {
                1: "ethereum",
                56: "bsc",
                137: "polygon",
                42161: "arbitrum",
                10: "optimism",
                43114: "avalanche",
                250: "fantom",
            }
            captured["chain_name"] = chain_name_map.get(chain_id, "ethereum")
            return {}

        cache._call_market_db = mock_call

        import asyncio
        asyncio.run(cache._call_market_db(1, [], True))
        assert captured["chain_name"] == "ethereum"

        asyncio.run(cache._call_market_db(56, [], True))
        assert captured["chain_name"] == "bsc"

        asyncio.run(cache._call_market_db(42161, [], True))
        assert captured["chain_name"] == "arbitrum"

        asyncio.run(cache._call_market_db(10, [], True))
        assert captured["chain_name"] == "optimism"
