"""
Repository 层 - 统一导出

Repository 模式将数据访问逻辑与业务逻辑分离。
"""

from backend.repositories.base import BaseRepository, ReadOnlyRepository
from backend.repositories.rule_chain import RuleChainRepository
from backend.repositories.alert import AlertRepository

__all__ = [
    "BaseRepository",
    "ReadOnlyRepository",
    "RuleChainRepository",
    "AlertRepository",
]
