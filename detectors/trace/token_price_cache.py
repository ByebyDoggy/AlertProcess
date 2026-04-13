"""
Token 元数据缓存（价格 + 精度）— v2 全量拉取模式
=============================================
从 MarketDataBase 每 5 分钟后台拉取一次全量价格数据，
所有查询直接从内存中获取，确保零网络延迟。

架构:
  ┌──────────────┐  GET /tokens/all-prices  ┌──────────────────┐
  │ TokenPriceCache│ ◄────────────────────── │  MarketDataBase   │
  │ (内存缓存)    │     每 5 分钟全量拉取     │  REST API         │
  └──────┬───────┘                          └──────────────────┘
         │
         ├── get_price(chain, addr) → 直接读内存 → float | None
         └── batch_fetch(chain, addrs) → 直接读内存 → dict[addr, TokenMeta]

v1 → v2 变更:
  - 移除: 按需远程查询（每次 batch_fetch 可能触发 HTTP 调用）
  - 新增: 后台定时任务，每 300s 从 /api/v1/tokens/all-prices 拉取全部价格
  - 所有读操作纯内存，O(1) 复杂度
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# 默认 MarketDataBase 服务地址
DEFAULT_MARKET_DB_URL = "http://localhost:8002"

# 全量刷新间隔（秒）
FULL_REFRESH_INTERVAL = 300  # 5 分钟


@dataclass
class TokenMeta:
    """代币元数据"""
    symbol: str = ""
    name: str = ""
    decimals: int = 18
    price_usd: Optional[float] = None
    price_24h_change: Optional[float] = None
    logo_url: Optional[str] = None
    fetched_at: float = field(default_factory=time.time)

    @property
    def is_price_fresh(self) -> bool:
        """检查是否有价格数据（v2 中只要非 None 即为 fresh）"""
        return self.price_usd is not None and self.fetched_at > 0


# 链 ID ↔ 链名称映射
CHAIN_ID_TO_NAME = {
    1: "ethereum",
    56: "bsc",
    137: "polygon",
    42161: "arbitrum",
    10: "optimism",
    43114: "avalanche",
}

NAME_TO_CHAIN_ID = {v: k for k, v in CHAIN_ID_TO_NAME.items()}


# 原生代币默认信息（当 MarketDataBase 不可用时的 fallback）
NATIVE_TOKEN_DEFAULTS = {
    1: {"symbol": "ETH", "decimals": 18, "name": "Ethereum"},
    56: {"symbol": "BNB", "decimals": 18, "name": "BNB"},
    137: {"symbol": "MATIC", "decimals": 18, "name": "Polygon"},
    42161: {"symbol": "ETH", "decimals": 18, "name": "Arbitrum"},
    10: {"symbol": "ETH", "decimals": 18, "name": "Optimism"},
}


class TokenPriceCache:
    """
    进程内 Token 元数据缓存 — v2 全量拉取模式。

    Key 格式:
      - 内部存储: f"{chain_name}:{contract_address.lower()}"; 原生代币 address=""
      - 对外接口: 使用 chain_id，内部自动转换

    生命周期:
      start_background_refresh() → 启动后台循环（通常在应用启动时调用）
      close()                    → 关闭 HTTP 客户端和后台任务
    """

    def __init__(self, market_db_url: str = "", client: httpx.AsyncClient | None = None):
        """
        Args:
            market_db_url: MarketDataBase 服务地址，为空则使用默认值
            client: 外部注入的 HTTP 客户端（用于测试）
        """
        self._base_url = (market_db_url or DEFAULT_MARKET_DB_URL).rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._enabled = True

        # 核心内存存储: key="{chain_name}:{addr_lower}" -> TokenMeta
        self._cache: dict[str, TokenMeta] = {}

        # 链名→原生代币缓存 key (方便快速定位)
        self._native_keys: dict[str, str] = {}  # chain_name -> cache_key

        # 后台任务
        self._refresh_task: asyncio.Task | None = None
        self._running = False

        # 统计
        self._last_refresh_time: float = 0.0
        self._last_refresh_count: int = 0
        self._total_refreshes: int = 0

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value

    # ──── Key 工具方法 ────

    @staticmethod
    def _make_key(chain_id: int, token_address: str) -> str:
        """生成缓存 key。token_address 为空字符串表示原生代币"""
        chain_name = CHAIN_ID_TO_NAME.get(chain_id, "ethereum")
        return f"{chain_name}:{token_address.lower()}"

    @staticmethod
    def _chain_key_for(chain_id: int) -> str:
        """生成链级前缀用于批量查找"""
        chain_name = CHAIN_ID_TO_NAME.get(chain_id, "ethereum")
        return f"{chain_name}:"

    # ──── 公开读取接口（纯内存） ────

    def get(self, chain_id: int, token_address: str) -> TokenMeta | None:
        """从内存获取缓存的元数据"""
        key = self._make_key(chain_id, token_address)
        return self._cache.get(key)

    def get_price(self, chain_id: int, token_address: str) -> float | None:
        """快速获取价格（仅返回内存中的值）"""
        meta = self.get(chain_id, token_address)
        if meta and meta.is_price_fresh:
            return meta.price_usd
        return None

    async def batch_fetch(
        self,
        chain_id: int,
        addresses: list[str],
        include_native: bool = True,
    ) -> dict[str, TokenMeta]:
        """
        批量获取代币元数据 — v2 纯内存读取。

        所有数据直接从内存 _cache 读取，不触发任何远程请求。
        如果某地址不在缓存中，返回空的 TokenMeta。
        """
        if not self._enabled:
            return self._build_fallback_result(chain_id, addresses, include_native)

        result: dict[str, TokenMeta] = {}
        for addr in addresses:
            key = self._make_key(chain_id, addr)
            cached = self._cache.get(key)
            if cached:
                result[addr] = cached
            else:
                result[addr] = TokenMeta(decimals=18)

        if include_native:
            native_meta = self._get_native_from_cache(chain_id)
            result[""] = native_meta or TokenMeta(
                **NATIVE_TOKEN_DEFAULTS.get(chain_id, {"symbol": "ETH", "decimals": 18})
            )

        return result

    async def refresh_prices(
        self, chain_id: int, addresses: list[str], include_native: bool = True
    ):
        """
        v2 兼容接口：刷新请求被忽略（由后台统一管理），直接返回当前缓存。
        """
        logger.debug("[TokenPriceCache v2] refresh_prices() is no-op; background handles it")

    # ──── 后台全量拉取 ────

    async def start_background_refresh(self):
        """启动后台定时全量刷新任务"""
        if self._refresh_task and not self._refresh_task.done():
            logger.warning("[TokenPriceCache v2] Background refresh already running")
            return

        self._running = True
        self._refresh_task = asyncio.create_task(self._refresh_loop())
        logger.info(f"[TokenPriceCache v2] Background refresh started (interval={FULL_REFRESH_INTERVAL}s)")

        # 立即执行首次拉取
        await self._do_full_refresh()

    async def stop_background_refresh(self):
        """停止后台刷新任务"""
        self._running = False
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
        logger.info("[TokenPriceCache v2] Background refresh stopped")

    async def _refresh_loop(self):
        """后台刷新循环"""
        while self._running:
            try:
                await asyncio.sleep(FULL_REFRESH_INTERVAL)
                if self._running:
                    await self._do_full_refresh()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[TokenPriceCache v2] Refresh loop error: {e}")

    async def _do_full_refresh(self):
        """执行一次全量价格拉取并更新内存缓存"""
        t0 = time.time()
        try:
            url = f"{self._base_url}/api/v1/tokens/all-prices"
            logger.debug(f"[TokenPriceCache v2] Fetching: {url}")
            resp = await self._client.get(url)
            resp.raise_for_status()
            data = resp.json()
            chains_data = data.get("chains", {})
        except Exception as e:
            is_empty = len(self._cache) == 0
            level = logging.ERROR if is_empty else logging.WARNING
            logger.log(
                level,
                f"[TokenPriceCache v2] Full refresh FAILED (empty={is_empty}): {e}. "
                f"URL={self._base_url}/api/v1/tokens/all-prices — "
                f"Is MarketDataBase running? Has the /all-prices endpoint been deployed? "
                f"Existing cache: {len(self._cache)} entries",
            )
            return

        # 清空旧缓存，写入新数据
        old_count = len(self._cache)
        new_cache: dict[str, TokenMeta] = {}
        new_native_keys: dict[str, str] = {}
        now = time.time()

        for chain_name, tokens in chains_data.items():
            for tok in tokens:
                addr = tok.get("contract_address", "")
                key = f"{chain_name}:{addr}"
                meta = TokenMeta(
                    symbol=tok.get("symbol", ""),
                    name=tok.get("name", ""),
                    decimals=tok.get("decimals", 18),
                    price_usd=tok.get("price_usd"),
                    price_24h_change=tok.get("change_24h"),
                    logo_url=tok.get("logo_url", ""),
                    fetched_at=now,
                )
                new_cache[key] = meta

            # 记录该链的原生代币 key（如果有 __native__ 或空地址条目）
            native_key = f"{chain_name}:"
            if native_key not in new_native_keys:
                # 标记该链有数据，后续 get 时如果找不到具体地址也能知道链存在
                pass

        # 尝试提取各链原生代币信息
        for chain_name in chains_data.keys():
            # 用链上第一个代币的价格区域作为参考，实际原生代币需要单独处理
            # 这里先标记
            new_native_keys.setdefault(chain_name, f"{chain_name}:")

        self._cache = new_cache
        self._native_keys = new_native_keys
        elapsed = time.time() - t0
        self._last_refresh_time = now
        self._last_refresh_count = len(new_cache)
        self._total_refreshes += 1

        logger.info(
            f"[TokenPriceCache v2] Full refresh complete: "
            f"{old_count} -> {len(new_cache)} entries, "
            f"{elapsed:.2f}s, {self._total_refreshes} total refreshes"
        )

    def _get_native_from_cache(self, chain_id: int) -> TokenMeta | None:
        """尝试从缓存获取原生代币信息"""
        chain_name = CHAIN_ID_TO_NAME.get(chain_id, "")
        if not chain_name:
            return None

        # 策略1: 查找空地址的 native 条目
        native_key = f"{chain_name}:"
        native_cached = self._cache.get(native_key)
        if native_cached:
            return native_cached

        # 策略2: 用 WETH/WBNB/WMATIC 地址作为代理
        weth_proxies = {
            1: "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
            56: "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c",
            137: "0x7ceb23fd6bc0add59e62ac25578270cff1b9f619",
            42161: "0x82af49447d8a07e3bd95bd0d56f35241523fbab1",
            10: "0x4200000000000000000000000000000000000006",
        }
        proxy_addr = weth_proxies.get(chain_id, "")
        if proxy_addr:
            proxy_key = f"{chain_name}:{proxy_addr}"
            proxy_meta = self._cache.get(proxy_key)
            if proxy_meta and proxy_meta.price_usd is not None:
                defaults = NATIVE_TOKEN_DEFAULTS.get(chain_id, {})
                return TokenMeta(
                    symbol=defaults.get("symbol", proxy_meta.symbol or "ETH"),
                    name=defaults.get("name", proxy_meta.name or ""),
                    decimals=defaults.get("decimals", 18),
                    price_usd=proxy_meta.price_usd,
                    price_24h_change=proxy_meta.price_24h_change,
                    logo_url=proxy_meta.logo_url,
                    fetched_at=proxy_meta.fetched_at,
                )

        # 无数据
        defaults = NATIVE_TOKEN_DEFAULTS.get(chain_id, {})
        return TokenMeta(
            symbol=defaults.get("symbol", "ETH"),
            name=defaults.get("name", ""),
            decimals=defaults.get("decimals", 18),
            price_usd=None,
        )

    # ──── Fallback & 工具方法 ────

    def _build_fallback_result(
        self, chain_id: int, addresses: list[str], include_native: bool
    ) -> dict[str, TokenMeta]:
        """MarketDataBase 不可用时使用 fallback 数据（优先使用已有缓存）"""
        result: dict[str, TokenMeta] = {}

        for addr in addresses:
            cached = self.get(chain_id, addr)
            if cached:
                result[addr] = cached
            else:
                result[addr] = TokenMeta(decimals=18)

        if include_native:
            native_meta = self._get_native_from_cache(chain_id)
            result[""] = native_meta or TokenMeta(
                **NATIVE_TOKEN_DEFAULTS.get(chain_id, {"symbol": "ETH", "decimals": 18})
            )
        return result

    def clear(self):
        """清空所有缓存"""
        self._cache.clear()
        self._native_keys.clear()

    def stats(self) -> dict:
        """缓存统计信息"""
        total = len(self._cache)
        with_price = sum(1 for m in self._cache.values() if m.price_usd is not None)
        return {
            "mode": "v2-full-refresh",
            "total_entries": total,
            "with_price_data": with_price,
            "last_refresh_time": self._last_refresh_time,
            "last_refresh_count": self._last_refresh_count,
            "total_refreshes": self._total_refreshes,
            "background_running": self._running,
            "refresh_interval_seconds": FULL_REFRESH_INTERVAL,
        }

    async def close(self):
        """关闭 HTTP 客户端和后台任务"""
        await self.stop_background_refresh()
        await self._client.aclose()


# 全局单例
_global_cache: TokenPriceCache | None = None


def get_token_price_cache() -> TokenPriceCache:
    """获取全局单例（延迟初始化）"""
    global _global_cache
    if _global_cache is None:
        try:
            from config.model import settings
            url = settings.market_db_url
        except Exception:
            url = ""
        _global_cache = TokenPriceCache(market_db_url=url)
    return _global_cache
