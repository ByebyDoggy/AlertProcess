"""
Pool 配置管理 API
=================
管理每条链的 apipool-server pool_identifier 配置。

端点:
  GET    /pool-config/                 获取所有链的 pool 配置
  GET    /pool-config/chains           获取支持的链列表
  GET    /pool-config/status           获取所有池的运行状态
  PUT    /pool-config/{chain_id}       更新指定链的 pool_identifier
  POST   /pool-config/health-check     执行健康检查
  POST   /pool-config/reload           重新加载配置
  POST   /pool-config/test-connection  测试单个 RPC URL 连通性
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
poolConfigRouter = APIRouter(prefix="/pool-config", tags=["pool-config"])


# ──────────────── Pydantic Schema ────────────────

class PoolIdentifierUpdate(BaseModel):
    """更新链的 pool_identifier"""
    pool_identifier: str = Field(
        ..., min_length=1, max_length=128,
        description="Pool identifier in apipool-server"
    )


class PoolConfigItem(BaseModel):
    """单条链的 pool 配置"""
    chain_id: int
    chain_name: str
    pool_identifier: str
    status: str = "unknown"  # ok / error / unknown


class TestConnectionRequest(BaseModel):
    """测试连接请求"""
    url: str = Field(..., description="要测试的 RPC URL")
    timeout: int = Field(default=15, ge=3, le=60)


class ServerConfigUpdate(BaseModel):
    """更新 apipool-server 全局连接配置"""
    server_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


# ──────────────── API 端点 ────────────────

@poolConfigRouter.get("/", response_model=list[dict])
async def get_pool_config(x_api_key: Optional[str] = Header(None)):
    """获取所有链的 pool_identifier 配置及连接状态"""
    from config.model import settings
    from detectors.trace.provider import CHAIN_META

    pool_map = settings.apipool_pool_map or {}
    result = []

    # 已配置的链
    configured_chains = set()
    for key, pool_id in pool_map.items():
        cid = int(key)
        configured_chains.add(cid)
        meta = CHAIN_META.get(cid, {})
        result.append({
            "chain_id": cid,
            "chain_name": meta.get("name", f"Chain-{cid}"),
            "pool_identifier": pool_id,
            "configured": True,
        })

    # 支持但未配置的链
    for cid, meta in CHAIN_META.items():
        if cid not in configured_chains:
            result.append({
                "chain_id": cid,
                "chain_name": meta.get("name", f"Chain-{cid}"),
                "pool_identifier": "",
                "configured": False,
            })

    result.sort(key=lambda x: x["chain_id"])
    return result


@poolConfigRouter.get("/chains", response_model=list[dict])
async def list_supported_chains():
    """返回支持的所有链信息"""
    from detectors.trace.provider import MultiRpcClient
    return MultiRpcClient.supported_chains()


@poolConfigRouter.get("/status", response_model=list[dict])
async def get_pool_status():
    """获取所有池的运行时状态 (健康节点数、连接信息等)"""
    from detectors.trace.provider import get_rpc_client

    client = get_rpc_client()
    if not client._initialized:
        return []
    return await client.get_pool_status()


# ──────────────── Server 全局配置 API (必须在 /{chain_id} 之前!) ────────────────

@poolConfigRouter.get("/server-config", response_model=dict)
async def get_server_config():
    """获取当前 apipool-server 全局连接配置 (密码脱敏)"""
    from config.model import settings

    return {
        "server_url": settings.apipool_server_url or "",
        "username": settings.apipool_username or "",
        "password": "******" if settings.apipool_password else "",
        "has_password": bool(settings.apipool_password),
    }


@poolConfigRouter.put("/server-config", response_model=dict)
async def update_server_config(body: ServerConfigUpdate):
    """
    更新 apipool-server 全局连接配置（持久化到 .env）。

    注意：修改 server_url / username / password 后需要点击 Reload 重新初始化连接池。
    密码传入空字符串表示不修改（保留原值）。
    """
    from config.model import settings

    if body.server_url is not None:
        settings.apipool_server_url = body.server_url
    if body.username is not None:
        settings.apipool_username = body.username
    # 仅当传入非空密码时才更新
    if body.password is not None and body.password and body.password != "******":
        settings.apipool_password = body.password

    # 持久化到 .env
    try:
        settings.persist_to_env({
            "apipool_server_url": "apipool_server_url",
            "apipool_username": "apipool_username",
            "apipool_password": "apipool_password",
        })
    except Exception as e:
        logger.warning(f"[pool-config] Persist server config to .env failed: {e}", exc_info=True)

    return {
        "status": "ok",
        "message": "Server configuration saved (persisted). Click Reload & Connect to apply.",
        "server_url": settings.apipool_server_url or "",
        "username": settings.apipool_username or "",
    }


@poolConfigRouter.put("/{chain_id}", response_model=dict)
async def update_pool_identifier(
    chain_id: int,
    body: PoolIdentifierUpdate,
    x_api_key: Optional[str] = Header(None),
):
    """
    更新指定链的 pool_identifier。
    运行时生效，无需重启服务。
    """
    from detectors.trace.provider import get_rpc_client, CHAIN_META

    if chain_id not in CHAIN_META:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported chain_id={chain_id}. "
                   f"Supported: {list(CHAIN_META.keys())}"
        )

    client = get_rpc_client()
    try:
        result = await client.update_pool_identifier(chain_id, body.pool_identifier)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update pool_identifier for chain {chain_id}: {str(e)}"
        ) from e


@poolConfigRouter.post("/health-check", response_model=list[dict])
async def health_check(chain_id: Optional[int] = None):
    """执行健康检查 (通过 apipool-server status API)"""
    from detectors.trace.provider import get_rpc_client

    client = get_rpc_client()
    if not client._initialized:
        raise HTTPException(status_code=503, detail="Pool client not initialized")
    return await client.run_health_checks(chain_id=chain_id)


@poolConfigRouter.post("/reload")
async def reload_config():
    """重新从配置加载所有 pool 连接"""
    from detectors.trace.provider import get_rpc_client

    client = get_rpc_client()
    try:
        await client.reload_config()
        pools = await client.get_pool_status()
        return {
            "status": "ok",
            "message": "Configuration reloaded successfully",
            "totalChains": len(pools),
            "chains": [p.get("chainName", "") for p in pools],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@poolConfigRouter.post("/test-connection")
async def test_connection(body: TestConnectionRequest):
    """测试单个 RPC URL 的连通性 (直接测试, 不经过 apipool-server)"""
    from detectors.trace.provider import get_rpc_client

    client = get_rpc_client()
    return await client.test_connection(body.url, timeout=body.timeout)
