"""
告警路由 - 使用 Service 层

告警接收、查询、统计。
"""

from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Depends

from dependencies import get_alert_service
from services import AlertService
from contracts.alert import (
    AlertSubmitRequest,
    AlertSubmitResponse,
    AlertResponse,
    AlertListRequest,
    AlertListResponse,
    AlertStatsResponse,
)


router = APIRouter()


def _auth_with_key(x_api_key: Optional[str], api_key: Optional[str]) -> None:
    """API Key 认证"""
    from config import settings

    auth_key = x_api_key if x_api_key else api_key
    if not auth_key or auth_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.post("/submit", response_model=AlertSubmitResponse)
async def submit_alert(
    data: AlertSubmitRequest,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,
    service: AlertService = Depends(get_alert_service),
):
    """提交告警"""
    _auth_with_key(x_api_key, api_key)
    return service.submit_alert(data)


@router.get("/alerts", response_model=AlertListResponse)
async def list_alerts(
    skip: int = 0,
    limit: int = 100,
    severity: Optional[str] = None,
    chain_id: Optional[int] = None,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,
    service: AlertService = Depends(get_alert_service),
):
    """获取告警列表"""
    _auth_with_key(x_api_key, api_key)

    request = AlertListRequest(
        skip=skip,
        limit=limit,
        severity=severity,
        chain_id=chain_id,
    )

    return service.list_alerts(request)


@router.get("/alerts/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: str,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,
    service: AlertService = Depends(get_alert_service),
):
    """获取单个告警"""
    _auth_with_key(x_api_key, api_key)
    return service.get_alert(alert_id)


@router.get("/stats", response_model=AlertStatsResponse)
async def get_alert_stats(
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,
    service: AlertService = Depends(get_alert_service),
):
    """获取告警统计信息"""
    _auth_with_key(x_api_key, api_key)
    return service.get_stats()


@router.delete("/alerts/{alert_id}")
async def delete_alert(
    alert_id: str,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,
    service: AlertService = Depends(get_alert_service),
):
    """删除告警"""
    _auth_with_key(x_api_key, api_key)
    return service.delete_alert(alert_id)
