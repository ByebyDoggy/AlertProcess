"""
Moralis API Key Pool Manager
============================
从 apipool-server 加载 Moralis API Key 列表，提供多 Key 轮换和故障切换。

架构:
  ┌──────────────────────────────────────────────────────┐
  │  MoralKeyPoolManager                                  │
  │                                                      │
  │  alogin() → aget_keys(pool_id) → _keys[]            │
  │  StatsCollector → 本地记录调用事件 → 后台推送到 server │
  │                                                      │
  │  get_key(index) → 按索引获取 key                     │
  │  all_keys → 完整列表（只读）                          │
  │  count → key 数量                                     │
  │  record_call() → 记录调用事件到 StatsCollector        │
  │  reload() → 重新从 server 拉取                        │
  │  close() → 清理资源                                    │
  └──────────────────────────────────────────────────────┘

用法:
    mgr = await MoralKeyPoolManager.create(
        service_url="http://localhost:8000",
        pool_identifier="moralis-keys",
        username="alice", password="password",
    )
    keys = mgr.all_keys  # ["key1", "key2", ...]
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import time
from typing import Any

logger = logging.getLogger(__name__)


class MoralKeyPoolManager:
    """
    从 apipool-server 加载并管理 Moralis API Key 的池管理器。

    与 AsyncRpcServerPoolManager 类似的 Hybrid Mode:
      - 通过 apipool-server 认证
      - 从指定 pool 拉取所有 key (Moralis API Keys)
      - 本地维护 key 列表供 Provider 使用
      - 集成 StatsCollector 记录每次 API 调用，后台定时推送到 server
    """

    def __init__(self) -> None:
        self._service_url: str = ""
        self._pool_identifier: str = ""
        self._username: str = ""
        self._password: str = ""

        self._auth_token: str = ""
        self._token_expires_at: float = 0.0

        # 加载的 key 列表（Moralis API Key 字符串）
        self._keys: list[str] = []
        self._loaded_at: float = 0.0

        # Stats 统计
        self.stats = None  # StatsCollector, 在 _init_stats 中赋值
        self._stats_report_url: str = ""
        self._stats_report_token: str = ""
        self._stats_report_interval: float = 30.0
        self._stats_report_task: asyncio.Task | None = None
        self._client_id: str = f"{platform.node()}:{os.getpid()}"

    @classmethod
    async def create(
        cls,
        service_url: str,
        pool_identifier: str,
        username: str,
        password: str,
        stats_report_interval: float = 30.0,
    ) -> "MoralKeyPoolManager":
        """工厂方法：认证 + 拉取 keys + 初始化 stats"""
        instance = cls()
        instance._service_url = service_url.rstrip("/")
        instance._pool_identifier = pool_identifier
        instance._username = username
        instance._password = password
        instance._stats_report_interval = stats_report_interval

        await instance._authenticate()
        await instance._load_keys()
        instance._init_stats()

        # 启动后台 stats 推送任务
        await instance._astart_stats_report()

        logger.info(
            f"[moralis-pool] Pool ready: {service_url} "
            f"pool={pool_identifier}, keys={len(instance._keys)}, stats=enabled"
        )
        return instance

    async def _authenticate(self) -> None:
        """向 apipool-server 认证"""
        from apipool.client import alogin

        tokens = await alogin(
            service_url=self._service_url,
            username=self._username,
            password=self._password,
        )
        self._auth_token = tokens["access_token"]
        expires_in = tokens.get("expires_in", 3600)
        self._token_expires_at = time.time() + expires_in * 0.9
        logger.debug(f"[moralis-pool] Authenticated (expires={expires_in}s)")

    async def _load_keys(self) -> None:
        """从 server 拉取 Moralis API Key 列表"""
        from apipool.client import aget_keys

        raw_keys = await aget_keys(
            service_url=self._service_url,
            pool_identifier=self._pool_identifier,
            auth_token=self._auth_token,
        )

        # 过滤空值，去重
        seen = set()
        result: list[str] = []
        for k in raw_keys:
            if k is None or (isinstance(k, str) and not k.strip()):
                continue
            s = str(k).strip()
            if s and s not in seen:
                seen.add(s)
                result.append(s)

        self._keys = result
        self._loaded_at = time.time()

        # 同步注册新 key 到 stats collector
        self._register_keys_in_stats()

        logger.info(
            f"[moralis-pool] Loaded {len(self._keys)} keys "
            f"from pool '{self._pool_identifier}'"
        )

    # ── Stats 统计 ──

    def _init_stats(self) -> None:
        """初始化本地 StatsCollector"""
        from apipool.stats import StatsCollector
        from sqlalchemy import create_engine

        # 使用临时目录存放 stats DB
        import tempfile
        db_dir = os.path.join(tempfile.gettempdir(), "apipool_stats")
        os.makedirs(db_dir, exist_ok=True)
        # 对 pool_identifier 做安全文件名处理
        safe_pool = self._pool_identifier.replace("/", "_").replace("\\", "_").replace(":", "_")
        db_path = os.path.join(db_dir, f"moralis_{safe_pool}.db")

        engine = create_engine(f"sqlite:///{db_path}")
        self.stats = StatsCollector(engine=engine)
        self._stats_report_url = self._service_url
        self._stats_report_token = self._auth_token

        # 注册当前 keys
        self._register_keys_in_stats()

        logger.info(
            f"[moralis-pool] Stats collector initialized: db={db_path}, "
            f"report_url={self._stats_report_url}, interval={self._stats_report_interval}s"
        )

    def _register_keys_in_stats(self) -> None:
        """将当前 keys 注册到 StatsCollector（确保 add_event 不会丢弃事件）"""
        if self.stats is None:
            return
        from apipool.stats import ApiKey as StatsApiKey
        ses = self.stats.create_session()
        try:
            for key in self._keys:
                existing = ses.query(StatsApiKey).filter(StatsApiKey.key == key).first()
                if existing is None:
                    new_key = StatsApiKey(key=key)
                    ses.add(new_key)
            ses.commit()
        finally:
            ses.close()
        # 刷新缓存
        self.stats._update_cache()

    def record_call(self, api_key: str, success: bool, latency: float,
                    method: str = "call", is_rate_limit: bool = False) -> None:
        """
        记录一次 Moralis API 调用事件。

        Args:
            api_key: 使用的 API key (掩码后的也可以，但需要能匹配到 stats DB 中的记录)
            success: 调用是否成功
            latency: 延迟（秒）
            method: 调用方法名
            is_rate_limit: 是否因速率限制失败
        """
        if self.stats is None:
            return

        from apipool.stats import StatusCollection

        if is_rate_limit:
            status_id = StatusCollection.c9_ReachLimit.id
        elif success:
            status_id = StatusCollection.c1_Success.id
        else:
            status_id = StatusCollection.c5_Failed.id

        self.stats.add_event(
            primary_key=api_key,
            status_id=status_id,
            latency=latency,
            method=method,
        )

    async def _astart_stats_report(self) -> None:
        """启动后台 stats 推送任务"""
        if not self._stats_report_url or self.stats is None:
            logger.info("[moralis-pool] Stats report DISABLED (no report_url or no stats)")
            return

        if self._stats_report_task is not None and not self._stats_report_task.done():
            logger.debug("[moralis-pool] Stats report task already running")
            return

        self._stats_report_task = asyncio.create_task(
            self._areport_loop(),
            name=f"moralis-stats-report-{self._pool_identifier}",
        )
        logger.info(
            f"[moralis-pool] Stats report task started: "
            f"url={self._stats_report_url}, interval={self._stats_report_interval}s"
        )

    async def _areport_loop(self) -> None:
        """后台定时推送 stats 事件到 server"""
        try:
            while True:
                await asyncio.sleep(self._stats_report_interval)
                try:
                    await self._ado_report()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.warning(f"[moralis-pool] Stats report failed: {e}")
        except asyncio.CancelledError:
            logger.debug("[moralis-pool] Stats report loop cancelled")

    async def _ado_report(self) -> None:
        """从 StatsCollector 取出事件，POST 到 server，成功后删除"""
        import httpx
        from apipool.stats import StatusCollection

        events = self.stats.fetch_events_batch(limit=100)
        if not events:
            return

        status_map = StatusCollection.get_mapper_id_to_description()
        report_events = []
        for evt in events:
            finished_at = evt["finished_at"]
            report_events.append({
                "key_identifier": evt["key_identifier"],
                "status": status_map.get(evt["status_id"], "unknown"),
                "latency": evt["latency"],
                "method": evt["method"],
                "finished_at": finished_at.isoformat() if finished_at else None,
            })

        logger.info(
            f"[moralis-pool] Reporting {len(report_events)} stats events to "
            f"{self._stats_report_url} (pool={self._pool_identifier}, client={self._client_id})"
        )

        async with httpx.AsyncClient() as client:
            url = f"{self._stats_report_url}/api/v1/stats/report"
            payload = {
                "pool_identifier": self._pool_identifier,
                "client_id": self._client_id,
                "events": report_events,
            }
            resp = await client.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {self._stats_report_token}"},
                timeout=10.0,
            )
            resp.raise_for_status()
            result = resp.json()

            if result.get("accepted", 0) > 0:
                self.stats.delete_events(events)
                logger.info(
                    f"[moralis-pool] Reported {len(report_events)} stats events, "
                    f"accepted={result['accepted']}"
                )
            else:
                logger.debug(f"[moralis-pool] Stats report response: {result}")

    def ensure_token_valid(self) -> None:
        """检查 token 是否过期，过期则重新认证并拉取 key"""
        if time.time() >= self._token_expires_at and self._username:
            logger.info("[moralis-pool] Token expiring, re-authenticating...")
            # 注意：这是同步方法中的异步操作标记
            # 实际重连由外部 async 方法调用
            raise RuntimeError("Token expired, call reload() to re-connect")

    async def reload(self) -> int:
        """
        重新认证并拉取 keys。
        Returns:
            新加载的 key 数量
        """
        await self._authenticate()
        await self._load_keys()
        return len(self._keys)

    # ── 公开属性 ──

    @property
    def all_keys(self) -> list[str]:
        """返回当前加载的所有 Moralis API Key（副本，防止修改）"""
        return list(self._keys)

    @property
    def count(self) -> int:
        """当前 key 数量"""
        return len(self._keys)

    @property
    def pool_identifier(self) -> str:
        return self._pool_identifier

    @property
    def service_url(self) -> str:
        return self._service_url

    @property
    def loaded_at(self) -> float:
        return self._loaded_at

    @property
    def is_ready(self) -> bool:
        """是否有可用的 key"""
        return len(self._keys) > 0

    def get_status_snapshot(self) -> dict[str, Any]:
        """返回状态快照（供 API 使用），所有字段使用 snake_case"""
        return {
            "pool_type": "MoralKeyPool",
            "service_url": self._service_url,
            "pool_identifier": self._pool_identifier,
            "key_count": len(self._keys),
            "loaded_at": self._loaded_at,
            "is_ready": self.is_ready,
            "stats_enabled": self.stats is not None,
            "stats_report_url": self._stats_report_url,
        }

    def close(self) -> None:
        """清理资源"""
        # 取消后台 stats 推送任务
        if self._stats_report_task is not None and not self._stats_report_task.done():
            self._stats_report_task.cancel()
            self._stats_report_task = None

        # 关闭 stats collector
        if self.stats is not None:
            try:
                self.stats.close()
            except Exception:
                pass
            self.stats = None

        self._auth_token = ""
        self._keys = []
        self._token_expires_at = 0.0
        logger.info("[moralis-pool] Connection closed")

    def __repr__(self) -> str:
        return (
            f"MoralKeyPoolManager(pool={self._pool_identifier!r}, "
            f"keys={len(self._keys)}, ready={self.is_ready})"
        )


# ── 全局单例 ──

_global_mgr: MoralKeyPoolManager | None = None


def get_moralis_key_pool() -> MoralKeyPoolManager | None:
    """获取全局单例（可能为 None 如果未初始化）"""
    return _global_mgr


async def init_moralis_key_pool() -> MoralKeyPoolManager | None:
    """
    从全局配置初始化全局 MoralKeyPoolManager 单例。
    需要配置 moralis_pool_identifier + apipool-server 连接信息。
    """
    global _global_mgr

    from config.model import settings

    pool_id = settings.moralis_pool_identifier
    server_url = settings.apipool_server_url
    username = settings.apipool_username
    password = settings.apipool_password

    if not pool_id or not server_url or not username or not password:
        logger.info("[moralis-pool] Not configured, skipping initialization")
        _global_mgr = None
        return None

    try:
        mgr = await MoralKeyPoolManager.create(
            service_url=server_url,
            pool_identifier=pool_id,
            username=username,
            password=password,
        )
        _global_mgr = mgr
        return mgr
    except Exception as e:
        logger.error(f"[moralis-pool] Initialization failed: {e}", exc_info=True)
        _global_mgr = None
        return None


async def reload_moralis_key_pool() -> dict[str, Any]:
    """重新加载全局 MoralKeyPoolManager（API 端点调用）"""
    global _global_mgr

    if _global_mgr is None:
        # 尝试首次初始化
        mgr = await init_moralis_key_pool()
        if mgr is None:
            raise RuntimeError(
                "Moralis key pool not configured. "
                "Set moralis_pool_identifier + apipool-server connection in settings."
            )
        return {
            "status": "ok",
            "message": "Initialized moralis key pool",
            **mgr.get_status_snapshot(),
        }

    try:
        count = await _global_mgr.reload()
        return {
            "status": "ok",
            "message": f"Reloaded {count} keys",
            **_global_mgr.get_status_snapshot(),
        }
    except Exception as e:
        raise RuntimeError(f"Failed to reload moralis key pool: {e}") from e
