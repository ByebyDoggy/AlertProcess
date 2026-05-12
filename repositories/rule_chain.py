"""
Repository 层 - 规则链数据访问

提供规则链的数据库操作接口。
"""

from typing import Optional, List
from datetime import datetime
import json

from sqlalchemy.orm import Session
from database.models import RuleChainDB
from repositories.base import BaseRepository


class RuleChainRepository(BaseRepository[RuleChainDB, str]):
    """规则链 Repository"""

    def get_by_id(self, id: str) -> Optional[RuleChainDB]:
        """根据 ID 获取规则链"""
        return self.db.query(RuleChainDB).filter(RuleChainDB.id == id).first()

    def get_all(self, skip: int = 0, limit: int = 100) -> List[RuleChainDB]:
        """获取所有规则链（分页，按更新时间倒序）"""
        return (
            self.db.query(RuleChainDB)
            .order_by(RuleChainDB.updated_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count(self, **filters) -> int:
        """统计规则链数量"""
        query = self.db.query(RuleChainDB)

        # 应用过滤条件
        if "enabled" in filters:
            query = query.filter(RuleChainDB.enabled == (1 if filters["enabled"] else 0))

        return query.count()

    def create(self, entity: RuleChainDB) -> RuleChainDB:
        """创建规则链"""
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def update(self, id: str, updates: dict) -> Optional[RuleChainDB]:
        """更新规则链"""
        chain = self.get_by_id(id)
        if not chain:
            return None

        # 应用更新
        for key, value in updates.items():
            if hasattr(chain, key):
                setattr(chain, key, value)

        # 更新时间戳
        chain.updated_at = datetime.now()

        self.db.commit()
        self.db.refresh(chain)
        return chain

    def delete(self, id: str) -> bool:
        """删除规则链"""
        chain = self.get_by_id(id)
        if not chain:
            return False

        self.db.delete(chain)
        self.db.commit()
        return True

    def get_by_name(self, name: str) -> Optional[RuleChainDB]:
        """根据名称获取规则链"""
        return self.db.query(RuleChainDB).filter(RuleChainDB.name == name).first()

    def get_enabled(self, skip: int = 0, limit: int = 100) -> List[RuleChainDB]:
        """获取所有启用的规则链"""
        return (
            self.db.query(RuleChainDB)
            .filter(RuleChainDB.enabled == 1)
            .order_by(RuleChainDB.updated_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def toggle_enabled(self, id: str, enabled: bool) -> Optional[RuleChainDB]:
        """切换规则链启用状态"""
        return self.update(id, {"enabled": 1 if enabled else 0})

    def update_config(self, id: str, chain_config: dict) -> Optional[RuleChainDB]:
        """更新规则链配置"""
        return self.update(id, {"chain_config": json.dumps(chain_config)})

    def search(
        self,
        keyword: Optional[str] = None,
        enabled: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[RuleChainDB]:
        """
        搜索规则链

        Args:
            keyword: 关键词（匹配名称或描述）
            enabled: 是否启用
            skip: 跳过记录数
            limit: 返回记录数

        Returns:
            符合条件的规则链列表
        """
        query = self.db.query(RuleChainDB)

        # 关键词搜索
        if keyword:
            search_pattern = f"%{keyword}%"
            query = query.filter(
                (RuleChainDB.name.like(search_pattern))
                | (RuleChainDB.description.like(search_pattern))
            )

        # 启用状态过滤
        if enabled is not None:
            query = query.filter(RuleChainDB.enabled == (1 if enabled else 0))

        return query.order_by(RuleChainDB.updated_at.desc()).offset(skip).limit(limit).all()
