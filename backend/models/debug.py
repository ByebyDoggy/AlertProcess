"""
调试数据模型 — 脚本执行调试信息

用于存储和传输脚本执行过程中的调试信息，包括日志、变量快照、性能指标等。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class LogLevel(str, Enum):
    """日志级别"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class DebugLog(BaseModel):
    """调试日志条目"""
    timestamp: datetime = Field(default_factory=datetime.now, description="日志时间戳")
    level: LogLevel = Field(default=LogLevel.INFO, description="日志级别")
    message: str = Field(..., description="日志消息")
    line_number: int | None = Field(None, description="代码行号")
    context: dict[str, Any] | None = Field(None, description="上下文信息")


class VariableSnapshot(BaseModel):
    """变量快照"""
    name: str = Field(..., description="变量名")
    value: Any = Field(..., description="变量值")
    type_name: str = Field(..., description="变量类型")
    size_bytes: int | None = Field(None, description="内存占用（字节）")


class PerformanceMetrics(BaseModel):
    """性能指标"""
    execution_time_ms: float = Field(..., description="执行时间（毫秒）")
    memory_peak_mb: float | None = Field(None, description="峰值内存（MB）")
    cpu_time_ms: float | None = Field(None, description="CPU 时间（毫秒）")
    lines_executed: int | None = Field(None, description="执行的代码行数")


class DebugExecutionResult(BaseModel):
    """调试执行结果"""
    execution_id: str = Field(..., description="执行 ID")
    success: bool = Field(..., description="是否成功")
    result: Any = Field(None, description="执行结果")
    error: str | None = Field(None, description="错误信息")

    # 调试信息
    logs: list[DebugLog] = Field(default_factory=list, description="执行日志")
    variables: list[VariableSnapshot] = Field(default_factory=list, description="变量快照")
    performance: PerformanceMetrics = Field(..., description="性能指标")

    # 元数据
    script_code: str = Field(..., description="执行的脚本代码")
    started_at: datetime = Field(default_factory=datetime.now, description="开始时间")
    completed_at: datetime | None = Field(None, description="完成时间")


class DebugRunRequest(BaseModel):
    """调试运行请求"""
    script_code: str = Field(..., description="脚本代码", min_length=1, max_length=50000)
    context: dict[str, Any] = Field(default_factory=dict, description="上下文变量")
    timeout: float = Field(default=5.0, description="超时时间（秒）", ge=0.1, le=30.0)
    capture_variables: bool = Field(default=True, description="是否捕获变量快照")
    capture_logs: bool = Field(default=True, description="是否捕获日志")


class DebugSession(BaseModel):
    """调试会话"""
    session_id: str = Field(..., description="会话 ID")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    executions: list[DebugExecutionResult] = Field(default_factory=list, description="执行历史")
