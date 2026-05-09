"""
RPC Client — 基于 apipool-server 的统一连接池管理
================================================
特性:
- 所有 RPC 调用统一由 apipool-server 管理, 本地不存储任何密钥
- 每条链使用独立的 pool_identifier, 通过配置文件或环境变量管理
- 自动认证 + token 刷新 + 故障转移
- 支持运行时动态更新 pool_identifier (通过 API 或热重载)

架构:
  Config(.env) → MultiRpcClient → AsyncRpcServerPoolManager(每链独立) → apipool-server → RPC Nodes
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from detectors.trace.rpc_pool import (
    AsyncRpcServerPoolManager,
    AllNodesExhaustedError,
)

logger = logging.getLogger(__name__)

# 链元信息 (名称和浏览器地址)
CHAIN_META: dict[int, dict] = {
    1:       {"name": "Ethereum",         "explorer": "https://etherscan.io/tx/"},
    56:      {"name": "BSC",              "explorer": "https://bscscan.com/tx/"},
    137:     {"name": "Polygon",          "explorer": "https://polygonscan.com/tx/"},
    42161:   {"name": "Arbitrum One",     "explorer": "https://arbiscan.io/tx/"},
    10:      {"name": "Optimism",         "explorer": "https://optimistic.etherscan.io/tx/"},
    43114:   {"name": "Avalanche C-Chain","explorer": "https://snowtrace.io/tx/"},
}


# ────────────────────────────────────────────
# 核心客户端
# ────────────────────────────────────────────
class MultiRpcClient:
    """
    多链 RPC 客户端 (v4 — 基于 apipool-server 统一管理)

    每条链使用一个 AsyncRpcServerPoolManager, 通过 pool_identifier
    连接到 apipool-server 上对应的池。

    用法:
        client = MultiRpcClient()
        result = await client.call(1, "eth_getBlockByNumber", ["latest", False])
        traces = await client.get_transaction_trace("0xabc...", chain_id=56)
    """

    def __init__(self, timeout: float = 30.0):
        self._timeout = timeout
        # 每链一个池管理器 (AsyncRpcServerPoolManager)
        self._pool_managers: dict[int, AsyncRpcServerPoolManager] = {}
        self._request_id: int = 0
        self._initialized: bool = False
        self._health_interval: float = 60.0
        self._health_task: Optional[asyncio.Task] = None
        # 初始化锁 — 防止并发请求重复登录/拉取密钥
        self._init_lock: asyncio.Lock = asyncio.Lock()
        # 正在初始化中的 Future，用于让等待者共享同一次初始化结果
        self._init_future: Optional[asyncio.Future] = None

        # 方法级能力缓存 — 记录某链上某个 RPC 方法是否所有节点均不支持
        # key = f"{chain_id}:{method}", True = 已确认该链上该方法不可用
        # 避免每次 trace 都浪费一轮尝试在不支持的节点上
        self._method_blacklist: dict[str, float] = {}  # key → timestamp when blacklisted
        self._blacklist_ttl: float = 600.0  # 黑名单有效期 10 分钟（节点可能更新）

    # ──── 配置加载 ────

    async def ensure_loaded(self):
        """
        首次调用时从配置加载 (幂等，并发安全)

        使用 Future 模式：第一个请求执行初始化，后续请求等待同一个 Future，
        避免并发时重复 login / fetch keys。
        """
        if self._initialized:
            return

        # 已有初始化正在进行 → 直接等它完成
        if self._init_future is not None and not self._init_future.done():
            await self._init_future
            return

        # 获取锁，保证只有一个协程真正执行初始化
        async with self._init_lock:
            # double-check：等锁期间可能已被其他协程完成
            if self._initialized:
                return
            # 再检查一次 Future（极端边界情况）
            if self._init_future is not None and not self._init_future.done():
                await self._init_future
                return

            # 创建 Future，让后续请求可以等待
            loop = asyncio.get_event_loop()
            self._init_future = loop.create_future()
            try:
                logger.debug("[RPC-v4] Acquired init lock, loading config...")
                await self.reload_config()
                self._init_future.set_result(True)
            except Exception as e:
                self._init_future.set_exception(e)
                raise

    async def reload_config(self):
        """
        从 config/model.py 读取 apipool-server 配置,
        为每条配置了 pool_identifier 的链创建 AsyncRpcServerPoolManager。
        """
        from config.model import settings

        server_url = settings.apipool_server_url
        username = settings.apipool_username
        password = settings.apipool_password
        pool_map = settings.apipool_pool_map

        if not server_url or not username or not password:
            raise RuntimeError(
                "[RPC-v4] apipool-server configuration is required. "
                "Please set APIPOOL_SERVER_URL, APIPOOL_USERNAME, APIPOOL_PASSWORD "
                "in .env or environment variables."
            )

        if not pool_map:
            raise RuntimeError(
                "[RPC-v4] No pool identifiers configured. "
                "Please set APIPOOL_POOL_MAP in .env, e.g. "
                "APIPOOL_POOL_MAP={\"1\":\"ethereum-rpc\",\"56\":\"bsc-rpc\"}"
            )

        # 关闭已有的池管理器
        for mgr in self._pool_managers.values():
            try:
                await mgr.close_all()
            except Exception as e:
                logger.warning(f"[RPC-v4] Error closing pool manager: {e}")
        self._pool_managers.clear()

        # 为每条链创建 AsyncRpcServerPoolManager
        for chain_id, pool_identifier in pool_map.items():
            chain_id = int(chain_id)
            try:
                mgr = await AsyncRpcServerPoolManager.create(
                    service_url=server_url,
                    pool_identifier=pool_identifier,
                    username=username,
                    password=password,
                    chain_id=chain_id,
                )
                self._pool_managers[chain_id] = mgr
                logger.info(
                    f"[RPC-v4] Chain {chain_id} ({CHAIN_META.get(chain_id, {}).get('name', '?')}) "
                    f"connected to pool={pool_identifier}"
                )
            except Exception as e:
                logger.error(
                    f"[RPC-v4] Failed to connect chain={chain_id} "
                    f"pool={pool_identifier}: {e}"
                )

        if not self._pool_managers:
            raise RuntimeError("[RPC-v4] No pool managers initialized. Check your configuration.")

        self._initialized = True
        summary = {cid: mgr._pool_identifier for cid, mgr in self._pool_managers.items()}
        logger.info(f"[RPC-v4] Config loaded: pools={summary}")

    async def update_pool_identifier(self, chain_id: int, pool_identifier: str) -> dict:
        """
        运行时更新指定链的 pool_identifier。
        关闭旧连接, 使用新的 pool_identifier 重新连接。

        Args:
            chain_id: 链 ID
            pool_identifier: 新的池标识符

        Returns:
            {"success": True, "chain_id": chain_id, "pool_identifier": pool_identifier}
        """
        from config.model import settings

        server_url = settings.apipool_server_url
        username = settings.apipool_username
        password = settings.apipool_password

        if not server_url or not username or not password:
            raise RuntimeError("[RPC-v4] apipool-server configuration missing")

        # 关闭旧的池管理器
        old_mgr = self._pool_managers.get(chain_id)
        if old_mgr:
            try:
                await old_mgr.close_all()
            except Exception as e:
                logger.warning(f"[RPC-v4] Error closing old pool for chain={chain_id}: {e}")

        # 创建新的池管理器
        try:
            new_mgr = await AsyncRpcServerPoolManager.create(
                service_url=server_url,
                pool_identifier=pool_identifier,
                username=username,
                password=password,
                chain_id=chain_id,
            )
            self._pool_managers[chain_id] = new_mgr

            # 更新配置中的 pool_map
            pool_map = dict(settings.apipool_pool_map)
            pool_map[str(chain_id)] = pool_identifier
            settings.apipool_pool_map = pool_map

            logger.info(
                f"[RPC-v4] Chain {chain_id} pool updated: {pool_identifier}"
            )
            return {
                "success": True,
                "chain_id": chain_id,
                "pool_identifier": pool_identifier,
            }
        except Exception as e:
            logger.error(
                f"[RPC-v4] Failed to update pool for chain={chain_id}: {e}"
            )
            # 如果更新失败, 尝试恢复旧的
            if old_mgr:
                self._pool_managers[chain_id] = old_mgr
            raise RuntimeError(
                f"Failed to update pool_identifier for chain={chain_id}: {e}"
            ) from e

    # ──── 核心调用方法 ────

    async def call(
        self,
        chain_id: int,
        method: str,
        params: list,
        retries: int | None = None,
    ) -> dict:
        """
        带自动轮换的 JSON-RPC 调用 (通过 apipool-server 代理)

        Args:
            chain_id: 链 ID
            method: RPC 方法名
            params: 参数列表
            retries: 最大重试次数 (由 apipool-server 管理)

        Returns:
            RPC 结果字典

        Raises:
            RuntimeError: 链未配置或所有节点均失败
        """
        await self.ensure_loaded()

        mgr = self._pool_managers.get(chain_id)
        if not mgr:
            raise RuntimeError(
                f"No pool configured for chain {chain_id}. "
                f"Available chains: {list(self._pool_managers.keys())}"
            )

        self._request_id += 1
        return await mgr.call(method, params, request_id=self._request_id)

    # ──── Trace 方法 (保持原有接口兼容) ────

    async def get_transaction_trace(self, tx_hash: str, chain_id: int,
                                    max_node_retries: int = 3) -> list[dict]:
        """
        获取交易的完整调用追踪 (trace_transaction → debug_traceTransaction 回退)

        当某个节点不支持 tracing 方法时，自动切换到池内其他节点重试，
        而非直接返回空列表。

        性能优化:
          - 方法级黑名单: 若某链上某方法所有节点均不支持, 后续调用直接跳过
          - 黑名单有 TTL (10分钟), 避免永久跳过(节点可能更新)
        """
        last_error = None
        now = time.time()

        # ── 尝试 trace_transaction ──
        bl_key_tt = f"{chain_id}:trace_transaction"
        if bl_key_tt not in self._method_blacklist or \
           now - self._method_blacklist[bl_key_tt] > self._blacklist_ttl:

            for attempt in range(max_node_retries):
                try:
                    result = await self.call(chain_id, "trace_transaction", [tx_hash])
                    if result and isinstance(result, list) and len(result) > 0:
                        logger.info(
                            f"[TRACE] Got {len(result)} entries via trace_transaction "
                            f"(chain={chain_id}, attempt={attempt + 1})"
                        )
                        return result
                except Exception as e:
                    last_error = e
                    err_msg = str(e).lower()
                    is_method_err = any(kw in err_msg for kw in [
                        "method not found", "-32601", "not supported",
                        "does not support", "tracing", "not allowed to access method", "-32053",
                    ])
                    if is_method_err:
                        logger.debug(
                            f"[TRACE] Node does not support trace_transaction "
                            f"(chain={chain_id}, attempt={attempt + 1}), trying next node..."
                        )
                        continue
                    logger.debug(
                        f"[TRACE] trace_transaction failed (chain={chain_id}, "
                        f"attempt={attempt + 1}): {e}"
                    )

            # 所有节点均返回 method not found → 加入黑名单，后续跳过此方法
            self._method_blacklist[bl_key_tt] = now
            logger.info(
                f"[TRACE] All nodes rejected 'trace_transaction' on chain {chain_id}, "
                f"blacklisting this method for {self._blacklist_ttl}s"
            )
        else:
            logger.debug(
                f"[TRACE] Skipping 'trace_transaction' (blacklisted for chain {chain_id})"
            )

        # ── 尝试 debug_traceTransaction ──
        bl_key_dt = f"{chain_id}:debug_traceTransaction"
        if bl_key_dt not in self._method_blacklist or \
           now - self._method_blacklist[bl_key_dt] > self._blacklist_ttl:

            for attempt in range(max_node_retries):
                try:
                    tracer_config = {"tracer": "callTracer", "tracerConfig": {"withLog": True}}
                    result = await self.call(
                        chain_id, "debug_traceTransaction", [tx_hash, tracer_config]
                    )
                    if result and isinstance(result, dict):
                        logger.info(
                            f"[TRACE] Got result via debug_traceTransaction "
                            f"(chain={chain_id}, attempt={attempt + 1})"
                        )
                        return self._flatten_calltracer(result)
                except Exception as e:
                    last_error = e
                    err_msg = str(e).lower()
                    is_method_err = any(kw in err_msg for kw in [
                        "method not found", "-32601", "not supported",
                        "does not support", "tracing", "not allowed to access method", "-32053",
                    ])
                    if is_method_err:
                        logger.debug(
                            f"[TRACE] Node does not support debug_traceTransaction "
                            f"(chain={chain_id}, attempt={attempt + 1}), trying next node..."
                        )
                        continue
                    logger.debug(
                        f"[TRACE] debug_traceTransaction failed (chain={chain_id}, "
                        f"attempt={attempt + 1}): {e}"
                    )

            # 所有节点均返回 method not found → 加入黑名单
            self._method_blacklist[bl_key_dt] = now
            logger.info(
                f"[TRACE] All nodes rejected 'debug_traceTransaction' on chain {chain_id}, "
                f"blacklisting this method for {self._blacklist_ttl}s"
            )
        else:
            logger.debug(
                f"[TRACE] Skipping 'debug_traceTransaction' (blacklisted for chain {chain_id})"
            )

        logger.warning(
            f"[TRACE] No tracing support available for tx {tx_hash[:16]}... "
            f"on chain {chain_id} after trying {max_node_retries} nodes per method"
            + (f". Last error: {last_error}" if last_error else "")
        )
        return []

    async def get_transaction_receipt(self, tx_hash: str, chain_id: int) -> dict:
        """获取交易收据"""
        return await self.call(chain_id, "eth_getTransactionReceipt", [tx_hash])

    async def get_transaction_by_hash(self, tx_hash: str, chain_id: int) -> dict:
        """获取交易基本信息"""
        return await self.call(chain_id, "eth_getTransactionByHash", [tx_hash])

    # ──── 健康检查 ────

    async def run_health_checks(self, chain_id: int | None = None,
                                 max_concurrent: int = 20) -> list[dict]:
        """
        运行健康检查 (通过 apipool-server 的 status API)

        Args:
            chain_id: 指定链 ID (None=全部)
            max_concurrent: 未使用 (兼容旧接口)
        """
        await self.ensure_loaded()
        reports = []

        for cid, mgr in self._pool_managers.items():
            if chain_id is not None and cid != chain_id:
                continue
            try:
                status = await mgr.check_health()
                reports.append({
                    "id": f"server:{cid}",
                    "name": f"apipool-server (pool={mgr._pool_identifier})",
                    "url": mgr._service_url,
                    "chain_id": cid,
                    "chain_name": CHAIN_META.get(cid, {}).get("name", f"Chain-{cid}"),
                    "status": "ok" if status.get("success", False) else "error",
                    "latency_ms": -1,
                    "chainId_match": True,
                    "error": status.get("error", ""),
                    "server_mode": True,
                    "pool_identifier": mgr._pool_identifier,
                })
            except Exception as e:
                reports.append({
                    "id": f"server:{cid}",
                    "chain_id": cid,
                    "chain_name": CHAIN_META.get(cid, {}).get("name", f"Chain-{cid}"),
                    "status": "error",
                    "error": str(e)[:200],
                    "pool_identifier": mgr._pool_identifier,
                })

        return reports

    async def start_health_monitor(self):
        """启动后台定期健康检查任务"""
        if self._health_task and not self._health_task.done():
            return
        self._health_task = asyncio.create_task(self._health_loop())
        logger.info("[RPC] Health monitor started")

    async def stop_health_monitor(self):
        """停止后台健康检查任务"""
        if self._health_task and not self._health_task.done():
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
            logger.info("[RPC] Health monitor stopped")

    async def _health_loop(self):
        while True:
            try:
                await asyncio.sleep(self._health_interval)
                reports = await self.run_health_checks()
                ok_count = sum(1 for r in reports if r.get("status") == "ok")
                total = len(reports)
                logger.debug(f"[RPC] Health check: {ok_count}/{total} pools OK")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[RPC] Health loop error: {e}")

    # ──── 状态查询 API ────

    async def get_pool_status(self) -> list[dict]:
        """返回所有节点池的状态 (供 API 使用)"""
        await self.ensure_loaded()
        result = []
        for cid, mgr in sorted(self._pool_managers.items()):
            meta = CHAIN_META.get(cid, {})
            snapshot = mgr.get_status_snapshot()
            result.append({
                "chainId": cid,
                "chainName": meta.get("name", f"Chain-{cid}"),
                "totalNodes": snapshot.get("totalNodes", 0),
                "healthyNodes": snapshot.get("healthyNodes", 0),
                "nodes": [],
                "serverMode": True,
                "serviceUrl": snapshot.get("serviceUrl", ""),
                "poolIdentifier": mgr._pool_identifier,
            })
        return result

    async def test_connection(self, rpc_url: str, timeout: int = 15) -> dict:
        """
        测试单个 RPC URL 连通性 (直接 httpx 测试, 不经过 apipool-server)
        返回: {ok, latency_ms, blockNumber, chainId, error}
        """
        import httpx

        result = {"ok": False, "latency_ms": -1, "block_number": "", "chain_id": "", "error": ""}
        t0 = time.time()
        try:
            client = httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=5.0))

            payload_cid = {"jsonrpc": "2.0", "method": "eth_chainId", "params": [], "id": 1}
            payload_block = {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 2}

            tasks = [
                client.post(rpc_url, json=payload_cid),
                client.post(rpc_url, json=payload_block),
            ]
            responses = await asyncio.gather(*tasks, return_exceptions=True)

            latency = (time.time() - t0) * 1000
            result["latency_ms"] = round(latency, 1)

            r1 = responses[0]
            if isinstance(r1, Exception):
                result["error"] = f"chainId request failed: {r1}"
            else:
                d1 = r1.json() if hasattr(r1, 'json') else {}
                result["chain_id"] = d1.get("result", "error" if "error" in d1 else "")

            r2 = responses[1]
            if isinstance(r2, Exception):
                result["error"] += (f" | blockNumber failed: {r2}" if result["error"] else f"blockNumber failed: {r2}")
            else:
                d2 = r2.json() if hasattr(r2, 'json') else {}
                if "error" in d2:
                    result["error"] = str(d2["error"])
                else:
                    result["block_number"] = d2.get("result", "")

            if not result.get("error") and result.get("chain_id"):
                result["ok"] = True

            await client.aclose()

        except Exception as e:
            result["error"] = str(e)[:300]
            result["latency_ms"] = round((time.time() - t0) * 1000, 1)

        return result

    # ──── 清理 ────

    async def close(self) -> None:
        """关闭所有连接"""
        await self.stop_health_monitor()
        for mgr in self._pool_managers.values():
            await mgr.close_all()
        self._pool_managers.clear()

    # ──── 工具方法 ────

    @staticmethod
    def get_chain_name(chain_id: int) -> str:
        meta = CHAIN_META.get(chain_id, {})
        return meta.get("name", f"Chain-{chain_id}")

    @staticmethod
    def get_explorer_url(chain_id: int) -> str:
        meta = CHAIN_META.get(chain_id, {})
        return meta.get("explorer", "")

    @staticmethod
    def supported_chains() -> list[dict]:
        return [
            {"chainId": cid, "name": cfg["name"], "explorer": cfg.get("explorer", "")}
            for cid, cfg in sorted(CHAIN_META.items())
        ]

    @staticmethod
    def get_default_chains() -> list[int]:
        return sorted(CHAIN_META.keys())

    @staticmethod
    def _flatten_calltracer(result: dict) -> list[dict]:
        """将 debug_traceTransaction 的 callTracer 递归结果展平为 trace_transaction 格式"""
        entries = []

        def _walk(node: dict, depth: int = 0):
            entry = {
                "action": {
                    "callType": node.get("type", "CALL").lower(),
                    "from": node.get("from", ""),
                    "to": node.get("to", ""),
                    "value": node.get("value", "0x0"),
                    "gas": node.get("gas", "0x0"),
                    "input": node.get("input", "0x"),
                },
                "result": {
                    "gasUsed": node.get("gasUsed", "0x0"),
                    "output": node.get("output", "0x"),
                },
                "subtraces": len(node.get("calls", [])),
                "traceAddress": [],
                "depth": depth,
            }
            entries.append(entry)
            for child in node.get("calls", []):
                _walk(child, depth + 1)

        _walk(result)
        return entries


# ────────────────────────────────────────────
# 全局单例
# ────────────────────────────────────────────
_global_client: Optional[MultiRpcClient] = None


def get_rpc_client() -> MultiRpcClient:
    """获取全局 RPC 客户端单例"""
    global _global_client
    if _global_client is None:
        _global_client = MultiRpcClient()
    return _global_client
