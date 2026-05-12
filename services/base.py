"""
Service 层 - 业务逻辑抽象基类

Service 层封装业务逻辑，协调多个 Repository 完成复杂操作。
"""

from typing import Generic, TypeVar
from abc import ABC
from sqlalchemy.orm import Session

T = TypeVar('T')


class BaseService(ABC, Generic[T]):
    """
    Service 基类，提供通用的业务逻辑框架。

    Service 层职责：
    1. 封装业务逻辑
    2. 协调多个 Repository
    3. 处理事务边界
    4. 数据转换（DB Model <-> Contract Model）
    """

    def __init__(self, db: Session):
        """
        初始化 Service

        Args:
            db: SQLAlchemy Session 实例
        """
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
