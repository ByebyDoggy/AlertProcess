"""
Repository 层 - 告警数据访问

提供告警的数据库操作接口。
"""

from typing import Optional, List
from datetime import datetime

from sqlalchemy.orm import Session
from backend.database.models import AlertDB, SeverityEnum
from backend.repositories.base import BaseRepository


class AlertRepository(BaseRepository[AlertDB, str]):
    """告警 Repository"""

    def get_by_id(self, id: str) -> Optional[AlertDB]:
        """根据 ID 获取告警"""
        return self.db.query(AlertDB).filter(AlertDB.alert_id == id).first()

    def get_all(self, skip: int = 0, limit: int = 100) -> List[AlertDB]:
        """获取所有告警（分页，按时间倒序）"""
        return (
            self.db.query(AlertDB)
            .order_by(AlertDB.timestamp.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count(self, **filters) -> int:
        """统计告警数量"""
        query = self.db.query(AlertDB)

        # 应用过滤条件
        if "severity" in filters:
            query = query.filter(AlertDB.severity == filters["severity"])
        if "chain_id" in filters:
            query = query.filter(AlertDB.chain_id == filters["chain_id"])
        if "start_time" in filters:
            query = query.filter(AlertDB.timestamp >= filters["start_time"])
        if "end_time" in filters:
            query = query.filter(AlertDB.timestamp <= filters["end_time"])

        return query.count()

    def create(self, entity: AlertDB) -> AlertDB:
        """创建告警"""
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def update(self, id: str, updates: dict) -> Optional[AlertDB]:
        """更新告警"""
        alert = self.get_by_id(id)
        if not alert:
            return None

        # 应用更新
        for key, value in updates.items():
            if hasattr(alert, key):
                setattr(alert, key, value)

        self.db.commit()
        self.db.refresh(alert)
        return alert

    def delete(self, id: str) -> bool:
        """删除告警"""
        alert = self.get_by_id(id)
        if not alert:
            return False

        self.db.delete(alert)
        self.db.commit()
        return True

    def get_by_severity(
        self, severity: SeverityEnum, skip: int = 0, limit: int = 100
    ) -> List[AlertDB]:
        """根据严重等级获取告警"""
        return (
            self.db.query(AlertDB)
            .filter(AlertDB.severity == severity)
            .order_by(AlertDB.timestamp.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_by_chain_id(
        self, chain_id: int, skip: int = 0, limit: int = 100
    ) -> List[AlertDB]:
        """根据链 ID 获取告警"""
        return (
            self.db.query(AlertDB)
            .filter(AlertDB.chain_id == chain_id)
            .order_by(AlertDB.timestamp.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_by_time_range(
        self,
        start_time: datetime,
        end_time: datetime,
        skip: int = 0,
        limit: int = 100,
    ) -> List[AlertDB]:
        """根据时间范围获取告警"""
        return (
            self.db.query(AlertDB)
            .filter(AlertDB.timestamp >= start_time, AlertDB.timestamp <= end_time)
            .order_by(AlertDB.timestamp.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def search(
        self,
        severity: Optional[SeverityEnum] = None,
        chain_id: Optional[int] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[AlertDB]:
        """
        搜索告警

        Args:
            severity: 严重等级
            chain_id: 链 ID
            start_time: 开始时间
            end_time: 结束时间
            skip: 跳过记录数
            limit: 返回记录数

        Returns:
            符合条件的告警列表
        """
        query = self.db.query(AlertDB)

        # 应用过滤条件
        if severity is not None:
            query = query.filter(AlertDB.severity == severity)
        if chain_id is not None:
            query = query.filter(AlertDB.chain_id == chain_id)
        if start_time is not None:
            query = query.filter(AlertDB.timestamp >= start_time)
        if end_time is not None:
            query = query.filter(AlertDB.timestamp <= end_time)

        return query.order_by(AlertDB.timestamp.desc()).offset(skip).limit(limit).all()

    def get_stats(self) -> dict:
        """
        获取告警统计信息

        Returns:
            统计信息字典
        """
        from sqlalchemy import func
        from datetime import timedelta

        total = self.db.query(AlertDB).count()

        # 按严重等级统计
        by_severity = {}
        severity_stats = (
            self.db.query(AlertDB.severity, func.count(AlertDB.alert_id))
            .group_by(AlertDB.severity)
            .all()
        )
        for severity, count in severity_stats:
            by_severity[severity.value if severity else "UNKNOWN"] = count

        # 按链统计
        by_chain = {}
        chain_stats = (
            self.db.query(AlertDB.chain_id, func.count(AlertDB.alert_id))
            .group_by(AlertDB.chain_id)
            .all()
        )
        for chain_id, count in chain_stats:
            by_chain[str(chain_id)] = count

        # 最近 24 小时
        now = datetime.now()
        recent_24h = (
            self.db.query(AlertDB)
            .filter(AlertDB.timestamp >= now - timedelta(hours=24))
            .count()
        )

        # 最近 7 天
        recent_7d = (
            self.db.query(AlertDB)
            .filter(AlertDB.timestamp >= now - timedelta(days=7))
            .count()
        )

        return {
            "total": total,
            "by_severity": by_severity,
            "by_chain": by_chain,
            "recent_24h": recent_24h,
            "recent_7d": recent_7d,
        }
