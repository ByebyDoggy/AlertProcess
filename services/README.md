# Service 层

## 概述

Service 层封装业务逻辑，协调多个 Repository 完成复杂操作，是连接 Router 和 Repository 的桥梁。

## 设计原则

1. **业务逻辑封装**: 将复杂的业务逻辑从 Router 中分离
2. **事务管理**: 负责管理跨多个 Repository 的事务
3. **数据转换**: 负责 DB Model 和 Contract Model 之间的转换
4. **错误处理**: 统一的业务异常处理

## 目录结构

```
services/
├── __init__.py           # 统一导出
├── base.py               # Service 基类
├── rule_chain.py         # 规则链 Service
├── alert.py              # 告警 Service
└── README.md             # 本文档
```

## 架构层次

```
Router (HTTP 层)
    ↓ 使用
Service (业务逻辑层)
    ↓ 使用
Repository (数据访问层)
    ↓
Database
```

## 使用方式

### 基本用法

```python
from database.models import SessionLocal
from services import RuleChainService

# 创建数据库会话
db = SessionLocal()

try:
    # 创建 Service 实例
    service = RuleChainService(db)
    
    # 调用业务方法
    chain = service.get_chain("chain-id-123")
    chains = service.list_chains(skip=0, limit=10)
    
    # Service 内部会调用 Repository
    # 并处理数据转换和业务逻辑
    
finally:
    db.close()
```

### 在 Router 中使用

```python
# routers/rule_chain/router.py
from fastapi import APIRouter, Depends
from services import RuleChainService
from contracts.rule_chain import RuleChainResponse

@router.get("/{chain_id}", response_model=RuleChainResponse)
async def get_rule_chain(
    chain_id: str,
    service: RuleChainService = Depends(get_rule_chain_service)
):
    # Router 只负责 HTTP 处理
    # 业务逻辑委托给 Service
    return service.get_chain(chain_id)
```

### 依赖注入

```python
# dependencies.py
from database.models import SessionLocal
from services import RuleChainService

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_rule_chain_service(db: Session = Depends(get_db)):
    return RuleChainService(db)
```

## Service 实现

### BaseService

所有 Service 的基类：

```python
class BaseService(ABC, Generic[T]):
    def __init__(self, db: Session):
        self.db = db
    
    def commit(self):
        """提交事务"""
        self.db.commit()
    
    def rollback(self):
        """回滚事务"""
        self.db.rollback()
    
    def close(self):
        """关闭数据库会话"""
        self.db.close()
```

### RuleChainService

规则链业务逻辑：

```python
class RuleChainService(BaseService[RuleChainDB]):
    def __init__(self, db: Session):
        super().__init__(db)
        self.repo = RuleChainRepository(db)
    
    # CRUD 操作
    def get_chain(self, chain_id: str) -> RuleChainResponse
    def list_chains(self, skip: int, limit: int) -> List[RuleChainResponse]
    def create_chain(self, request: RuleChainCreateRequest) -> RuleChainResponse
    def update_chain(self, chain_id: str, request: RuleChainUpdateRequest) -> RuleChainResponse
    def delete_chain(self, chain_id: str) -> dict
    
    # 业务操作
    def validate_chain(self, request: ValidateRequest) -> ValidateResponse
    def execute_chain(self, request: ExecuteRequest) -> ExecuteResponse
    def search_chains(self, keyword: str, enabled: bool, ...) -> List[RuleChainResponse]
    def toggle_enabled(self, chain_id: str, enabled: bool) -> RuleChainResponse
    
    # 内部方法
    def _to_response(self, chain: RuleChainDB) -> RuleChainResponse
    def _to_validate_error(self, error) -> ValidateError
```

### AlertService

告警业务逻辑：

```python
class AlertService(BaseService[AlertDB]):
    def __init__(self, db: Session):
        super().__init__(db)
        self.repo = AlertRepository(db)
    
    # CRUD 操作
    def submit_alert(self, request: AlertSubmitRequest) -> AlertSubmitResponse
    def get_alert(self, alert_id: str) -> AlertResponse
    def list_alerts(self, request: AlertListRequest) -> AlertListResponse
    def delete_alert(self, alert_id: str) -> dict
    
    # 业务操作
    def get_stats(self) -> AlertStatsResponse
    def update_alert_severity(self, alert_id: str, severity: SeverityLevel, ...) -> AlertResponse
    
    # 内部方法
    def _to_response(self, alert: AlertDB) -> AlertResponse
```

## 职责划分

### Router 层职责
- HTTP 请求/响应处理
- 参数校验（通过 Pydantic）
- 认证和授权
- 调用 Service 层

### Service 层职责
- 业务逻辑封装
- 数据转换（DB Model ↔ Contract Model）
- 事务管理
- 协调多个 Repository
- 业务异常处理

### Repository 层职责
- 数据库 CRUD 操作
- 查询构建
- 数据持久化

## 最佳实践

### 1. 数据转换

Service 负责 DB Model 和 Contract Model 之间的转换：

```python
# ✅ 正确：在 Service 中转换
class RuleChainService:
    def get_chain(self, chain_id: str) -> RuleChainResponse:
        # Repository 返回 DB Model
        chain = self.repo.get_by_id(chain_id)
        
        # Service 转换为 Contract Model
        return self._to_response(chain)
    
    def _to_response(self, chain: RuleChainDB) -> RuleChainResponse:
        return RuleChainResponse(
            id=chain.id,
            name=chain.name,
            # ... 其他字段
        )
```

### 2. 事务管理

Service 负责管理事务边界：

```python
# ✅ 正确：Service 管理事务
class RuleChainService:
    def create_chain_with_validation(self, request: RuleChainCreateRequest):
        try:
            # 1. 校验
            validation = self.validate_chain(ValidateRequest(
                nodes=request.nodes,
                edges=request.edges
            ))
            
            if not validation.valid:
                raise ValidationError(validation.errors)
            
            # 2. 创建
            chain = self.create_chain(request)
            
            # 3. 提交事务
            self.commit()
            
            return chain
        except Exception:
            # 回滚事务
            self.rollback()
            raise
```

### 3. 错误处理

Service 抛出业务异常，Router 处理 HTTP 异常：

```python
# ✅ 正确：Service 抛出 HTTPException
class RuleChainService:
    def get_chain(self, chain_id: str) -> RuleChainResponse:
        chain = self.repo.get_by_id(chain_id)
        if not chain:
            raise HTTPException(status_code=404, detail="Rule chain not found")
        return self._to_response(chain)

# Router 直接传递异常
@router.get("/{chain_id}")
async def get_rule_chain(chain_id: str, service: RuleChainService = Depends(...)):
    return service.get_chain(chain_id)  # HTTPException 会被 FastAPI 自动处理
```

### 4. 复杂业务逻辑

将复杂的业务逻辑封装在 Service 中：

```python
# ✅ 正确：复杂逻辑在 Service 中
class RuleChainService:
    def execute_chain_with_retry(
        self, 
        chain_id: str, 
        alert_data: dict, 
        max_retries: int = 3
    ) -> ExecuteResponse:
        """执行规则链，失败时重试"""
        last_error = None
        
        for attempt in range(max_retries):
            try:
                return self.execute_chain(ExecuteRequest(
                    chain_id=chain_id,
                    alert_data=alert_data,
                    dry_run=False
                ))
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # 指数退避
        
        raise HTTPException(
            status_code=500,
            detail=f"Chain execution failed after {max_retries} attempts: {last_error}"
        )
```

### 5. 协调多个 Repository

Service 可以协调多个 Repository 完成复杂操作：

```python
class RuleChainService:
    def __init__(self, db: Session):
        super().__init__(db)
        self.chain_repo = RuleChainRepository(db)
        self.alert_repo = AlertRepository(db)
    
    def execute_and_create_alert(self, chain_id: str, alert_data: dict):
        """执行规则链并创建告警"""
        try:
            # 1. 执行规则链
            result = self.execute_chain(ExecuteRequest(
                chain_id=chain_id,
                alert_data=alert_data
            ))
            
            # 2. 如果检测到攻击，创建告警
            if result.result.get("final_severity") in ["CRITICAL", "HIGH"]:
                alert = AlertDB(
                    alert_id=str(uuid.uuid4()),
                    severity=SeverityEnum(result.result["final_severity"]),
                    message=f"Attack detected by chain {chain_id}",
                    # ... 其他字段
                )
                self.alert_repo.create(alert)
            
            # 3. 提交事务
            self.commit()
            
            return result
        except Exception:
            self.rollback()
            raise
```

## 测试

### 单元测试

Mock Repository 测试 Service：

```python
# tests/services/test_rule_chain.py
from unittest.mock import Mock
from services import RuleChainService
from database.models import RuleChainDB

def test_get_chain():
    # Mock Repository
    mock_repo = Mock()
    mock_repo.get_by_id.return_value = RuleChainDB(
        id="test-chain",
        name="Test Chain",
        chain_config='{"nodes": [], "edges": []}',
    )
    
    # 创建 Service（注入 Mock Repository）
    service = RuleChainService(Mock())
    service.repo = mock_repo
    
    # 测试
    response = service.get_chain("test-chain")
    
    assert response.id == "test-chain"
    assert response.name == "Test Chain"
    mock_repo.get_by_id.assert_called_once_with("test-chain")

def test_get_chain_not_found():
    # Mock Repository 返回 None
    mock_repo = Mock()
    mock_repo.get_by_id.return_value = None
    
    service = RuleChainService(Mock())
    service.repo = mock_repo
    
    # 测试异常
    with pytest.raises(HTTPException) as exc_info:
        service.get_chain("non-existent")
    
    assert exc_info.value.status_code == 404
```

### 集成测试

使用真实数据库测试 Service：

```python
# tests/services/test_rule_chain_integration.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.models import Base
from services import RuleChainService
from contracts.rule_chain import RuleChainCreateRequest

@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_create_and_get_chain(db):
    service = RuleChainService(db)
    
    # 创建
    request = RuleChainCreateRequest(
        name="Test Chain",
        nodes=[],
        edges=[]
    )
    created = service.create_chain(request)
    
    # 查询
    found = service.get_chain(created.id)
    
    assert found.id == created.id
    assert found.name == "Test Chain"
```

## 扩展 Service

### 添加新的 Service

```python
# services/detector.py
from services.base import BaseService
from repositories import DetectorRepository

class DetectorService(BaseService):
    def __init__(self, db: Session):
        super().__init__(db)
        self.repo = DetectorRepository(db)
    
    def ingest_trace(self, request: TraceIngestRequest) -> TraceIngestResponse:
        # 业务逻辑
        pass
    
    def execute_detector(self, request: DetectorExecuteRequest) -> DetectorExecuteResponse:
        # 业务逻辑
        pass
```

## 参考资料

- [Service Layer Pattern](https://martinfowler.com/eaaCatalog/serviceLayer.html)
- [FastAPI Dependency Injection](https://fastapi.tiangolo.com/tutorial/dependencies/)
- [Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
