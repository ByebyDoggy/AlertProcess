"""
API 契约层 - 统一导出所有契约模型

这个包定义了前后端之间的 API 契约，独立于业务逻辑实现。
前端可以基于这些模型生成 TypeScript 类型定义。

使用方式:
    from contracts.rule_chain import RuleChainCreateRequest, RuleChainResponse
    from contracts.alert import AlertSubmitRequest, AlertListResponse
    from contracts.detector import TraceIngestRequest, DetectorExecuteResponse
    from contracts.execution import ExecutionHistoryResponse, ExecutionStatsResponse
"""

# 规则链相关契约
from contracts.rule_chain import (
    RuleNode,
    RuleEdge,
    RuleChainCreateRequest,
    RuleChainUpdateRequest,
    RuleChainResponse,
    RuleChainListResponse,
    ValidateRequest,
    ValidateError,
    ValidateResponse,
    ExecuteRequest,
    ExecuteResponse,
    NodeTypeResponse,
    NodeTypesResponse,
)

# 告警相关契约
from contracts.alert import (
    SeverityLevel,
    AlertSubmitRequest,
    AlertSubmitResponse,
    AlertResponse,
    AlertListRequest,
    AlertListResponse,
    AlertStatsResponse,
)

# 检测器相关契约
from contracts.detector import (
    TraceIngestRequest,
    TraceIngestResponse,
    TraceQueryRequest,
    TraceQueryResponse,
    DetectorExecuteRequest,
    DetectorExecuteResponse,
)

# 执行相关契约
from contracts.execution import (
    ExecutionStatus,
    ExecutionHistoryResponse,
    ExecutionHistoryListRequest,
    ExecutionHistoryListResponse,
    ExecutionLogEntry,
    ExecutionLogResponse,
    ExecutionStatsResponse,
)

__all__ = [
    # 规则链
    "RuleNode",
    "RuleEdge",
    "RuleChainCreateRequest",
    "RuleChainUpdateRequest",
    "RuleChainResponse",
    "RuleChainListResponse",
    "ValidateRequest",
    "ValidateError",
    "ValidateResponse",
    "ExecuteRequest",
    "ExecuteResponse",
    "NodeTypeResponse",
    "NodeTypesResponse",
    # 告警
    "SeverityLevel",
    "AlertSubmitRequest",
    "AlertSubmitResponse",
    "AlertResponse",
    "AlertListRequest",
    "AlertListResponse",
    "AlertStatsResponse",
    # 检测器
    "TraceIngestRequest",
    "TraceIngestResponse",
    "TraceQueryRequest",
    "TraceQueryResponse",
    "DetectorExecuteRequest",
    "DetectorExecuteResponse",
    # 执行
    "ExecutionStatus",
    "ExecutionHistoryResponse",
    "ExecutionHistoryListRequest",
    "ExecutionHistoryListResponse",
    "ExecutionLogEntry",
    "ExecutionLogResponse",
    "ExecutionStatsResponse",
]
