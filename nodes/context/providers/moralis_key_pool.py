"""
Moralis API Key Pool Manager
============================
从 apipool-server 加载 Moralis API Key 列表，提供多 Key 轮换和故障切换。

架构:
  ┌──────────────────────────────────────────────┐
  │  MoralKeyPoolManager                          │
  │                                              │
  │  alogin() → aget_keys(pool_id) → _keys[]    │
  │                                              │
  │  get_key(index) → 按索引获取 key             │
  │  all_keys → 完整列表（只读）                  │
  │  count → key 数量                             │
  │  reload() → 重新从 server 拉取                │
  │  close() → 清理资源                            │
  └──────────────────────────────────────────────┘

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

    @classmethod
    async def create(
        cls,
        service_url: str,
        pool_identifier: str,
        username: str,
        password: str,
    ) -> "MoralKeyPoolManager":
        """工厂方法：认证 + 拉取 keys"""
        instance = cls()
        instance._service_url = service_url.rstrip("/")
        instance._pool_identifier = pool_identifier
        instance._username = username
        instance._password = password

        await instance._authenticate()
        await instance._load_keys()

        logger.info(
            f"[moralis-pool] Pool ready: {service_url} "
            f"pool={pool_identifier}, keys={len(instance._keys)}"
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

        logger.info(
            f"[moralis-pool] Loaded {len(self._keys)} keys "
            f"from pool '{self._pool_identifier}'"
        )

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
        }

    def close(self) -> None:
        """清理资源"""
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
