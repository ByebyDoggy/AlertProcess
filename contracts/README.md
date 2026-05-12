# API 契约层 (Contracts)

## 概述

`contracts/` 目录定义了前后端之间的 API 契约，使用 Pydantic Models 实现类型安全的接口定义。

## 设计原则

1. **独立性**: 契约层独立于业务逻辑实现，只定义数据结构
2. **稳定性**: API 契约应保持向后兼容，变更需谨慎
3. **文档化**: 所有字段都有清晰的 `description`，便于自动生成文档
4. **类型安全**: 使用 Pydantic 提供运行时类型校验

## 目录结构

```
contracts/
├── __init__.py           # 统一导出所有契约
├── rule_chain.py         # 规则链相关契约
├── alert.py              # 告警相关契约
├── detector.py           # 检测器相关契约
├── execution.py          # 执行历史相关契约
└── README.md             # 本文档
```

## 使用方式

### 后端使用

```python
# 在 Router 中使用契约
from contracts.rule_chain import RuleChainCreateRequest, RuleChainResponse

@router.post("/", response_model=RuleChainResponse)
async def create_rule_chain(data: RuleChainCreateRequest):
    # 业务逻辑
    pass
```

### 前端使用

可以使用工具从 Pydantic Models 生成 TypeScript 类型定义：

```bash
# 使用 pydantic-to-typescript 或类似工具
pydantic-to-typescript --module contracts --output frontend/src/types/api.ts
```

生成的 TypeScript 类型：

```typescript
export interface RuleChainCreateRequest {
  name: string;
  description?: string;
  enabled?: boolean;
  nodes: RuleNode[];
  edges: RuleEdge[];
  sequence_phases?: any[];
}
```

## 契约模块说明

### rule_chain.py - 规则链契约

定义规则链的 CRUD、校验、执行等 API 契约。

**主要模型**:
- `RuleNode`: 规则链节点定义
- `RuleEdge`: 规则链边定义
- `RuleChainCreateRequest`: 创建规则链请求
- `RuleChainUpdateRequest`: 更新规则链请求
- `RuleChainResponse`: 规则链响应
- `ValidateRequest/Response`: 规则链校验
- `ExecuteRequest/Response`: 规则链执行
- `NodeTypeResponse`: 节点类型定义

### alert.py - 告警契约

定义告警提交、查询、统计等 API 契约。

**主要模型**:
- `AlertSubmitRequest`: 提交告警请求
- `AlertSubmitResponse`: 提交告警响应
- `AlertResponse`: 告警详情
- `AlertListRequest/Response`: 告警列表查询
- `AlertStatsResponse`: 告警统计

### detector.py - 检测器契约

定义检测器数据摄入、Trace 查询等 API 契约。

**主要模型**:
- `TraceIngestRequest/Response`: Trace 数据摄入
- `TraceQueryRequest/Response`: Trace 查询
- `DetectorExecuteRequest/Response`: 检测器执行

### execution.py - 执行历史契约

定义规则链执行历史、日志、监控等 API 契约。

**主要模型**:
- `ExecutionHistoryResponse`: 执行历史详情
- `ExecutionHistoryListRequest/Response`: 执行历史列表
- `ExecutionLogEntry/Response`: 执行日志
- `ExecutionStatsResponse`: 执行统计

## 契约变更流程

### 1. 向后兼容的变更（推荐）

- 添加新的可选字段
- 添加新的端点
- 扩展枚举类型

```python
# ✅ 向后兼容：添加可选字段
class RuleChainCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    tags: Optional[list[str]] = None  # 新增可选字段
```

### 2. 破坏性变更（需谨慎）

- 删除字段
- 修改字段类型
- 修改必填/可选属性

**处理方式**:
1. 使用 API 版本控制（如 `/v2/rule-chain/`）
2. 保留旧版本 API 一段时间
3. 提供迁移指南

```python
# ⚠️ 破坏性变更：需要版本控制
# v1: name 是可选的
class RuleChainCreateRequestV1(BaseModel):
    name: Optional[str] = None

# v2: name 变为必填
class RuleChainCreateRequestV2(BaseModel):
    name: str  # 现在是必填
```

## 最佳实践

### 1. 字段命名

- 使用 `snake_case` 命名（Python 风格）
- 使用 `alias` 支持前端的 `camelCase`

```python
class RuleEdge(BaseModel):
    source_port: str = Field(default="output", alias="sourcePort")
    target_port: str = Field(default="input", alias="targetPort")
    
    model_config = {"populate_by_name": True}  # 同时支持两种命名
```

### 2. 字段描述

- 所有字段都应有清晰的 `description`
- 描述应说明字段的用途和约束

```python
class RuleChainCreateRequest(BaseModel):
    name: str = Field(
        ..., 
        min_length=1, 
        max_length=200, 
        description="规则链名称，1-200 个字符"
    )
```

### 3. 默认值

- 为可选字段提供合理的默认值
- 使用 `Field(default_factory=...)` 处理可变默认值

```python
class RuleChainCreateRequest(BaseModel):
    enabled: bool = Field(default=True, description="是否启用")
    nodes: list[RuleNode] = Field(default_factory=list, description="节点列表")
```

### 4. 响应模型

- 使用 `model_config = {"from_attributes": True}` 支持从 ORM 模型转换

```python
class RuleChainResponse(BaseModel):
    id: str
    name: str
    created_at: datetime
    
    model_config = {"from_attributes": True}  # 支持从 SQLAlchemy 模型转换
```

## 自动化工具

### 生成 OpenAPI 文档

FastAPI 自动从契约生成 OpenAPI 文档：

```bash
# 启动服务后访问
http://localhost:8000/docs
```

### 生成 TypeScript 类型

```bash
# 安装工具
pip install pydantic-to-typescript

# 生成类型定义
pydantic-to-typescript \
  --module contracts \
  --output frontend/src/types/api.ts
```

### 契约测试

```python
# tests/contracts/test_rule_chain.py
from contracts.rule_chain import RuleChainCreateRequest

def test_rule_chain_create_request_validation():
    # 测试必填字段
    with pytest.raises(ValidationError):
        RuleChainCreateRequest(description="test")  # 缺少 name
    
    # 测试字段约束
    with pytest.raises(ValidationError):
        RuleChainCreateRequest(name="")  # name 不能为空
    
    # 测试正常情况
    request = RuleChainCreateRequest(name="Test Chain")
    assert request.name == "Test Chain"
    assert request.enabled is True  # 默认值
```

## 迁移指南

### 从内联模型迁移到契约层

**之前**:
```python
# routers/rule_chain/router.py
class RuleChainCreate(BaseModel):
    name: str
    description: Optional[str] = ""
```

**之后**:
```python
# contracts/rule_chain.py
class RuleChainCreateRequest(BaseModel):
    name: str = Field(..., description="规则链名称")
    description: Optional[str] = Field(default="", description="规则链描述")

# routers/rule_chain/router.py
from contracts.rule_chain import RuleChainCreateRequest as RuleChainCreate
```

## 参考资料

- [Pydantic 官方文档](https://docs.pydantic.dev/)
- [FastAPI 响应模型](https://fastapi.tiangolo.com/tutorial/response-model/)
- [API 设计最佳实践](https://github.com/microsoft/api-guidelines)
