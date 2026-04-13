"""
TokenPriceCache 单元测试
========================
测试缓存逻辑、batch_fetch、fallback 降级、TTL 过期等
"""
import time
import pytest
import httpx

from detectors.trace.token_price_cache import (
    TokenMeta,
    TokenPriceCache,
    NATIVE_TOKEN_DEFAULTS,
    PRICE_TTL_SECONDS,
)


# ================================================================
# TokenMeta 测试
# ================================================================

class TestTokenMeta:
    """TokenMeta 数据类测试"""

    def test_default_values(self):
        meta = TokenMeta()
        assert meta.symbol == ""
        assert meta.name == ""
        assert meta.decimals == 18
        assert meta.price_usd is None
        assert meta.price_24h_change is None
        assert meta.logo_url is None
        assert meta.fetched_at == 0.0

    def test_is_price_fresh_no_price(self):
        meta = TokenMeta()
        assert meta.is_price_fresh is False

    def test_is_price_fresh_just_fetched(self):
        meta = TokenMeta(price_usd=3500.0, fetched_at=time.time())
        assert meta.is_price_fresh is True

    def test_is_price_fresh_expired(self):
        meta = TokenMeta(
            price_usd=3500.0,
            fetched_at=time.time() - PRICE_TTL_SECONDS - 10,
        )
        assert meta.is_price_fresh is False

    def test_is_price_fresh_zero_fetched_at(self):
        meta = TokenMeta(price_usd=3500.0, fetched_at=0)
        assert meta.is_price_fresh is False


# ================================================================
# TokenPriceCache 基础测试（不依赖远程服务）
# ================================================================

class TestTokenPriceCacheBasic:
    """TokenPriceCache 基础缓存逻辑测试"""

    def _make_cache(self, enabled=False) -> TokenPriceCache:
        """创建禁用远程查询的缓存实例"""
        cache = TokenPriceCache(market_db_url="http://localhost:9999")
        cache.enabled = enabled
        return cache

    def test_make_key(self):
        key = TokenPriceCache._make_key(1, "0xabc123")
        assert key == "1:0xabc123"

    def test_make_key_native(self):
        key = TokenPriceCache._make_key(1, "")
        assert key == "1:"

    def test_get_empty_cache(self):
        cache = self._make_cache()
        result = cache.get(1, "0xabc")
        assert result is None

    def test_get_price_empty_cache(self):
        cache = self._make_cache()
        result = cache.get_price(1, "0xabc")
        assert result is None

    def test_get_price_fresh(self):
        cache = self._make_cache()
        meta = TokenMeta(price_usd=3500.0, fetched_at=time.time())
        cache._cache["1:0xabc"] = meta
        result = cache.get_price(1, "0xABC")  # 大小写不敏感
        assert result == 3500.0

    def test_get_price_stale(self):
        cache = self._make_cache()
        meta = TokenMeta(
            price_usd=3500.0,
            fetched_at=time.time() - PRICE_TTL_SECONDS - 10,
        )
        cache._cache["1:0xabc"] = meta
        result = cache.get_price(1, "0xabc")
        assert result is None

    def test_clear(self):
        cache = self._make_cache()
        cache._cache["1:0xabc"] = TokenMeta()
        cache.clear()
        assert len(cache._cache) == 0

    def test_stats(self):
        cache = self._make_cache()
        cache._cache["1:0xabc"] = TokenMeta(
            price_usd=100.0, fetched_at=time.time()
        )
        cache._cache["1:0xdef"] = TokenMeta(
            price_usd=200.0,
            fetched_at=time.time() - PRICE_TTL_SECONDS - 10,
        )
        stats = cache.stats()
        assert stats["total_entries"] == 2
        assert stats["fresh_price"] == 1
        assert stats["stale_price"] == 1
        assert stats["with_price_data"] == 2


# ================================================================
# Fallback 测试
# ================================================================

class TestTokenPriceCacheFallback:
    """MarketDataBase 不可用时的 fallback 逻辑"""

    def _make_cache(self) -> TokenPriceCache:
        cache = TokenPriceCache(market_db_url="http://localhost:99999")
        cache.enabled = False  # 禁用远程
        return cache

    @pytest.mark.asyncio
    async def test_fallback_returns_native_defaults(self):
        cache = self._make_cache()
        result = await cache.batch_fetch(
            chain_id=1, addresses=[], include_native=True
        )
        assert "" in result
        native = result[""]
        assert native.symbol == "ETH"
        assert native.decimals == 18

    @pytest.mark.asyncio
    async def test_fallback_unknown_addresses(self):
        cache = self._make_cache()
        result = await cache.batch_fetch(
            chain_id=1,
            addresses=["0xunknown123"],
            include_native=True,
        )
        # 未知地址应有空 meta
        assert "0xunknown123" in result
        assert result["0xunknown123"].symbol == ""

    @pytest.mark.asyncio
    async def test_fallback_bsc_native(self):
        cache = self._make_cache()
        result = await cache.batch_fetch(
            chain_id=56, addresses=[], include_native=True
        )
        assert result[""].symbol == "BNB"

    @pytest.mark.asyncio
    async def test_fallback_uses_cached_data(self):
        cache = self._make_cache()
        # 先手动缓存一个 token
        meta = TokenMeta(
            symbol="USDT", decimals=6, price_usd=1.0, fetched_at=time.time()
        )
        cache._cache["1:0xdac17f958d2ee523a2206206994597c13d831ec7"] = meta

        result = await cache.batch_fetch(
            chain_id=1,
            addresses=["0xdac17f958d2ee523a2206206994597c13d831ec7"],
            include_native=False,
        )
        usdt_addr = "0xdac17f958d2ee523a2206206994597c13d831ec7"
        assert usdt_addr in result
        assert result[usdt_addr].symbol == "USDT"
        assert result[usdt_addr].price_usd == 1.0


# ================================================================
# Mock 远程 API 测试
# ================================================================

class TestTokenPriceCacheRemote:
    """使用 mock httpx 测试远程 API 调用"""

    @pytest.fixture
    def mock_response(self):
        """构建一个标准的 batch-info 响应"""
        return {
            "success": True,
            "data": {
                "tokens": {
                    "0xdac17f958d2ee523a2206206994597c13d831ec7": {
                        "symbol": "USDT",
                        "name": "Tether USD",
                        "decimals": 6,
                        "price_usd": 1.0,
                        "price_usd_24h_change": 0.01,
                        "logo_url": "https://example.com/usdt.png",
                    },
                    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": {
                        "symbol": "WETH",
                        "name": "Wrapped Ether",
                        "decimals": 18,
                        "price_usd": 3499.50,
                        "price_usd_24h_change": 2.35,
                        "logo_url": "https://example.com/weth.png",
                    },
                },
                "__native__": {
                    "symbol": "ETH",
                    "name": "Ethereum",
                    "decimals": 18,
                    "price_usd": 3500.0,
                    "price_usd_24h_change": 2.40,
                    "logo_url": "https://example.com/eth.png",
                },
            },
            "metadata": {
                "total_requested": 2,
                "found": 2,
                "not_found": [],
                "data_timestamp": "2026-04-11T12:00:00Z",
                "source": "coingecko",
            },
        }

    @pytest.mark.asyncio
    async def test_batch_fetch_with_mock(self, mock_response):
        """测试通过 mock client 的 batch_fetch"""
        # 创建 mock AsyncClient
        mock_client = httpx.AsyncClient()

        # 拦截 post 请求
        original_post = mock_client.post

        async def mock_post(url, **kwargs):
            resp = httpx.Response(
                status_code=200,
                json=mock_response,
                request=httpx.Request("POST", url),
            )
            return resp

        mock_client.post = mock_post

        cache = TokenPriceCache(
            market_db_url="http://localhost:8002",
            client=mock_client,
        )

        result = await cache.batch_fetch(
            chain_id=1,
            addresses=[
                "0xdac17f958d2ee523a2206206994597c13d831ec7",
                "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
            ],
            include_native=True,
        )

        # 验证结果
        assert "0xdac17f958d2ee523a2206206994597c13d831ec7" in result
        assert "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2" in result
        assert "" in result  # native

        usdt = result["0xdac17f958d2ee523a2206206994597c13d831ec7"]
        assert usdt.symbol == "USDT"
        assert usdt.decimals == 6
        assert usdt.price_usd == 1.0
        assert usdt.logo_url == "https://example.com/usdt.png"

        weth = result["0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"]
        assert weth.symbol == "WETH"
        assert weth.decimals == 18
        assert weth.price_usd == 3499.50

        native = result[""]
        assert native.symbol == "ETH"
        assert native.price_usd == 3500.0
        assert native.logo_url == "https://example.com/eth.png"

        await mock_client.aclose()

    @pytest.mark.asyncio
    async def test_batch_fetch_caches_results(self, mock_response):
        """测试 batch_fetch 结果被缓存"""
        mock_client = httpx.AsyncClient()
        call_count = 0

        async def mock_post(url, **kwargs):
            nonlocal call_count
            call_count += 1
            resp = httpx.Response(
                status_code=200,
                json=mock_response,
                request=httpx.Request("POST", url),
            )
            return resp

        mock_client.post = mock_post

        cache = TokenPriceCache(
            market_db_url="http://localhost:8002",
            client=mock_client,
        )

        # 第一次调用
        await cache.batch_fetch(
            chain_id=1,
            addresses=["0xdac17f958d2ee523a2206206994597c13d831ec7"],
            include_native=True,
        )
        assert call_count == 1

        # 第二次调用 — 缓存命中（价格仍在 TTL 内）
        await cache.batch_fetch(
            chain_id=1,
            addresses=["0xdac17f958d2ee523a2206206994597c13d831ec7"],
            include_native=True,
        )
        assert call_count == 1  # 没有增加，缓存命中

        await mock_client.aclose()

    @pytest.mark.asyncio
    async def test_batch_fetch_partial_cache(self, mock_response):
        """测试部分缓存命中时的行为"""
        mock_client = httpx.AsyncClient()
        call_count = 0

        async def mock_post(url, **kwargs):
            nonlocal call_count
            call_count += 1
            resp = httpx.Response(
                status_code=200,
                json=mock_response,
                request=httpx.Request("POST", url),
            )
            return resp

        mock_client.post = mock_post

        cache = TokenPriceCache(
            market_db_url="http://localhost:8002",
            client=mock_client,
        )

        # 先缓存 USDT
        usdt_meta = TokenMeta(
            symbol="USDT", decimals=6, price_usd=1.0, fetched_at=time.time()
        )
        cache._cache["1:0xdac17f958d2ee523a2206206994597c13d831ec7"] = usdt_meta

        # 请求 USDT + WETH
        result = await cache.batch_fetch(
            chain_id=1,
            addresses=[
                "0xdac17f958d2ee523a2206206994597c13d831ec7",  # 已缓存
                "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",  # 未缓存
            ],
            include_native=True,
        )

        # 远程调用应该只查未缓存的 WETH
        assert call_count == 1

        # 两个都应该在结果中
        assert "0xdac17f958d2ee523a2206206994597c13d831ec7" in result
        assert "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2" in result

        await mock_client.aclose()

    @pytest.mark.asyncio
    async def test_batch_fetch_remote_failure_fallback(self):
        """测试远程调用失败时的 fallback"""
        mock_client = httpx.AsyncClient()

        async def mock_post(url, **kwargs):
            resp = httpx.Response(
                status_code=500,
                json={"detail": "Internal error"},
                request=httpx.Request("POST", url),
            )
            return resp

        mock_client.post = mock_post

        cache = TokenPriceCache(
            market_db_url="http://localhost:8002",
            client=mock_client,
        )

        result = await cache.batch_fetch(
            chain_id=1,
            addresses=["0xdac17f958d2ee523a2206206994597c13d831ec7"],
            include_native=True,
        )

        # 应该 fallback 到默认值
        assert "" in result
        assert result[""].symbol == "ETH"
        # 未知地址价格应为 None
        assert "0xdac17f958d2ee523a2206206994597c13d831ec7" in result

        await mock_client.aclose()


# ================================================================
# 价格计算公式测试
# ================================================================

class TestPriceCalculation:
    """验证 value_usd = (amount_raw / 10^decimals) * price_usd"""

    def test_eth_price_calculation(self):
        """ETH 余额变化的 USD 估值计算"""
        amount_raw = 65_361_960_326_939_766_177  # ~65.362 ETH
        decimals = 18
        price_usd = 3500.00
        expected = round(abs(amount_raw) / 10 ** decimals * price_usd, 2)
        # 65.361960326939766177 * 3500 ≈ 228,766.86
        assert abs(expected - 228766.86) < 1

    def test_usdt_price_calculation(self):
        """USDT 余额变化的 USD 估值计算"""
        amount_raw = 15_000_000  # 15 USDT (6 decimals)
        decimals = 6
        price_usd = 1.00
        expected = round(abs(amount_raw) / 10 ** decimals * price_usd, 2)
        assert expected == 15.0

    def test_weth_price_calculation(self):
        """WETH 余额变化的 USD 估值计算"""
        amount_raw = 2_305_427_700_000_000_000  # ~2.305 WETH
        decimals = 18
        price_usd = 3499.50
        expected = round(abs(amount_raw) / 10 ** decimals * price_usd, 2)
        # 2.3054277 * 3499.50 ≈ 8068.41
        assert abs(expected - 8068.41) < 1

    def test_uni_price_calculation(self):
        """UNI 余额变化的 USD 估值计算"""
        amount_raw = 5_000_000_000_000_000_000  # 5 UNI
        decimals = 18
        price_usd = 7.25
        expected = round(abs(amount_raw) / 10 ** decimals * price_usd, 2)
        assert expected == 36.25

    def test_no_price_returns_none(self):
        """无价格时 USD 估值应为 None"""
        amount_raw = 1_000_000_000_000_000_000
        decimals = 18
        price_usd = None
        value_usd = round(
            abs(amount_raw) / 10 ** decimals * (price_usd or 0), 2
        ) if price_usd else None
        assert value_usd is None


# ================================================================
# BalanceChangeItem to_dict 测试
# ================================================================

class TestBalanceChangeItemSerialization:
    """BalanceChangeItem 序列化测试"""

    def test_to_dict_with_price_and_logo(self):
        from detectors.trace.models import BalanceChangeItem

        item = BalanceChangeItem(
            address="0xabc",
            address_label="Test",
            token_address="0xdef",
            token_symbol="USDT",
            decimals=6,
            amount_raw=15_000_000,
            amount_formatted="+15.0000",
            value_usd=15.0,
            price_usd=1.0,
            logo_url="https://example.com/usdt.png",
        )

        d = item.to_dict()
        assert d["address"] == "0xabc"
        assert d["tokenSymbol"] == "USDT"
        assert d["valueUsd"] == 15.0
        assert d["priceUsd"] == 1.0
        assert d["logoUrl"] == "https://example.com/usdt.png"

    def test_to_dict_without_price_and_logo(self):
        from detectors.trace.models import BalanceChangeItem

        item = BalanceChangeItem(
            address="0xabc",
            token_symbol="UNKNOWN",
            decimals=18,
            amount_raw=1000,
        )

        d = item.to_dict()
        assert d["valueUsd"] is None
        assert d["priceUsd"] is None
        assert d["logoUrl"] is None

    def test_to_dict_native_eth(self):
        from detectors.trace.models import BalanceChangeItem

        item = BalanceChangeItem(
            address="0xabc",
            token_address="",
            token_symbol="ETH",
            decimals=18,
            amount_raw=1_000_000_000_000_000_000,
            amount_formatted="+1.0000",
            value_usd=3500.0,
            price_usd=3500.0,
            logo_url="https://example.com/eth.png",
        )

        d = item.to_dict()
        assert d["tokenAddress"] == ""
        assert d["tokenSymbol"] == "ETH"
        assert d["valueUsd"] == 3500.0
        assert d["priceUsd"] == 3500.0


# ================================================================
# WETH Fallback 测试
# ================================================================

class TestWETHFallback:
    """测试 MarketDataBase 未返回 __native__ 时使用 WETH 价格作为 fallback"""

    @pytest.mark.asyncio
    async def test_weth_fallback_when_no_native(self):
        """当 __native__ 缺失但 WETH 在结果中时，用 WETH 价格作为原生代币价格"""
        # 模拟 MarketDataBase 返回（不含 __native__，但含 WETH）
        mock_response_no_native = {
            "success": True,
            "data": {
                "tokens": {
                    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": {
                        "symbol": "WETH",
                        "name": "Wrapped Ether",
                        "decimals": 18,
                        "price_usd": 2246.42,
                        "price_usd_24h_change": -1.5,
                        "logo_url": "https://example.com/weth.png",
                    },
                },
            },
            "metadata": {
                "total_requested": 1,
                "found": 1,
                "not_found": [],
                "data_timestamp": "2026-04-11T12:00:00Z",
                "source": "coingecko",
            },
        }

        mock_client = httpx.AsyncClient()

        async def mock_post(url, **kwargs):
            resp = httpx.Response(
                status_code=200,
                json=mock_response_no_native,
                request=httpx.Request("POST", url),
            )
            return resp

        mock_client.post = mock_post

        cache = TokenPriceCache(
            market_db_url="http://localhost:8002",
            client=mock_client,
        )

        result = await cache.batch_fetch(
            chain_id=1,
            addresses=["0xdac17f958d2ee523a2206206994597c13d831ec7"],
            include_native=True,
        )

        # 应该有 native token（来自 WETH fallback）
        assert "" in result
        native = result[""]
        assert native.symbol == "ETH"
        assert native.price_usd == 2246.42  # WETH 的价格
        assert native.logo_url == "https://example.com/weth.png"
        assert native.decimals == 18

        await mock_client.aclose()

    @pytest.mark.asyncio
    async def test_weth_fallback_adds_weth_to_request(self):
        """测试 include_native=True 时自动将 WETH 地址加入请求"""
        captured_payload = {}

        mock_response_no_native = {
            "success": True,
            "data": {
                "tokens": {
                    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": {
                        "symbol": "WETH",
                        "name": "Wrapped Ether",
                        "decimals": 18,
                        "price_usd": 2246.42,
                    },
                },
            },
            "metadata": {"total_requested": 1, "found": 1, "not_found": [], "data_timestamp": "2026-04-11T12:00:00Z", "source": "coingecko"},
        }

        mock_client = httpx.AsyncClient()

        async def mock_post(url, **kwargs):
            captured_payload.update(kwargs.get("json", {}))
            resp = httpx.Response(
                status_code=200,
                json=mock_response_no_native,
                request=httpx.Request("POST", url),
            )
            return resp

        mock_client.post = mock_post

        cache = TokenPriceCache(
            market_db_url="http://localhost:8002",
            client=mock_client,
        )

        await cache.batch_fetch(
            chain_id=1,
            addresses=["0xdac17f958d2ee523a2206206994597c13d831ec7"],
            include_native=True,
        )

        # 验证 WETH 地址被自动添加到请求中
        addrs = captured_payload.get("contract_addresses", [])
        weth = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
        assert any(a.lower() == weth for a in addrs), f"WETH address not in request: {addrs}"

        await mock_client.aclose()
