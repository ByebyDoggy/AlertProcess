"""
规则链路由 - 校验和执行

处理规则链的校验、执行等操作。
"""

from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Depends

from dependencies import get_rule_chain_service
from services import RuleChainService
from contracts.rule_chain import (
    ValidateRequest,
    ValidateResponse,
    ExecuteRequest,
    ExecuteResponse,
)


router = APIRouter()


def _auth_with_key(x_api_key: Optional[str], api_key: Optional[str]) -> None:
    """API Key 认证"""
    from config import settings

    auth_key = x_api_key if x_api_key else api_key
    if not auth_key or auth_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.post("/validate", response_model=ValidateResponse)
async def validate_chain(
    data: ValidateRequest,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,
    service: RuleChainService = Depends(get_rule_chain_service),
):
    """
    验证规则链配置是否合法

    使用新引擎 ChainParser + ChainValidator 进行完整校验。
    """
    _auth_with_key(x_api_key, api_key)
    return service.validate_chain(data)


@router.post("/execute", response_model=ExecuteResponse)
async def execute_chain(
    data: ExecuteRequest,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,
    service: RuleChainService = Depends(get_rule_chain_service),
):
    """
    执行规则链

    可以选择 dry_run 模式进行测试。
    """
    _auth_with_key(x_api_key, api_key)
    return await service.execute_chain(data)
