"""
规则链路由 - CRUD 操作

使用 Service 层处理业务逻辑，Router 只负责 HTTP 请求/响应。
"""

from typing import Optional, List
from fastapi import APIRouter, Header, HTTPException, Depends

from dependencies import get_rule_chain_service
from services import RuleChainService
from contracts.rule_chain import (
    RuleChainCreateRequest,
    RuleChainUpdateRequest,
    RuleChainResponse,
    RuleChainListResponse,
)


router = APIRouter()


def _auth_with_key(x_api_key: Optional[str], api_key: Optional[str]) -> None:
    """API Key 认证"""
    from config import settings

    auth_key = x_api_key if x_api_key else api_key
    if not auth_key or auth_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.get("/", response_model=List[RuleChainResponse])
async def list_rule_chains(
    skip: int = 0,
    limit: int = 100,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,
    service: RuleChainService = Depends(get_rule_chain_service),
):
    """获取规则链列表"""
    _auth_with_key(x_api_key, api_key)
    return service.list_chains(skip=skip, limit=limit)


@router.get("/{chain_id}", response_model=RuleChainResponse)
async def get_rule_chain(
    chain_id: str,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,
    service: RuleChainService = Depends(get_rule_chain_service),
):
    """获取单个规则链"""
    _auth_with_key(x_api_key, api_key)
    return service.get_chain(chain_id)


@router.post("/", response_model=RuleChainResponse)
async def create_rule_chain(
    chain_data: RuleChainCreateRequest,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,
    service: RuleChainService = Depends(get_rule_chain_service),
):
    """创建规则链"""
    _auth_with_key(x_api_key, api_key)
    return service.create_chain(chain_data)


@router.put("/{chain_id}", response_model=RuleChainResponse)
async def update_rule_chain(
    chain_id: str,
    chain_data: RuleChainUpdateRequest,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,
    service: RuleChainService = Depends(get_rule_chain_service),
):
    """更新规则链"""
    _auth_with_key(x_api_key, api_key)
    return service.update_chain(chain_id, chain_data)


@router.delete("/{chain_id}")
async def delete_rule_chain(
    chain_id: str,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,
    service: RuleChainService = Depends(get_rule_chain_service),
):
    """删除规则链"""
    _auth_with_key(x_api_key, api_key)
    return service.delete_chain(chain_id)


@router.get("/search/", response_model=List[RuleChainResponse])
async def search_rule_chains(
    keyword: Optional[str] = None,
    enabled: Optional[bool] = None,
    skip: int = 0,
    limit: int = 100,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,
    service: RuleChainService = Depends(get_rule_chain_service),
):
    """搜索规则链"""
    _auth_with_key(x_api_key, api_key)
    return service.search_chains(keyword=keyword, enabled=enabled, skip=skip, limit=limit)


@router.patch("/{chain_id}/toggle", response_model=RuleChainResponse)
async def toggle_rule_chain(
    chain_id: str,
    enabled: bool,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,
    service: RuleChainService = Depends(get_rule_chain_service),
):
    """切换规则链启用状态"""
    _auth_with_key(x_api_key, api_key)
    return service.toggle_enabled(chain_id, enabled)
