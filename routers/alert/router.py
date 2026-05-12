"""告警路由 — 告警接收、查询、统计"""
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from database.models import SessionLocal, AlertDB, SeverityEnum
from contracts.alert import (
    AlertSubmitRequest,
    AlertSubmitResponse,
    AlertResponse,
    AlertListResponse,
)

alertRouter = APIRouter(
    prefix="/alert",
    tags=["alert"]
)


def _auth(api_key: Optional[str] = None):
    from config import settings
    if not api_key or api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


def _auth_with_key(x_api_key: Optional[str] = None, api_key: Optional[str] = None):
    from config import settings
    key = x_api_key if x_api_key else api_key
    if not key or key != settings.api_key:
        raise HTTPException(status_code=401, detail="API key is required")


@alertRouter.post("/submit", response_model=AlertSubmitResponse)
async def submit_alert(
    data: AlertSubmitRequest,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,
):
    _auth_with_key(x_api_key, api_key)
    alert_id = str(uuid.uuid4())

    db = SessionLocal()
    try:
        db_alert = AlertDB(
            alert_id=alert_id,
            attacked_address=data.attacked_address,
            exploiter_address=data.exploiter_address,
            severity=SeverityEnum.UNKNOWN,
            message=f"Alert for tx {data.tx_hash} on chain {data.chain_id}",
            timestamp=datetime.now(),
            risk_score="PENDING",
        )
        db.add(db_alert)
        db.commit()
        return AlertSubmitResponse(status="success", alert_id=alert_id)
    finally:
        db.close()


@alertRouter.get("/alerts", response_model=AlertListResponse)
async def list_alerts(
    skip: int = 0,
    limit: int = 100,
    severity: Optional[str] = None,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,
):
    _auth_with_key(x_api_key, api_key)

    db = SessionLocal()
    try:
        query = db.query(AlertDB)
        if severity:
            try:
                query = query.filter(AlertDB.severity == SeverityEnum(severity))
            except ValueError:
                pass

        total = query.count()
        alerts = query.order_by(AlertDB.timestamp.desc()).offset(skip).limit(limit).all()

        alert_responses = [
            AlertResponse(
                alert_id=a.alert_id,
                attacked_address=a.attacked_address,
                exploiter_address=a.exploiter_address,
                severity=a.severity.value if a.severity else "UNKNOWN",
                message=a.message,
                timestamp=a.timestamp,
                risk_score=a.risk_score,
            )
            for a in alerts
        ]

        return AlertListResponse(
            total=total,
            alerts=alert_responses,
            skip=skip,
            limit=limit,
        )
            "limit": limit,
        }
    finally:
        db.close()


@alertRouter.get("/alerts/{alert_id}")
async def get_alert(
    alert_id: str,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,
):
    _auth_with_key(x_api_key, api_key)

    db = SessionLocal()
    try:
        alert = db.query(AlertDB).filter(AlertDB.alert_id == alert_id).first()
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        return {
            "alert_id": alert.alert_id,
            "attacked_address": alert.attacked_address,
            "exploiter_address": alert.exploiter_address,
            "severity": alert.severity.value if alert.severity else "UNKNOWN",
            "message": alert.message,
            "timestamp": alert.timestamp.isoformat() if alert.timestamp else None,
            "risk_score": alert.risk_score,
        }
    finally:
        db.close()


@alertRouter.get("/stats")
async def alert_stats(
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,
):
    _auth_with_key(x_api_key, api_key)

    db = SessionLocal()
    try:
        total = db.query(AlertDB).count()
        critical = db.query(AlertDB).filter(AlertDB.severity == SeverityEnum.CRITICAL).count()
        suspicious = db.query(AlertDB).filter(AlertDB.severity == SeverityEnum.SUSPICIOUS).count()

        return {
            "total": total,
            "critical": critical,
            "suspicious": suspicious,
            "avg_score": 0,
        }
    finally:
        db.close()
