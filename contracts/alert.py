"""
API 契约层 - 告警相关的请求和响应模型

定义告警提交、查询、统计等 API 的契约。
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


# ============================================
# 告警严重等级枚举
# ============================================

SeverityLevel = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", "UNKNOWN"]


# ============================================
# 告警提交
# ============================================

class AlertSubmitRequest(BaseModel):
    """提交告警请求"""
    chain_id: int = Field(..., description="链 ID")
    tx_hash: str = Field(..., min_length=1, description="交易哈希")
    attacked_address: Optional[str] = Field(None, description="被攻击地址")
    exploiter_address: Optional[str] = Field(None, description="攻击者地址")


class AlertSubmitResponse(BaseModel):
    """提交告警响应"""
    status: Literal["success", "failed"] = Field(..., description="提交状态")
    alert_id: str = Field(..., description="告警 ID")
    message: Optional[str] = Field(None, description="附加消息")


# ============================================
# 告警查询
# ============================================

class AlertResponse(BaseModel):
    """告警详情响应"""
    alert_id: str = Field(..., description="告警 ID")
    attacked_address: Optional[str] = Field(None, description="被攻击地址")
    exploiter_address: Optional[str] = Field(None, description="攻击者地址")
    severity: SeverityLevel = Field(..., description="严重等级")
    message: str = Field(..., description="告警消息")
    timestamp: datetime = Field(..., description="告警时间")
    risk_score: str = Field(..., description="风险评分")
    tags: Optional[list[str]] = Field(None, description="告警标签")
    metadata: Optional[dict] = Field(None, description="附加元数据")

    model_config = {"from_attributes": True}


class AlertListRequest(BaseModel):
    """告警列表查询请求"""
    skip: int = Field(default=0, ge=0, description="跳过记录数")
    limit: int = Field(default=100, ge=1, le=1000, description="返回记录数")
    severity: Optional[SeverityLevel] = Field(None, description="按严重等级过滤")
    chain_id: Optional[int] = Field(None, description="按链 ID 过滤")
    start_time: Optional[datetime] = Field(None, description="开始时间")
    end_time: Optional[datetime] = Field(None, description="结束时间")


class AlertListResponse(BaseModel):
    """告警列表响应"""
    total: int = Field(..., description="总记录数")
    alerts: list[AlertResponse] = Field(..., description="告警列表")
    skip: int = Field(..., description="跳过记录数")
    limit: int = Field(..., description="返回记录数")


# ============================================
# 告警统计
# ============================================

class AlertStatsResponse(BaseModel):
    """告警统计响应"""
    total: int = Field(..., description="总告警数")
    by_severity: dict[str, int] = Field(..., description="按严重等级统计")
    by_chain: dict[str, int] = Field(..., description="按链统计")
    recent_24h: int = Field(..., description="最近 24 小时告警数")
    recent_7d: int = Field(..., description="最近 7 天告警数")
