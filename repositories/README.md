# Repository 层

## 概述

Repository 层实现了数据访问逻辑的抽象，将数据库操作与业务逻辑分离。

## 设计原则

1. **单一职责**: 每个 Repository 只负责一个实体的数据访问
2. **接口抽象**: 通过基类定义统一的 CRUD 接口
3. **可测试性**: Repository 可以被 Mock，便于单元测试
4. **数据库无关**: 业务逻辑不直接依赖 SQLAlchemy，便于切换数据库

## 目录结构

```
repositories/
├── __init__.py           # 统一导出
├── base.py               # Repository 基类
├── rule_chain.py         # 规则链 Repository
├── alert.py              # 告警 Repository
└── README.md             # 本文档
```

## 使用方式

### 基本用法

```python
from database.models import SessionLocal
from repositories import RuleChainRepository

# 创建数据库会话
db = SessionLocal()

try:
    # 创建 Repository 实例
    repo = RuleChainRepository(db)
    
    # 查询
    chain = repo.get_by_id("chain-id-123")
    all_chains = repo.get_all(skip=0, limit=10)
    
    # 创建
    new_chain = RuleChainDB(
        id="new-chain-id",
        name="New Chain",
        chain_config=json.dumps({"nodes": [], "edges": []}),
    )
    created = repo.create(new_chain)
    
    # 更新
    updated = repo.update("chain-id-123", {"name": "Updated Name"})
    
    # 删除
    success = repo.delete("chain-id-123")
    
finally:
    db.close()
```

### 在 Service 层使用

```python
# services/rule_chain.py
from repositories import RuleChainRepository

class RuleChainService:
    def __init__(self, db: Session):
        self.repo = RuleChainRepository(db)
    
    def get_chain(self, chain_id: str):
        chain = self.repo.get_by_id(chain_id)
        if not chain:
            raise ChainNotFoundError(chain_id)
        return chain
```

### 在 Router 层使用

```python
# routers/rule_chain/router.py
from repositories import RuleChainRepository

@router.get("/{chain_id}")
async def get_rule_chain(chain_id: str):
    db = SessionLocal()
    try:
        repo = RuleChainRepository(db)
        chain = repo.get_by_id(chain_id)
        if not chain:
            raise HTTPException(status_code=404)
        return chain
    finally:
        db.close()
```

## Repository 实现

### BaseRepository

所有 Repository 的基类，定义了通用的 CRUD 接口：

```python
class BaseRepository(ABC, Generic[T, ID]):
    def get_by_id(self, id: ID) -> Optional[T]
    def get_all(self, skip: int = 0, limit: int = 100) -> List[T]
    def count(self, **filters) -> int
    def create(self, entity: T) -> T
    def update(self, id: ID, updates: dict) -> Optional[T]
    def delete(self, id: ID) -> bool
```

### RuleChainRepository

规则链数据访问，提供额外的业务方法：

```python
class RuleChainRepository(BaseRepository[RuleChainDB, str]):
    # 基础 CRUD（继承自 BaseRepository）
    def get_by_id(self, id: str) -> Optional[RuleChainDB]
    def get_all(self, skip: int = 0, limit: int = 100) -> List[RuleChainDB]
    def create(self, entity: RuleChainDB) -> RuleChainDB
    def update(self, id: str, updates: dict) -> Optional[RuleChainDB]
    def delete(self, id: str) -> bool
    
    # 业务方法
    def get_by_name(self, name: str) -> Optional[RuleChainDB]
    def get_enabled(self, skip: int = 0, limit: int = 100) -> List[RuleChainDB]
    def toggle_enabled(self, id: str, enabled: bool) -> Optional[RuleChainDB]
    def update_config(self, id: str, chain_config: dict) -> Optional[RuleChainDB]
    def search(self, keyword: str, enabled: bool, ...) -> List[RuleChainDB]
```

### AlertRepository

告警数据访问，提供统计和查询方法：

```python
class AlertRepository(BaseRepository[AlertDB, str]):
    # 基础 CRUD
    def get_by_id(self, id: str) -> Optional[AlertDB]
    def get_all(self, skip: int = 0, limit: int = 100) -> List[AlertDB]
    def create(self, entity: AlertDB) -> AlertDB
    def update(self, id: str, updates: dict) -> Optional[AlertDB]
    def delete(self, id: str) -> bool
    
    # 业务方法
    def get_by_severity(self, severity: SeverityEnum, ...) -> List[AlertDB]
    def get_by_chain_id(self, chain_id: int, ...) -> List[AlertDB]
    def get_by_time_range(self, start_time, end_time, ...) -> List[AlertDB]
    def search(self, severity, chain_id, start_time, end_time, ...) -> List[AlertDB]
    def get_stats(self) -> dict
```

## 最佳实践

### 1. 事务管理

Repository 不负责事务管理，由调用方（Service 或 Router）控制：

```python
# ✅ 正确：调用方管理事务
db = SessionLocal()
try:
    repo = RuleChainRepository(db)
    chain = repo.create(new_chain)
    # 其他操作...
    db.commit()  # 调用方提交事务
except Exception:
    db.rollback()  # 调用方回滚
    raise
finally:
    db.close()
```

```python
# ❌ 错误：Repository 内部提交事务（已在实现中处理）
# 注意：当前实现中 create/update/delete 会自动 commit
# 这是为了简化使用，但在复杂事务场景下可能需要调整
```

### 2. 查询优化

使用 Repository 的专用方法而不是通用查询：

```python
# ✅ 正确：使用专用方法
enabled_chains = repo.get_enabled(skip=0, limit=10)

# ❌ 避免：在业务层构造查询
chains = repo.get_all()
enabled_chains = [c for c in chains if c.enabled]
```

### 3. 返回值处理

Repository 返回 None 表示未找到，调用方负责错误处理：

```python
# ✅ 正确：调用方检查返回值
chain = repo.get_by_id(chain_id)
if not chain:
    raise HTTPException(status_code=404, detail="Chain not found")
return chain

# ❌ 错误：Repository 抛出异常
# Repository 应该返回 None，不应该抛出业务异常
```

### 4. 复杂查询

对于复杂查询，在 Repository 中添加专用方法：

```python
# ✅ 正确：在 Repository 中实现
class AlertRepository(BaseRepository):
    def get_critical_alerts_last_24h(self) -> List[AlertDB]:
        now = datetime.now()
        return (
            self.db.query(AlertDB)
            .filter(
                AlertDB.severity == SeverityEnum.CRITICAL,
                AlertDB.timestamp >= now - timedelta(hours=24)
            )
            .all()
        )

# ❌ 避免：在 Service 层直接操作 db.query()
```

### 5. 分页和排序

统一使用 skip/limit 进行分页：

```python
# ✅ 正确：标准分页
chains = repo.get_all(skip=0, limit=10)  # 第 1 页
chains = repo.get_all(skip=10, limit=10)  # 第 2 页

# 计算总页数
total = repo.count()
total_pages = (total + limit - 1) // limit
```

## 测试

### 单元测试

使用内存数据库测试 Repository：

```python
# tests/repositories/test_rule_chain.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.models import Base, RuleChainDB
from repositories import RuleChainRepository

@pytest.fixture
def db():
    # 创建内存数据库
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_create_rule_chain(db):
    repo = RuleChainRepository(db)
    
    chain = RuleChainDB(
        id="test-chain",
        name="Test Chain",
        chain_config='{"nodes": [], "edges": []}',
    )
    
    created = repo.create(chain)
    assert created.id == "test-chain"
    assert created.name == "Test Chain"

def test_get_by_id(db):
    repo = RuleChainRepository(db)
    
    # 创建测试数据
    chain = RuleChainDB(id="test-chain", name="Test")
    repo.create(chain)
    
    # 查询
    found = repo.get_by_id("test-chain")
    assert found is not None
    assert found.name == "Test"
    
    # 查询不存在的
    not_found = repo.get_by_id("non-existent")
    assert not_found is None
```

### Mock Repository

在 Service 层测试中 Mock Repository：

```python
# tests/services/test_rule_chain.py
from unittest.mock import Mock
from services import RuleChainService

def test_get_chain_not_found():
    # Mock Repository
    mock_repo = Mock()
    mock_repo.get_by_id.return_value = None
    
    # 测试 Service
    service = RuleChainService(mock_repo)
    
    with pytest.raises(ChainNotFoundError):
        service.get_chain("non-existent")
```

## 扩展 Repository

### 添加新的 Repository

1. 继承 `BaseRepository`
2. 实现抽象方法
3. 添加业务特定方法

```python
# repositories/knowledge_base.py
from repositories.base import BaseRepository
from database.models import KnowledgeBaseDB

class KnowledgeBaseRepository(BaseRepository[KnowledgeBaseDB, str]):
    def get_by_id(self, id: str) -> Optional[KnowledgeBaseDB]:
        return self.db.query(KnowledgeBaseDB).filter(
            KnowledgeBaseDB.id == id
        ).first()
    
    # ... 实现其他抽象方法
    
    # 业务方法
    def get_by_attack_type(self, attack_type: str) -> List[KnowledgeBaseDB]:
        return self.db.query(KnowledgeBaseDB).filter(
            KnowledgeBaseDB.attack_type == attack_type
        ).all()
```

### 只读 Repository

对于只需要查询的场景，使用 `ReadOnlyRepository`：

```python
from repositories.base import ReadOnlyRepository

class AlertStatsRepository(ReadOnlyRepository[AlertDB, str]):
    def get_by_id(self, id: str) -> Optional[AlertDB]:
        return self.db.query(AlertDB).filter(AlertDB.alert_id == id).first()
    
    def get_all(self, skip: int = 0, limit: int = 100) -> List[AlertDB]:
        return self.db.query(AlertDB).offset(skip).limit(limit).all()
    
    def count(self, **filters) -> int:
        return self.db.query(AlertDB).count()
    
    # 只读的统计方法
    def get_daily_stats(self, days: int = 7) -> dict:
        # 实现统计逻辑
        pass
```

## 参考资料

- [Repository Pattern](https://martinfowler.com/eaaCatalog/repository.html)
- [SQLAlchemy ORM Tutorial](https://docs.sqlalchemy.org/en/20/orm/tutorial.html)
- [Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
