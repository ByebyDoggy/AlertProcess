"""
API 契约层 - 检测器相关的请求和响应模型

定义检测器数据摄入、Trace 查询等 API 的契约。
"""

from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime


# ============================================
# Trace 数据摄入
# ============================================

class TraceIngestRequest(BaseModel):
    """Trace 数据摄入请求"""
    chain_id: int = Field(..., description="链 ID")
    tx_hash: str = Field(..., min_length=1, description="交易哈希")
    trace_data: dict[str, Any] = Field(..., description="Trace 数据")
    block_number: Optional[int] = Field(None, description="区块号")
    timestamp: Optional[datetime] = Field(None, description="交易时间")


class TraceIngestResponse(BaseModel):
    """Trace 数据摄入响应"""
    status: str = Field(..., description="摄入状态")
    trace_id: str = Field(..., description="Trace ID")
    message: Optional[str] = Field(None, description="附加消息")


# ============================================
# Trace 查询
# ============================================

class TraceQueryRequest(BaseModel):
    """Trace 查询请求"""
    chain_id: int = Field(..., description="链 ID")
    tx_hash: str = Field(..., min_length=1, description="交易哈希")


class TraceQueryResponse(BaseModel):
    """Trace 查询响应"""
    found: bool = Field(..., description="是否找到")
    trace_id: Optional[str] = Field(None, description="Trace ID")
    chain_id: Optional[int] = Field(None, description="链 ID")
    tx_hash: Optional[str] = Field(None, description="交易哈希")
    trace_data: Optional[dict[str, Any]] = Field(None, description="Trace 数据")
    block_number: Optional[int] = Field(None, description="区块号")
    timestamp: Optional[datetime] = Field(None, description="交易时间")


# ============================================
# 检测器执行
# ============================================

class DetectorExecuteRequest(BaseModel):
    """检测器执行请求"""
    detector_type: str = Field(..., description="检测器类型")
    trace_data: dict[str, Any] = Field(..., description="Trace 数据")
    config: Optional[dict[str, Any]] = Field(None, description="检测器配置")


class DetectorExecuteResponse(BaseModel):
    """检测器执行响应"""
    success: bool = Field(..., description="是否执行成功")
    detector_type: str = Field(..., description="检测器类型")
    score: float = Field(..., description="检测评分")
    matched_patterns: list[str] = Field(..., description="匹配的模式")
    details: dict[str, Any] = Field(..., description="详细结果")
    error: Optional[str] = Field(None, description="错误信息")
