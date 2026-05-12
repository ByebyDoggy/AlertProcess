"""
API 契约层 - 规则链相关的请求和响应模型

这些模型定义了前后端之间的 API 契约，独立于业务逻辑实现。
前端可以基于这些模型生成 TypeScript 类型定义。
"""

from pydantic import BaseModel, Field
from typing import Optional, Any, Literal
from datetime import datetime


# ============================================
# 规则链节点和边的定义
# ============================================

class RuleNode(BaseModel):
    """规则链节点定义"""
    id: str = Field(..., description="节点唯一标识")
    type: str = Field(..., description="节点类型（如 gas_price_detector）")
    label: str = Field(default="", description="节点显示名称")
    config: dict[str, Any] = Field(default_factory=dict, description="节点配置")
    position: dict[str, Any] = Field(
        default_factory=lambda: {"x": 0, "y": 0},
        description="节点在画布上的位置"
    )


class RuleEdge(BaseModel):
    """规则链边定义"""
    id: str = Field(default="", description="边唯一标识")
    source: str = Field(..., description="源节点 ID")
    source_port: str = Field(default="output", alias="sourcePort", description="源端口名称")
    target: str = Field(..., description="目标节点 ID")
    target_port: str = Field(default="input", alias="targetPort", description="目标端口名称")
    label: str = Field(default="", description="边显示标签")
    field_mapping: Optional[dict[str, Any]] = Field(
        default=None,
        alias="fieldMapping",
        description="字段映射配置"
    )
    input_transformer: Optional[dict[str, Any]] = Field(
        default=None,
        alias="inputTransformer",
        description="输入转换器配置"
    )

    model_config = {"populate_by_name": True}


# ============================================
# 规则链 CRUD 请求/响应
# ============================================

class RuleChainCreateRequest(BaseModel):
    """创建规则链请求"""
    name: str = Field(..., min_length=1, max_length=200, description="规则链名称")
    description: Optional[str] = Field(default="", max_length=1000, description="规则链描述")
    enabled: bool = Field(default=True, description="是否启用")
    nodes: list[RuleNode] = Field(default_factory=list, description="节点列表")
    edges: list[RuleEdge] = Field(default_factory=list, description="边列表")
    sequence_phases: list[dict[str, Any]] = Field(
        default_factory=list,
        description="序列阶段配置（用于拓扑排序）"
    )


class RuleChainUpdateRequest(BaseModel):
    """更新规则链请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=200, description="规则链名称")
    description: Optional[str] = Field(None, max_length=1000, description="规则链描述")
    enabled: Optional[bool] = Field(None, description="是否启用")
    nodes: Optional[list[RuleNode]] = Field(None, description="节点列表")
    edges: Optional[list[RuleEdge]] = Field(None, description="边列表")
    sequence_phases: Optional[list[dict[str, Any]]] = Field(None, description="序列阶段配置")


class RuleChainResponse(BaseModel):
    """规则链响应"""
    id: str = Field(..., description="规则链 ID")
    name: str = Field(..., description="规则链名称")
    description: Optional[str] = Field(None, description="规则链描述")
    enabled: bool = Field(..., description="是否启用")
    chain_config: dict = Field(..., description="规则链完整配置（包含 nodes 和 edges）")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    model_config = {"from_attributes": True}


class RuleChainListResponse(BaseModel):
    """规则链列表响应"""
    total: int = Field(..., description="总数")
    items: list[RuleChainResponse] = Field(..., description="规则链列表")


# ============================================
# 规则链校验
# ============================================

class ValidateRequest(BaseModel):
    """规则链校验请求"""
    nodes: list[RuleNode] = Field(..., description="节点列表")
    edges: list[RuleEdge] = Field(default_factory=list, description="边列表")


class ValidateError(BaseModel):
    """校验错误/警告"""
    type: Literal["error", "warning"] = Field(default="error", description="错误类型")
    code: str = Field(..., description="错误代码")
    severity: Literal["error", "warning"] = Field(default="error", description="严重程度")
    field: str = Field(default="", description="错误字段")
    field_path: str = Field(default="", description="字段路径")
    message: str = Field(..., description="错误消息")
    node_id: Optional[str] = Field(None, description="相关节点 ID")
    edge_id: Optional[str] = Field(None, description="相关边 ID")
    suggestion: Optional[str] = Field(None, description="修复建议")


class ValidateResponse(BaseModel):
    """规则链校验响应"""
    valid: bool = Field(..., description="是否通过校验")
    errors: list[ValidateError] = Field(default_factory=list, description="错误列表")
    warnings: list[ValidateError] = Field(default_factory=list, description="警告列表")
    normalized_config: Optional[dict[str, Any]] = Field(None, description="标准化后的配置")
    stats: Optional[dict[str, Any]] = Field(None, description="校验统计信息")


# ============================================
# 规则链执行
# ============================================

class ExecuteRequest(BaseModel):
    """规则链执行请求"""
    chain_id: str = Field(..., description="规则链 ID")
    alert_data: dict[str, Any] = Field(..., description="告警数据")
    dry_run: bool = Field(default=False, description="是否为试运行（不执行 Action 节点）")


class ExecuteResponse(BaseModel):
    """规则链执行响应"""
    success: bool = Field(..., description="是否执行成功")
    execution_id: str = Field(..., description="执行 ID")
    chain_id: str = Field(..., description="规则链 ID")
    duration_ms: float = Field(..., description="执行耗时（毫秒）")
    result: dict[str, Any] = Field(..., description="执行结果")
    error: Optional[str] = Field(None, description="错误信息")


# ============================================
# 节点类型定义
# ============================================

class NodeTypeResponse(BaseModel):
    """节点类型定义响应"""
    name: str = Field(..., description="节点类型名称")
    label: str = Field(..., description="节点显示标签")
    description: str = Field(..., description="节点描述")
    category: str = Field(..., description="节点分类")
    icon: str = Field(..., description="节点图标")
    color: str = Field(..., description="节点颜色")
    inputs: list[dict[str, Any]] = Field(..., description="输入端口定义")
    outputs: list[dict[str, Any]] = Field(..., description="输出端口定义")
    config_schema: dict[str, Any] = Field(..., description="配置 JSON Schema")
    default_config: dict[str, Any] = Field(..., description="默认配置")
    input_schemas: list[dict[str, Any]] = Field(..., description="输入端口 Schema 列表")
    output_schemas: list[dict[str, Any]] = Field(..., description="输出端口 Schema 列表")


class NodeTypesResponse(BaseModel):
    """节点类型列表响应"""
    total: int = Field(..., description="节点类型总数")
    items: list[NodeTypeResponse] = Field(..., description="节点类型列表")
