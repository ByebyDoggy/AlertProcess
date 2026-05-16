"""
API 契约层 - 规则链执行相关的请求和响应模型

定义规则链执行历史、日志、监控等 API 的契约。
"""

from pydantic import BaseModel, Field
from typing import Optional, Any, Literal
from datetime import datetime


# ============================================
# 执行历史
# ============================================

class ExecutionStatus(BaseModel):
    """执行状态"""
    status: Literal["pending", "running", "success", "failed", "timeout"] = Field(
        ..., description="执行状态"
    )
    started_at: Optional[datetime] = Field(None, description="开始时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")
    duration_ms: Optional[float] = Field(None, description="执行耗时（毫秒）")


class ExecutionHistoryResponse(BaseModel):
    """执行历史响应"""
    execution_id: str = Field(..., description="执行 ID")
    chain_id: str = Field(..., description="规则链 ID")
    chain_name: str = Field(..., description="规则链名称")
    status: Literal["pending", "running", "success", "failed", "timeout"] = Field(
        ..., description="执行状态"
    )
    started_at: datetime = Field(..., description="开始时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")
    duration_ms: Optional[float] = Field(None, description="执行耗时（毫秒）")
    input_data: dict[str, Any] = Field(..., description="输入数据")
    output_data: Optional[dict[str, Any]] = Field(None, description="输出数据")
    error: Optional[str] = Field(None, description="错误信息")
    node_executions: list[dict[str, Any]] = Field(..., description="节点执行详情")

    model_config = {"from_attributes": True}


class ExecutionHistoryListRequest(BaseModel):
    """执行历史列表查询请求"""
    skip: int = Field(default=0, ge=0, description="跳过记录数")
    limit: int = Field(default=100, ge=1, le=1000, description="返回记录数")
    chain_id: Optional[str] = Field(None, description="按规则链 ID 过滤")
    status: Optional[Literal["pending", "running", "success", "failed", "timeout"]] = Field(
        None, description="按状态过滤"
    )
    start_time: Optional[datetime] = Field(None, description="开始时间")
    end_time: Optional[datetime] = Field(None, description="结束时间")


class ExecutionHistoryListResponse(BaseModel):
    """执行历史列表响应"""
    total: int = Field(..., description="总记录数")
    items: list[ExecutionHistoryResponse] = Field(..., description="执行历史列表")
    skip: int = Field(..., description="跳过记录数")
    limit: int = Field(..., description="返回记录数")


# ============================================
# 执行日志
# ============================================

class ExecutionLogEntry(BaseModel):
    """执行日志条目"""
    timestamp: datetime = Field(..., description="日志时间")
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(..., description="日志级别")
    node_id: Optional[str] = Field(None, description="节点 ID")
    node_type: Optional[str] = Field(None, description="节点类型")
    message: str = Field(..., description="日志消息")
    metadata: Optional[dict[str, Any]] = Field(None, description="附加元数据")


class ExecutionLogResponse(BaseModel):
    """执行日志响应"""
    execution_id: str = Field(..., description="执行 ID")
    logs: list[ExecutionLogEntry] = Field(..., description="日志列表")


# ============================================
# 执行统计
# ============================================

class ExecutionStatsResponse(BaseModel):
    """执行统计响应"""
    total_executions: int = Field(..., description="总执行次数")
    success_count: int = Field(..., description="成功次数")
    failed_count: int = Field(..., description="失败次数")
    avg_duration_ms: float = Field(..., description="平均执行耗时（毫秒）")
    by_chain: dict[str, int] = Field(..., description="按规则链统计")
    by_status: dict[str, int] = Field(..., description="按状态统计")
    recent_24h: int = Field(..., description="最近 24 小时执行次数")
