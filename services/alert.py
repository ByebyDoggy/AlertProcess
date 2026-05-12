"""
Service 层 - 告警业务逻辑

封装告警的业务逻辑，包括提交、查询、统计等。
"""

from typing import Optional, List
import uuid
from datetime import datetime

from sqlalchemy.orm import Session
from fastapi import HTTPException

from services.base import BaseService
from repositories import AlertRepository
from contracts.alert import (
    AlertSubmitRequest,
    AlertSubmitResponse,
    AlertResponse,
    AlertListRequest,
    AlertListResponse,
    AlertStatsResponse,
    SeverityLevel,
)
from database.models import AlertDB, SeverityEnum


class AlertService(BaseService[AlertDB]):
    """告警业务逻辑服务"""

    def __init__(self, db: Session):
        super().__init__(db)
        self.repo = AlertRepository(db)

    def submit_alert(self, request: AlertSubmitRequest) -> AlertSubmitResponse:
        """
        提交告警

        Args:
            request: 提交请求

        Returns:
            提交响应
        """
        alert_id = str(uuid.uuid4())

        # 创建告警实体
        db_alert = AlertDB(
            alert_id=alert_id,
            attacked_address=request.attacked_address,
            exploiter_address=request.exploiter_address,
            severity=SeverityEnum.UNKNOWN,
            message=f"Alert for tx {request.tx_hash} on chain {request.chain_id}",
            timestamp=datetime.now(),
            risk_score="PENDING",
        )

        # 保存到数据库
        self.repo.create(db_alert)

        return AlertSubmitResponse(status="success", alert_id=alert_id)

    def get_alert(self, alert_id: str) -> AlertResponse:
        """
        获取告警详情

        Args:
            alert_id: 告警 ID

        Returns:
            告警详情

        Raises:
            HTTPException: 告警不存在
        """
        alert = self.repo.get_by_id(alert_id)
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")

        return self._to_response(alert)

    def list_alerts(self, request: AlertListRequest) -> AlertListResponse:
        """
        获取告警列表

        Args:
            request: 查询请求

        Returns:
            告警列表
        """
        # 转换 severity 字符串为枚举
        severity_enum = None
        if request.severity:
            try:
                severity_enum = SeverityEnum(request.severity)
            except ValueError:
                pass

        # 查询告警
        alerts = self.repo.search(
            severity=severity_enum,
            chain_id=request.chain_id,
            start_time=request.start_time,
            end_time=request.end_time,
            skip=request.skip,
            limit=request.limit,
        )

        # 统计总数
        total = self.repo.count(
            severity=severity_enum,
            chain_id=request.chain_id,
            start_time=request.start_time,
            end_time=request.end_time,
        )

        # 转换为响应模型
        alert_responses = [self._to_response(alert) for alert in alerts]

        return AlertListResponse(
            total=total,
            alerts=alert_responses,
            skip=request.skip,
            limit=request.limit,
        )

    def get_stats(self) -> AlertStatsResponse:
        """
        获取告警统计信息

        Returns:
            统计信息
        """
        stats = self.repo.get_stats()

        return AlertStatsResponse(
            total=stats["total"],
            by_severity=stats["by_severity"],
            by_chain=stats["by_chain"],
            recent_24h=stats["recent_24h"],
            recent_7d=stats["recent_7d"],
        )

    def update_alert_severity(
        self, alert_id: str, severity: SeverityLevel, risk_score: Optional[str] = None
    ) -> AlertResponse:
        """
        更新告警严重等级

        Args:
            alert_id: 告警 ID
            severity: 新的严重等级
            risk_score: 风险评分

        Returns:
            更新后的告警

        Raises:
            HTTPException: 告警不存在
        """
        updates = {"severity": SeverityEnum(severity)}
        if risk_score is not None:
            updates["risk_score"] = risk_score

        alert = self.repo.update(alert_id, updates)
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")

        return self._to_response(alert)

    def delete_alert(self, alert_id: str) -> dict:
        """
        删除告警

        Args:
            alert_id: 告警 ID

        Returns:
            删除结果

        Raises:
            HTTPException: 告警不存在
        """
        success = self.repo.delete(alert_id)
        if not success:
            raise HTTPException(status_code=404, detail="Alert not found")

        return {"status": "success", "message": "Alert deleted"}

    def _to_response(self, alert: AlertDB) -> AlertResponse:
        """将数据库模型转换为响应模型"""
        return AlertResponse(
            alert_id=alert.alert_id,
            attacked_address=alert.attacked_address,
            exploiter_address=alert.exploiter_address,
            severity=alert.severity.value if alert.severity else "UNKNOWN",
            message=alert.message,
            timestamp=alert.timestamp,
            risk_score=alert.risk_score,
        )
