"""
Repository 层 - 数据访问抽象基类

Repository 模式将数据访问逻辑与业务逻辑分离，提供统一的数据操作接口。
"""

from typing import Generic, TypeVar, Optional, List, Any
from abc import ABC, abstractmethod
from sqlalchemy.orm import Session

# 泛型类型变量
T = TypeVar('T')  # 数据库模型类型
ID = TypeVar('ID')  # ID 类型（通常是 str 或 int）


class BaseRepository(ABC, Generic[T, ID]):
    """
    Repository 基类，定义通用的 CRUD 操作接口。

    所有具体的 Repository 都应继承此类并实现抽象方法。
    """

    def __init__(self, db: Session):
        """
        初始化 Repository

        Args:
            db: SQLAlchemy Session 实例
        """
        self.db = db

    @abstractmethod
    def get_by_id(self, id: ID) -> Optional[T]:
        """
        根据 ID 获取单条记录

        Args:
            id: 记录 ID

        Returns:
            找到的记录，如果不存在则返回 None
        """
        pass

    @abstractmethod
    def get_all(self, skip: int = 0, limit: int = 100) -> List[T]:
        """
        获取所有记录（分页）

        Args:
            skip: 跳过的记录数
            limit: 返回的最大记录数

        Returns:
            记录列表
        """
        pass

    @abstractmethod
    def count(self, **filters) -> int:
        """
        统计记录数

        Args:
            **filters: 过滤条件

        Returns:
            符合条件的记录数
        """
        pass

    @abstractmethod
    def create(self, entity: T) -> T:
        """
        创建新记录

        Args:
            entity: 要创建的实体对象

        Returns:
            创建后的实体对象（包含生成的 ID 等）
        """
        pass

    @abstractmethod
    def update(self, id: ID, updates: dict[str, Any]) -> Optional[T]:
        """
        更新记录

        Args:
            id: 记录 ID
            updates: 要更新的字段字典

        Returns:
            更新后的实体对象，如果不存在则返回 None
        """
        pass

    @abstractmethod
    def delete(self, id: ID) -> bool:
        """
        删除记录

        Args:
            id: 记录 ID

        Returns:
            是否删除成功
        """
        pass

    def commit(self):
        """提交事务"""
        self.db.commit()

    def rollback(self):
        """回滚事务"""
        self.db.rollback()

    def refresh(self, entity: T) -> T:
        """
        刷新实体对象（从数据库重新加载）

        Args:
            entity: 要刷新的实体对象

        Returns:
            刷新后的实体对象
        """
        self.db.refresh(entity)
        return entity


class ReadOnlyRepository(ABC, Generic[T, ID]):
    """
    只读 Repository 基类，只提供查询操作。

    适用于只需要读取数据的场景，如统计、报表等。
    """

    def __init__(self, db: Session):
        self.db = db

    @abstractmethod
    def get_by_id(self, id: ID) -> Optional[T]:
        """根据 ID 获取单条记录"""
        pass

    @abstractmethod
    def get_all(self, skip: int = 0, limit: int = 100) -> List[T]:
        """获取所有记录（分页）"""
        pass

    @abstractmethod
    def count(self, **filters) -> int:
        """统计记录数"""
        pass
