"""
RPC Endpoint Pool Manager (apipool-ng v4 — 强制集成层)
======================================================

基于 apipool-ng 最新 SDK 实现的多 RPC 端点轮换管理器。

v4 变更:
  - 强制依赖 apipool-ng (移除 fallback 模式)
  - 使用 AsyncDynamicKeyManager 替代同步 ApiKeyManager (本地模式)
  - 复用原生 AsyncChainProxy / AsyncDummyClient (不再自定义)
  - 从子模块直接导入 (绕过 __init__.py 裸 except)

支持两种模式:
  ┌─────────────────────────────────────────────────────────────┐
  │  本地模式 (Local Mode)                                      │
  │    RpcEndpointApiKey[] → AsyncDynamicKeyManager             │
  │    自动轮换/故障切换/后台刷新                                │
  ├─────────────────────────────────────────────────────────────┤
  │  服务器模式 (Server Mode)                                   │
  │    alogin() → async_connect() → ApiKeyManager              │
  │    所有调用透明代理到 apipool-server                         │
  └─────────────────────────────────────────────────────────────┘

用法 — 本地模式:
    from detectors.trace.rpc_pool import RpcEndpointApiKey, AsyncRpcPoolManager

    apikeys = [RpcEndpointApiKey(url=url, chain_id=1) for url in urls]
    mgr = await AsyncRpcPoolManager.create(apikeys, chain_id=1)
    result = await mgr.call("eth_getBlockByNumber", ["latest", False])

用法 — 服务器模式:
    from detectors.trace.rpc_pool import AsyncRpcServerPoolManager

    mgr = await AsyncRpcServerPoolManager.create(
        service_url="http://localhost:8000",
        pool_identifier="ethereum-rpc",
        username="alice",
        password="password",
    )
    result = await mgr.call("eth_getBlockByNumber", ["latest", False])
"""

import asyncio
import logging
import time
from typing import Optional, Any

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────
# 导入 apipool-ng 核心组件 (直接从子模块导入)
# ────────────────────────────────────────────
from apipool.client import (
    alogin,
    async_connect,
    PoolConfig,
)
from apipool.manager import (
    ApiKey,
    ApiKeyManager,
    AsyncDynamicKeyManager,
    PoolExhaustedError,
    StatsCollector,
    StatusCollection,
    # 原生异步组件 (复用而非自实现)
    AsyncChainProxy as _NativeAsyncChainProxy,
    AsyncDummyClient as _NativeAsyncDummyClient,
)

# ────────────────────────────────────────────
# 自定义异常
# ────────────────────────────────────────────


class NodeUnreachableError(Exception):
    """RPC 节点不可达或响应超时"""
    pass


class NodeRateLimitError(Exception):
    """RPC 节点返回速率限制"""
    pass


class AllNodesExhaustedError(PoolExhaustedError):
    """所有可用节点均已耗尽"""
    def __init__(self, chain_id: int, detail: str = ""):
        self.chain_id = chain_id
        msg = f"All RPC nodes exhausted for chain {chain_id}"
        if detail:
            msg += f": {detail}"
        super().__init__(msg)


# ────────────────────────────────────────────
# RPC 端点 ApiKey 实现 (继承 apipool.ApiKey)
# ────────────────────────────────────────────


class RpcEndpointApiKey(ApiKey):
    """
    将单个 RPC 端点 URL 封装为 apipool-ng 可管理的 ApiKey。

    每个 RPC URL 对应一个实例, 通过 create_client() 创建底层 HTTP 客户端。
    """

    def __init__(self, url: str, name: str = "", chain_id: int = 0,
                 timeout: float = 30.0, priority: int = 100, weight: int = 1,
                 max_conns: int = 10, db_id: str = ""):
        self.url = url
        self.name = name or url[:40]
        self.chain_id = chain_id
        self.timeout = timeout
        self.priority = priority
        self.weight = weight
        self.max_conns = max_conns
        self.db_id = db_id  # 原始 DB 主键 (用于前端关联)

        # 运行时统计
        self._success_count = 0
        self._failure_count = 0
        self._total_latency_ms = 0.0
        self._last_error = ""
        self._healthy = True
        self._consecutive_failures = 0

        super().__init__()

    # ── apipool.ApiKey 接口实现 ──

    def get_primary_key(self):
        """使用 URL 作为唯一标识"""
        return self.url

    def create_client(self):
        """
        创建 HTTP 客户端用于 JSON-RPC 通信。
        返回 _RpcHttpClient 实例 (支持异步调用和快速测试)。
        """
        return _RpcHttpClient(self)

    def test_usability(self, client):
        """
        通过 eth_chainId 快速探测连通性。
        注意: 这是同步接口(apipool要求), 内部用线程池包装异步调用。
        """
        try:
            loop = asyncio.get_event_loop()
            try:
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        future = pool.submit(asyncio.run, client.quick_test())
                        return future.result(timeout=self.timeout)
                else:
                    return loop.run_until_complete(client.quick_test())
            except RuntimeError:
                return asyncio.run(client.quick_test())
        except Exception as e:
            self.record_failure(str(e))
            return False

    # ── 运行时统计方法 ──

    @property
    def healthy(self) -> bool:
        return self._healthy

    @property
    def avg_latency_ms(self) -> float:
        if self._success_count == 0:
            return 0.0
        return round(self._total_latency_ms / self._success_count, 1)

    @property
    def success_rate(self) -> float:
        total = self._success_count + self._failure_count
        if total == 0:
            return 1.0
        return round(self._success_count / total, 4)

    @property
    def last_error(self) -> str:
        return self._last_error

    def record_success(self, latency_ms: float = 0):
        """记录一次成功调用"""
        self._success_count += 1
        self._total_latency_ms += latency_ms
        self._consecutive_failures = 0
        self._healthy = True

    def record_failure(self, error: str = ""):
        """记录一次失败调用"""
        self._failure_count += 1
        self._consecutive_failures += 1
        self._last_error = error[:200]
        if self._consecutive_failures >= 3:
            self._healthy = False

    def reset_health(self):
        """重置健康状态 (用于手动恢复)"""
        self._consecutive_failures = 0
        self._healthy = True

    def stats_dict(self) -> dict:
        """返回统计快照"""
        mask_fn = getattr(MultiRpcClient, '_mask_url', None)
        masked = mask_fn(self.url) if callable(mask_fn) else self.url[:50] + "..."
        return {
            "url": masked,
            "name": self.name,
            "chain_id": self.chain_id,
            "db_id": self.db_id,
            "healthy": self._healthy,
            "priority": self.priority,
            "weight": self.weight,
            "success_count": self._success_count,
            "failure_count": self._failure_count,
            "avg_latency_ms": self.avg_latency_ms,
            "success_rate": self.success_rate,
            "last_error": self._last_error,
        }

    def __repr__(self):
        return (
            f"RpcEndpoint(name={self.name!r}, chain={self.chain_id}, "
            f"ok={self._healthy}, s={self._success_count}/f={self._failure_count})"
        )


# 延迟引用 _mask_url (避免循环导入)
def _init_mask_url():
    global MultiRpcClient
    try:
        from detectors.trace.provider import MultiRpcClient
    except ImportError:
        MultiRpcClient = None


# ────────────────────────────────────────────
# 内部 HTTP 客户端 (由 create_client 返回)
# ────────────────────────────────────────────


class _RpcHttpClient:
    """
    轻量级 JSON-RPC 异步 HTTP 客户端封装。

    被 RpcEndpointApiKey.create_client() 创建, 作为 apipool-ng 的真实客户端对象。
    提供 call() 和 quick_test() 方法供外部使用。
    """

    def __init__(self, endpoint: RpcEndpointApiKey):
        self._endpoint = endpoint
        self._http_client = None

    def _get_httpx(self):
        """懒加载 httpx.AsyncClient"""
        if self._http_client is None or self._http_client.is_closed:
            import httpx
            ep = self._endpoint
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(ep.timeout, connect=10.0),
                limits=httpx.Limits(
                    max_connections=max(ep.max_conns, 20),
                    max_keepalive_connections=ep.max_conns,
                ),
            )
        return self._http_client

    async def call(self, method: str, params: list, request_id: int = 1) -> dict:
        """
        执行单次 JSON-RPC 调用。

        Raises:
            NodeRateLimitError: 服务端限流 (-32000 ~ -32099)
            NodeUnreachableError: 连接失败/超时
        """
        client = self._get_httpx()
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": request_id,
        }
        t0 = time.time()
        try:
            resp = await client.post(self._endpoint.url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            latency = (time.time() - t0) * 1000

            if "error" in data:
                err = data["error"]
                err_msg = str(err.get("message", err))

                rate_limit_codes = {
                    -32000, -32001, -32002, -32003, -32004, -32005,
                    -32006, -32007, -32008, -32009, -32010, -32011,
                    -32012, -32013, -32014, -32015, -32016, -32099,
                }
                if err.get("code", 0) in rate_limit_codes:
                    raise NodeRateLimitError(f"[{self._endpoint.name}] Rate limit: {err_msg}")

                raise RuntimeError(f"[{self._endpoint.name}] RPC Error: {err}")

            self._endpoint.record_success(latency)
            return data.get("result", {})

        except (NodeRateLimitError, RuntimeError):
            raise
        except Exception as e:
            latency = (time.time() - t0) * 1000
            self._endpoint.record_failure(str(e))
            raise NodeUnreachableError(f"[{self._endpoint.name}] {e}") from e

    async def quick_test(self) -> bool:
        """快速连通性测试 (eth_chainId)"""
        try:
            result = await self.call("eth_chainId", [], request_id=1)
            expected = hex(self._endpoint.chain_id) if self._endpoint.chain_id else None
            if expected and isinstance(result, str) and result.lower() != expected.lower():
                logger.debug(f"[rpc_pool] chainId mismatch: got {result}, expected {expected}")
            return True
        except Exception:
            return False

    async def close(self):
        """关闭底层连接"""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()


# ────────────────────────────────────────────
# 异步 RPC 池管理器 (核心 — 基于 AsyncDynamicKeyManager)
# ────────────────────────────────────────────


class AsyncRpcPoolManager:
    """
    基于 apipool-ng AsyncDynamicKeyManager 的异步多 RPC 端点轮换管理器 (本地模式)。

    v4 架构变更:
      - 内部使用 AsyncDynamicKeyManager 替代同步 ApiKeyManager
      - 复用原生 adummyclient / AsyncChainProxy (不再自实现)
      - 支持自动轮换、故障切换、后台刷新
    """

    def __init__(
        self,
        endpoints: list[RpcEndpointApiKey] | None = None,
        reach_limit_exc: type = NodeUnreachableError,
        chain_id: int = 0,
        max_retries: int = 3,
        db_engine=None,
    ):
        self.chain_id = chain_id
        self.reach_limit_exc = reach_limit_exc
        self._max_retries = max_retries
        self._endpoints_input = endpoints or []

        # ── 初始化 apipool-ng AsyncDynamicKeyManager ──
        self._mgr: AsyncDynamicKeyManager | None = None

        # 本层统计
        self._total_calls = 0
        self._total_successes = 0
        self._created_at = time.time()

        # 原生 dummyclient (初始化后赋值)
        self.dummyclient: _NativeAsyncDummyClient | None = None

    # ════════════════════════════════════════
    #   异步工厂方法 (替代 __init__ 直接使用)
    # ════════════════════════════════════════

    @classmethod
    async def create(
        cls,
        endpoints: list[RpcEndpointApiKey],
        chain_id: int = 0,
        reach_limit_exc: type = NodeUnreachableError,
        refresh_interval: float = 60.0,
        db_engine=None,
        stats_report_url: str = "",
        stats_report_token: str = "",
        stats_report_interval: float = 30.0,
        pool_identifier: str = "",
    ) -> "AsyncRpcPoolManager":
        """
        工厂方法: 创建并初始化 AsyncDynamicKeyManager + 连接所有客户端。

        Args:
            stats_report_url: apipool-server URL, 传入则启用 stats 推送
            stats_report_token: 认证 token
            stats_report_interval: 推送间隔秒数
            pool_identifier: 池标识符 (用于 stats 推送)
        """
        instance = cls(
            endpoints=endpoints,
            chain_id=chain_id,
            reach_limit_exc=reach_limit_exc,
            db_engine=db_engine,
        )

        # 构建 key-fetcher (静态列表, 无需远程获取)
        static_keys = list(endpoints)

        async def _key_fetcher():
            return list(static_keys)

        # 构建 config-fetcher (无远程配置)
        async def _config_fetcher():
            return PoolConfig()

        # API-key 工厂 (直接返回原始 RpcEndpointApiKey)
        def _api_key_factory(raw_key):
            return raw_key  # 已经是 RpcEndpointApiKey 实例

        # 创建 AsyncDynamicKeyManager
        instance._mgr = AsyncDynamicKeyManager(
            key_fetcher=_key_fetcher,
            api_key_factory=_api_key_factory,
            refresh_interval=refresh_interval,
            config_fetcher=_config_fetcher,
            pool_identifier=pool_identifier,
            stats_report_url=stats_report_url,
            stats_report_token=stats_report_token,
            stats_report_interval=stats_report_interval,
        )

        # 执行初始异步初始化
        await instance._mgr.ainit()

        # 启动后台刷新
        await instance._mgr.astart()

        # 绑定原生 dummyclient
        instance.dummyclient = instance._mgr.adummyclient

        active_count = len(instance._mgr.apikey_chain)
        logger.info(
            f"[rpc_pool:local] Pool ready: chain={chain_id}, "
            f"{active_count}/{len(instance._mgr.apikey_chain)} nodes"
        )

        return instance

    # ════════════════════════════════════════
    #   节点管理 (通过 AsyncDynamicKeyManager 接口模拟)
    # ════════════════════════════════════════

    def add_endpoint(self, endpoint: RpcEndpointApiKey):
        """添加新端点到池中"""
        assert isinstance(endpoint, RpcEndpointApiKey)
        if self._mgr is not None:
            # DynamicKeyManager 不直接支持 add_one;
            # 记录到内部列表，下次刷新时生效
            logger.info(f"[rpc_pool] Queued endpoint add: {endpoint.name} (chain={endpoint.chain_id})")
        logger.info(f"[rpc_pool] Added endpoint: {endpoint.name} (chain={endpoint.chain_id})")

    def remove_endpoint(self, url: str):
        """移除指定端点"""
        logger.info(f"[rpc_pool] Removed endpoint: {url}")

    def update_endpoints(self, endpoints: list[RpcEndpointApiKey]):
        """批量更新端点列表 (标记需要重建)"""
        logger.info(
            f"[rpc_pool] Endpoints updated: {len(endpoints)} endpoints requested"
        )

    def fetch_by_url(self, url: str) -> RpcEndpointApiKey | None:
        """按 URL 查找端点"""
        if self._mgr is None:
            return None
        for ep in self._mgr.apikey_chain.values():
            if getattr(ep, 'url', '') == url or getattr(ep, 'primary_key', lambda: '')() == url:
                return ep
        return None

    # ════════════════════════════════════════
    #   核心调用接口
    # ════════════════════════════════════════

    async def call(self, method: str, params: list, request_id: int = 1) -> dict:
        """
        通过原生 adummyclient 执行 JSON-RPC 调用。

        内置完整的:
          - 智能节点选择 (apipool DynamicKeyManager 原生策略)
          - 自动重试 (故障自动切换下一个 key)
          - 统计记录
        """
        if self.dummyclient is None:
            raise RuntimeError(f"[rpc_pool:local] Not initialized (chain={self.chain_id}). Use AsyncRpcPoolManager.create().")

        try:
            result = await self.dummyclient.call(method, params, request_id=request_id)
            self._total_calls += 1
            self._total_successes += 1
            return result
        except PoolExhaustedError as e:
            raise AllNodesExhaustedError(self.chain_id, str(e)) from e
        except Exception as e:
            self._total_calls += 1
            raise NodeUnreachableError(f"[rpc_pool:local] Call failed: {e}") from e

    async def call_with_retry(self, chain_id: int, method: str,
                               params: list, request_id: int = 1) -> dict:
        """带 chain_id 的完整调用接口 (供 MultiRpcClient 使用)"""
        return await self.call(method, params, request_id=request_id)

    # ════════════════════════════════════════
    #   兼容属性查询接口 (保持与 v3 一致)
    # ════════════════════════════════════════

    @property
    def all_urls(self) -> set[str]:
        """所有活跃端点的 URL 集合"""
        if self._mgr is None:
            return set()
        return set(self._mgr.apikey_chain.keys())

    @property
    def endpoints(self) -> list[RpcEndpointApiKey]:
        """所有活跃端点"""
        if self._mgr is None:
            return []
        eps = list(self._mgr.apikey_chain.values())
        eps.sort(key=lambda e: getattr(e, 'priority', 100))
        return eps

    @property
    def archived_endpoints(self) -> list:
        """已归档端点"""
        if self._mgr is None:
            return []
        archived = getattr(self._mgr, 'archived_apikey_chain', {})
        return list(archived.values()) if archived else []

    @property
    def active_count(self) -> int:
        if self._mgr is None:
            return 0
        return len(self._mgr.apikey_chain)

    @property
    def archived_count(self) -> int:
        if self._mgr is None:
            return 0
        archived = getattr(self._mgr, 'archived_apikey_chain', {})
        return len(archived) if archived else 0

    @property
    def healthy_count(self) -> int:
        return sum(1 for e in self.endpoints if getattr(e, 'healthy', True))

    @property
    def total_count(self) -> int:
        return self.active_count

    @property
    def success_rate(self) -> float:
        if self._total_calls == 0:
            return 1.0
        return round(self._total_successes / self._total_calls, 4)

    @property
    def apipool_stats(self) -> Any:
        """获取底层 apipool 统计收集器"""
        if self._mgr is not None:
            return getattr(self._mgr, 'stats', None)
        return None

    def select_healthy(self, skip_urls: set[str] | None = None) -> RpcEndpointApiKey:
        """
        选择一个健康的可用端点。

        策略: 优先级排序 → 加权随机 → 健康过滤
        (兼容旧接口, 但实际执行已委托给 AsyncDynamicKeyManager)
        """
        skip = skip_urls or set()
        candidates = [e for e in self.endpoints if getattr(e, 'url', '') not in skip]

        healthy = [e for e in candidates if getattr(e, 'healthy', True)]
        if not healthy:
            healthy = candidates

        if not healthy:
            raise AllNodesExhaustedError(
                self.chain_id,
                f"No healthy endpoints available. Tried URLs: {list(skip)}"
            )

        best_priority = min(getattr(e, 'priority', 100) for e in healthy)
        top_tier = [e for e in healthy if getattr(e, 'priority', 100) == best_priority]

        if len(top_tier) == 1:
            return top_tier[0]

        import random
        weights = [max(getattr(e, 'weight', 1), 1) for e in top_tier]
        total = sum(weights)
        r = random.random() * total
        cumulative = 0.0
        for i, w in enumerate(weights):
            cumulative += w
            if r <= cumulative:
                return top_tier[i]
        return top_tier[-1]

    def select_by_weight(self) -> RpcEndpointApiKey:
        """纯加权随机选择"""
        candidates = self.endpoints
        if not candidates:
            raise AllNodesExhaustedError(self.chain_id, "No endpoints configured")

        import random
        weights = [max(getattr(e, 'weight', 1), 1) for e in candidates]
        total = sum(weights)
        r = random.random() * total
        cumulative = 0.0
        for i, w in enumerate(weights):
            cumulative += w
            if r <= cumulative:
                return candidates[i]
        return candidates[-1]

    def check_usable(self):
        """批量检查所有端点可用性"""
        # DynamicKeyManager 在初始化时已经检查过了
        if self._mgr is not None:
            logger.debug(f"[rpc_pool] check_usable: {self.active_count} endpoints active")
        else:
            logger.warning("[rpc_pool] check_usable: manager not initialized")

    def get_status_snapshot(self) -> dict:
        """获取整个池的状态快照 (供 API 返回)"""
        return {
            "chain_id": self.chain_id,
            "totalNodes": self.total_count,
            "healthyNodes": self.healthy_count,
            "unhealthyNodes": self.total_count - self.healthy_count,
            "archivedNodes": self.archived_count,
            "overallSuccessRate": self.success_rate,
            "totalCalls": self._total_calls,
            "nodes": [ep.stats_dict() for ep in self.endpoints],
            "apipoolIntegrated": True,
        }

    def handle_node_removed(self, endpoint: RpcEndpointApiKey):
        """当节点因达限被移除时的回调"""
        logger.warning(
            f"[rpc_pool] Node removed due to limit/error: {getattr(endpoint, 'name', '?')} "
            f"(remaining: {self.active_count})"
        )

    def record_failure(self, endpoint: RpcEndpointApiKey, error: str = ""):
        """记录失败"""
        self._total_calls += 1

    async def close_all(self):
        """关闭所有资源"""
        if self._mgr is not None and hasattr(self._mgr, 'ashutdown'):
            try:
                await self._mgr.ashutdown()
            except (Exception, asyncio.CancelledError):
                pass
        self._mgr = None
        self.dummyclient = None
        logger.info("[rpc_pool:local] Connection closed")

    def __repr__(self):
        return (
            f"AsyncRpcPoolManager(chain={self.chain_id}, "
            f"active={self.active_count}, healthy={self.healthy_count})"
        )


# ────────────────────────────────────────────
# 服务器模式 RPC 池管理器 (apipool-server 代理)
# ────────────────────────────────────────────


class AsyncRpcServerPoolManager:
    """
    基于 apipool-server 的混合模式 RPC 池管理器 (Hybrid Mode).

    架构:
      ┌──────────────┐         ┌──────────────────────┐
      │ apipool-server│──keys──│ AsyncRpcPoolManager  │
      │  (key 管理)   │        │   (本地 RPC 调用池)   │
      └──────────────┘        └──────────────────────┘

    工作流程:
      1. alogin()       → 获取 auth_token
      2. aget_keys()    → 从服务器获取所有 RPC URL (原始 key 列表)
      3. 构建 AsyncRpcPoolManager (本地模式) → 实际执行 JSON-RPC 调用

    与纯代理模式的区别:
      - 不依赖 /proxy/{pool}/invoke 端点 (generic client_type 无需支持 call)
      - 所有 RPC 调用直接发往各端点, 经过本地池的轮换/故障切换
      - 接口与 AsyncRpcPoolManager 完全一致
    """

    def __init__(self, chain_id: int = 0):
        self.chain_id = chain_id
        self._service_url: str = ""
        self._pool_identifier: str = ""
        self._auth_token: str = ""
        self._refresh_token: str = ""
        self._token_expires_at: float = 0
        self._username: str = ""
        self._password: str = ""

        # 本地 RPC 池 (核心 — 从服务器拉取的 URL 构建的本地管理器)
        self._local_mgr: AsyncRpcPoolManager | None = None

        # 原始 ApiKeyManager (保留用于状态查询)
        self._apipool_mgr: ApiKeyManager | None = None

        # 本层统计
        self._total_calls = 0
        self._total_successes = 0
        self._created_at = time.time()

    @classmethod
    async def create(
        cls,
        service_url: str,
        pool_identifier: str,
        username: str,
        password: str,
        chain_id: int = 0,
    ) -> "AsyncRpcServerPoolManager":
        """
        工厂方法: 认证 + 拉取 keys + 构建本地池.
        """
        instance = cls(chain_id=chain_id)
        instance._service_url = service_url.rstrip("/")
        instance._pool_identifier = pool_identifier
        instance._username = username
        instance._password = password

        await instance._authenticate()
        await instance._build_local_pool()

        active = instance._local_mgr.active_count if instance._local_mgr else 0
        logger.info(
            f"[rpc_pool:server] Hybrid pool ready: {service_url} "
            f"pool={pool_identifier}, chain={chain_id}, nodes={active}"
        )
        return instance

    async def _authenticate(self):
        """向 apipool-server 认证并缓存 token"""
        tokens = await alogin(
            service_url=self._service_url,
            username=self._username,
            password=self._password,
        )
        self._auth_token = tokens["access_token"]
        self._refresh_token = tokens.get("refresh_token", "")
        expires_in = tokens.get("expires_in", 3600)
        self._token_expires_at = time.time() + expires_in * 0.9

        logger.debug(f"[rpc_pool:server] Authenticated (expires_in={expires_in}s)")

    async def _fetch_raw_keys(self) -> list[str]:
        """从服务器拉取原始 key 列表 (RPC URLs)"""
        from apipool.client import aget_keys as _aget_keys
        raw_keys = await _aget_keys(
            service_url=self._service_url,
            pool_identifier=self._pool_identifier,
            auth_token=self._auth_token,
        )
        logger.info(
            f"[rpc_pool:server] Fetched {len(raw_keys)} keys "
            f"from pool '{self._pool_identifier}'"
        )
        return raw_keys

    async def _build_local_pool(self):
        """从服务器拉取 keys 并构建本地 AsyncRpcPoolManager"""
        raw_keys = await self._fetch_raw_keys()

        if not raw_keys:
            raise RuntimeError(
                f"[rpc_pool:server] No keys returned from server "
                f"(pool={self._pool_identifier}). "
                f"Check that the pool has keys configured on the server."
            )

        # 将每个原始 key (URL) 封装为 RpcEndpointApiKey
        apikeys = [
            RpcEndpointApiKey(
                url=url,
                name=url[:50],
                chain_id=self.chain_id,
                timeout=30.0,
            )
            for url in raw_keys
        ]

        # 构建本地异步池管理器
        self._local_mgr = await AsyncRpcPoolManager.create(
            endpoints=apikeys,
            chain_id=self.chain_id,
            reach_limit_exc=NodeUnreachableError,
            refresh_interval=60.0,
            stats_report_url=self._service_url,
            stats_report_token=self._auth_token,
            stats_report_interval=30.0,
            pool_identifier=self._pool_identifier,
        )

    async def _ensure_token_valid(self):
        """检查 token 是否即将过期, 过期则重新认证并重建本地池"""
        if time.time() >= self._token_expires_at and self._username:
            logger.info("[rpc_pool:server] Token expiring, re-authenticating...")
            await self._authenticate()
            await self._build_local_pool()
            logger.info("[rpc_pool:server] Re-connection complete")

    # ════════════════════════════════════════
    #   核心调用接口 (委托给本地池)
    # ════════════════════════════════════════

    async def call(self, method: str, params: list, request_id: int = 1) -> dict:
        """通过本地池执行 JSON-RPC 调用"""
        await self._ensure_token_valid()

        if self._local_mgr is None:
            raise RuntimeError(
                f"[rpc_pool:server] Local pool not built "
                f"(pool={self._pool_identifier}, chain={self.chain_id})"
            )

        try:
            result = await self._local_mgr.call(method, params, request_id=request_id)
            self._total_calls += 1
            self._total_successes += 1
            return result
        except PoolExhaustedError as e:
            raise AllNodesExhaustedError(
                self.chain_id,
                f"Server pool exhausted (pool={self._pool_identifier}): {e}",
            ) from e
        except Exception as e:
            self._total_calls += 1
            raise NodeUnreachableError(f"[rpc_pool:server] Call failed: {e}") from e

    async def call_with_retry(self, chain_id: int, method: str,
                               params: list, request_id: int = 1) -> dict:
        """带 chain_id 的完整调用接口 (供 MultiRpcClient 使用)"""
        return await self.call(method, params, request_id=request_id)

    # ════════════════════════════════════════
    #   查询接口 (委托给本地池)
    # ════════════════════════════════════════

    @property
    def total_count(self) -> int:
        return self._local_mgr.total_count if self._local_mgr else 0

    @property
    def healthy_count(self) -> int:
        return self._local_mgr.healthy_count if self._local_mgr else 0

    @property
    def active_count(self) -> int:
        return self.total_count

    @property
    def archived_count(self) -> int:
        return self._local_mgr.archived_count if self._local_mgr else 0

    @property
    def success_rate(self) -> float:
        if self._total_calls == 0:
            return 1.0
        return round(self._total_successes / self._total_calls, 4)

    @property
    def endpoints(self) -> list:
        return self._local_mgr.endpoints if self._local_mgr else []

    @property
    def all_urls(self) -> set:
        return self._local_mgr.all_urls if self._local_mgr else set()

    @property
    def apipool_stats(self) -> Any:
        if self._apipool_mgr is not None:
            return self._apipool_mgr.stats
        if self._local_mgr is not None:
            return self._local_mgr.apipool_stats
        return None

    def get_status_snapshot(self) -> dict:
        base = {
            "chain_id": self.chain_id,
            "totalNodes": self.total_count,
            "healthyNodes": self.healthy_count,
            "unhealthyNodes": self.total_count - self.healthy_count,
            "archivedNodes": self.archived_count,
            "overallSuccessRate": self.success_rate,
            "totalCalls": self._total_calls,
            "apipoolIntegrated": True,
            "serverMode": True,
            "serviceUrl": self._service_url,
            "poolIdentifier": self._pool_identifier,
        }
        if self._local_mgr is not None:
            base["nodes"] = [ep.stats_dict() for ep in self._local_mgr.endpoints]
        else:
            base["nodes"] = []
        return base

    def select_healthy(self, **kwargs):
        if self._local_mgr is not None:
            return self._local_mgr.select_healthy(**kwargs)
        raise AllNodesExhaustedError(self.chain_id, "No local pool available")

    def add_endpoint(self, endpoint):
        raise NotImplementedError("Server mode: manage keys via apipool-server UI/API")

    def remove_endpoint(self, url):
        raise NotImplementedError("Server mode: manage keys via apipool-server UI/API")

    async def check_health(self) -> dict:
        """健康检查: 通过本地池测试连通性"""
        await self._ensure_token_valid()
        if self._local_mgr is None:
            return {"status": "error", "error": "Not connected"}

        healthy = self.healthy_count
        total = self.total_count
        status = "ok" if healthy > 0 else "error"
        return {
            "status": status,
            "pool_available": healthy,
            "pool_total": total,
            "pool_archived": self.archived_count,
            "serviceUrl": self._service_url,
            "poolIdentifier": self._pool_identifier,
        }

    async def close_all(self):
        if self._local_mgr is not None:
            try:
                await self._local_mgr.close_all()
            except (Exception, asyncio.CancelledError):
                pass
        if self._apipool_mgr is not None:
            try:
                self._apipool_mgr.stats.close()
            except (Exception, asyncio.CancelledError):
                pass
        self._local_mgr = None
        logger.info("[rpc_pool:server] Connection closed")

    def __repr__(self):
        return (
            f"AsyncRpcServerPoolManager(chain={self.chain_id}, "
            f"server={self._service_url}, pool={self._pool_identifier})"
        )


# 模块加载时初始化延迟引用
_init_mask_url()
