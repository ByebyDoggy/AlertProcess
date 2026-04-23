"""
Pool 配置管理 API
=================
管理每条链的 apipool-server pool_identifier 配置 + Moralis API Key 池配置。

端点:
  ── RPC 池管理 (原有) ──
  GET    /pool-config/                 获取所有链的 pool 配置
  GET    /pool-config/chains           获取支持的链列表
  GET    /pool-config/status           获取所有池的运行状态
  PUT    /pool-config/{chain_id}       更新指定链的 pool_identifier
  POST   /pool-config/health-check     执行健康检查
  POST   /pool-config/reload           重新加载配置
  POST   /pool-config/test-connection  测试单个 RPC URL 连通性

  ── Moralis API Key 池管理 (新增) ──
  GET    /pool-config/moralis-status   获取 MoralKeyPool 状态
  PUT    /pool-config/moralis-config   更新 moralis_pool_identifier
  POST   /pool-config/moralis-reload   重载 MoralKeyPool

  ── Server 全局配置 (共用) ──
  GET    /pool-config/server-config    获取 apipool-server 连接配置（密码脱敏）
  PUT    /pool-config/server-config    更新 server_url/username/password 并持久化到 .env
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


class MoralisPoolConfigUpdate(BaseModel):
    """更新 MoralKeyPool 的 pool_identifier"""
    pool_identifier: str = Field(
        ..., min_length=1, max_length=128,
        description="Pool identifier in apipool-server that stores Moralis API Keys"
    )


class BlockTimeConfigUpdate(BaseModel):
    """更新单条链的区块时间配置"""
    chain_id: int = Field(..., ge=0, description="Chain ID")
    block_time_seconds: float = Field(
        ...,
        gt=0,
        le=3600,
        description="Single block time in seconds (e.g. 12 for Ethereum)",
    )


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


# ──────────────── Moralis API Key 池管理 (必须在 /{chain_id} 之前!) ────────────────

@poolConfigRouter.get("/moralis-status", response_model=dict)
async def get_moralis_pool_status():
    """获取 MoralKeyPool 当前状态（key 数量、pool identifier、是否就绪）"""
    from nodes.context.providers.moralis_key_pool import get_moralis_key_pool
    from config.model import settings

    mgr = get_moralis_key_pool()
    if mgr is None:
        return {
            "initialized": False,
            "is_ready": False,
            "configured": bool(settings.moralis_pool_identifier),
            "pool_identifier": settings.moralis_pool_identifier or "",
            "key_count": 0,
            "service_url": settings.apipool_server_url or "",
        }

    status = mgr.get_status_snapshot()
    status["initialized"] = True
    return status


@poolConfigRouter.put("/moralis-config", response_model=dict)
async def update_moralis_pool_config(body: MoralisPoolConfigUpdate):
    """
    更新 moralis_pool_identifier 配置（持久化到 .env）。
    修改后需要点击 Reload 重新加载 Key 池。
    """
    from config.model import settings

    settings.moralis_pool_identifier = body.pool_identifier

    # 持久化到 .env
    try:
        settings.persist_to_env({
            "moralis_pool_identifier": "moralis_pool_identifier",
        })
    except Exception as e:
        logger.warning(f"[pool-config] Persist moralis config to .env failed: {e}", exc_info=True)

    return {
        "status": "ok",
        "message": f"Moralis pool config saved: {body.pool_identifier}. Click Reload & Connect to apply.",
        "pool_identifier": body.pool_identifier,
    }


@poolConfigRouter.post("/moralis-reload", response_model=dict)
async def reload_moralis_pool():
    """重新加载 MoralKeyPool（从 apipool-server 重新认证并拉取 keys）"""
    from nodes.context.providers.moralis_key_pool import reload_moralis_key_pool

    try:
        result = await reload_moralis_key_pool()
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reload moralis pool: {str(e)}") from e


# ──────────────── 区块时间配置 (用于地址年龄估算) ────────────────

@poolConfigRouter.get("/block-time-config", response_model=dict)
async def get_block_time_config():
    """
    获取所有链的区块时间配置。

    返回每条链的当前区块时间(秒)，包括用户自定义值和默认值。
    前端用此数据渲染可编辑的配置表单。
    """
    from nodes.context.providers.moralis_address import DEFAULT_BLOCK_TIME
    from config.model import settings

    # 合并: 用户配置覆盖默认值
    result = {}
    for chain_id, default_sec in DEFAULT_BLOCK_TIME.items():
        user_val = None
        cfg = settings.block_time_config
        if isinstance(cfg, dict):
            user_val = cfg.get(chain_id) or cfg.get(str(chain_id))
        result[str(chain_id)] = {
            "chain_id": chain_id,
            "block_time_seconds": float(user_val) if user_val is not None else default_sec,
            "default_seconds": default_sec,
            "is_customized": user_val is not None,
        }

    return {"chains": result}


@poolConfigRouter.put("/block-time-config", response_model=dict)
async def update_block_time_config(body: BlockTimeConfigUpdate):
    """
    更新指定链的单块时间（秒）。

    修改后立即生效，同时持久化到 .env 文件。
    传 block_time_seconds 为 null 可恢复为默认值。
    """
    from config.model import settings
    from nodes.context.providers.moralis_address import DEFAULT_BLOCK_TIME

    chain_id = body.chain_id
    new_sec = body.block_time_seconds
    default_sec = DEFAULT_BLOCK_TIME.get(chain_id, 12.0)

    # 如果等于默认值，移除自定义配置（恢复默认）
    if abs(new_sec - default_sec) < 0.001:
        cfg = settings.block_time_config
        if isinstance(cfg, dict):
            cfg.pop(chain_id, None)
            cfg.pop(str(chain_id), None)
    else:
        cfg = settings.block_time_config
        if not isinstance(cfg, dict):
            cfg = {}
            settings.block_time_config = cfg
        cfg[chain_id] = new_sec

    # 持久化到 .env
    try:
        settings.persist_to_env({
            "block_time_config": "block_time_config",
        })
    except Exception as e:
        logger.warning(f"[pool-config] Persist block time config failed: {e}", exc_info=True)

    return {
        "status": "ok",
        "message": f"Chain {chain_id} block time updated to {new_sec}s",
        "chain_id": chain_id,
        "block_time_seconds": new_sec,
    }


# ──────────────── RPC Pool: 按 chain_id 更新 (必须在 Moralis 之后!) ────────────────

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
