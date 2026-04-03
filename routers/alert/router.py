import requests
from fastapi import APIRouter, Header, HTTPException, BackgroundTasks
from models import AlertInput
import uuid
from datetime import datetime
from typing import Optional

from config import settings
from database.models import SessionLocal, AlertDB, SeverityEnum, RuleChainDB
from models import FinalAlert, SeverityEnum as ModelSeverityEnum

from engine.parser import ChainParser
from engine.executor import ChainExecutor
import nodes


nodes.init_registry()


alertRouter = APIRouter(
    prefix="/alert",
    tags=["alert"]
)

_chain_executor = ChainExecutor()


class AlertProcessingPipeline:
    """
    使用新引擎 (engine/) 的告警处理管道。
    """

    def _load_enabled_chains(self) -> list[tuple[str, dict]]:
        """从数据库加载所有已启用的规则链配置"""
        chains = []
        db = SessionLocal()
        try:
            db_chains = db.query(RuleChainDB).filter(RuleChainDB.enabled == 1).all()
            for db_chain in db_chains:
                try:
                    config = (json.loads(db_chain.chain_config)
                              if isinstance(db_chain.chain_config, str)
                              else db_chain.chain_config)
                    parsed_chain = ChainParser.parse(config)
                    chains.append((db_chain.id, parsed_chain))
                except Exception:
                    pass
        finally:
            db.close()
        return chains

    async def process(self, alert: AlertInput) -> FinalAlert:
        """使用新引擎执行规则链处理告警"""
        import json

        alert_id = str(uuid.uuid4())
        alert_data = alert.model_dump()

        # 执行所有已启用的规则链
        chain_results = []
        enabled_chains = self._load_enabled_chains()
        chain_severity = None
        chain_score = 0.0
        chain_tags = []

        for chain_id, parsed_chain in enabled_chains:
            try:
                ctx = await _chain_executor.execute(parsed_chain, alert_data)
                if ctx.get_success():
                    chain_results.append({
                        "chain_id": chain_id,
                        "severity": ctx.final_severity,
                        "score": ctx.final_score,
                        "tags": ctx.collected_labels,
                    })
                    if ctx.final_severity and ctx.final_severity != "UNKNOWN":
                        chain_severity = ctx.final_severity
                    if ctx.final_score > chain_score:
                        chain_score = ctx.final_score
                    chain_tags.extend(t for t in ctx.collected_labels if t not in chain_tags)
            except Exception:
                pass

        severity = ModelSeverityEnum.UNKNOWN
        if chain_severity:
            try:
                severity = ModelSeverityEnum(chain_severity)
            except ValueError:
                pass

        final_alert = FinalAlert(
            alert_id=alert_id,
            chain_id=alert.chain_id,
            tx_hash=alert.tx_hash,
            severity=severity,
            score=chain_score,
            detections=[],
            matched_rules=[],
            context=None,
            timestamp=datetime.now(),
            metadata={
                "chain_results": chain_results,
                "chain_severity": chain_severity,
                "chain_score": chain_score,
                "chain_tags": chain_tags,
            }
        )

        return final_alert


pipeline = AlertProcessingPipeline()


def _map_to_db_severity(severity: ModelSeverityEnum) -> SeverityEnum:
    """Map model severity to database severity"""
    mapping = {
        ModelSeverityEnum.UNKNOWN: SeverityEnum.UNKNOWN,
        ModelSeverityEnum.LOW: SeverityEnum.SUSPICIOUS,
        ModelSeverityEnum.MEDIUM: SeverityEnum.SUSPICIOUS,
        ModelSeverityEnum.HIGH: SeverityEnum.CRITICAL,
        ModelSeverityEnum.CRITICAL: SeverityEnum.CRITICAL,
    }
    return mapping.get(severity, SeverityEnum.UNKNOWN)


async def process_alert_task(alert: AlertInput, alert_id: str):
    """Background task to process alert"""
    result = await pipeline.process(alert)

    db = SessionLocal()
    try:
        db_alert = db.query(AlertDB).filter(AlertDB.alert_id == alert_id).first()
        if db_alert:
            db_alert.risk_score = str(result.score)
            db_alert.severity = _map_to_db_severity(result.severity)
        db.commit()
    finally:
        db.close()

    if settings.notify_webhook_url and result.score > 200:
        try:
            requests.post(settings.notify_webhook_url, json={
                "alert_id": alert_id,
                "attacked_address": alert.attacked_address,
                "exploiter_address": alert.exploiter_address,
                "risk_score": result.score,
                "severity": result.severity.value,
                "result": result.model_dump(),
            })
        except Exception:
            pass


@alertRouter.post("/submit")
async def receive_alert(
        alert: AlertInput,
        background_tasks: BackgroundTasks,
        x_api_key: Optional[str] = Header(None),
        api_key: Optional[str] = None
):
    auth_key = x_api_key if x_api_key else api_key

    if not auth_key:
        raise HTTPException(status_code=401, detail="API key is required")

    if auth_key != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")

    alert_id = str(uuid.uuid4())

    db = SessionLocal()

    try:
        db_alert = AlertDB(
            alert_id=alert_id,
            attacked_address=alert.attacked_address,
            exploiter_address=alert.exploiter_address,
            severity=SeverityEnum.SUSPICIOUS,
            message=f"Alert for transaction {alert.tx_hash}",
            timestamp=datetime.now(),
            risk_score="PENDING"
        )

        db.add(db_alert)
        db.commit()
        db.refresh(db_alert)

        background_tasks.add_task(process_alert_task, alert, alert_id)

        return {
            "status": "success",
            "message": "Alert received and authenticated",
            "alert_id": alert_id,
            "alert_data": alert.model_dump(),
            "risk_check_status": "pending",
            "detail": "Alert received and risk check started in background"
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to process alert: {str(e)}")
    finally:
        db.close()


@alertRouter.get("/alerts/{alert_id}")
async def get_alert(
        alert_id: str,
        x_api_key: Optional[str] = Header(None),
        api_key: Optional[str] = None
):
    auth_key = x_api_key if x_api_key else api_key

    if not auth_key:
        raise HTTPException(status_code=401, detail="API key is required")

    if auth_key != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")

    db = SessionLocal()

    try:
        alert = db.query(AlertDB).filter(AlertDB.alert_id == alert_id).first()

        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")

        return {
            "alert_id": alert.alert_id,
            "attacked_address": alert.attacked_address,
            "exploiter_address": alert.exploiter_address,
            "severity": alert.severity.value,
            "message": alert.message,
            "timestamp": alert.timestamp,
            "risk_score": alert.risk_score
        }

    finally:
        db.close()


@alertRouter.get("/alerts")
async def list_alerts(
        skip: int = 0,
        limit: int = 100,
        severity: Optional[str] = None,
        chain_id: Optional[int] = None,
        x_api_key: Optional[str] = Header(None),
        api_key: Optional[str] = None
):
    auth_key = x_api_key if x_api_key else api_key

    if not auth_key:
        raise HTTPException(status_code=401, detail="API key is required")

    if auth_key != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")

    db = SessionLocal()

    try:
        query = db.query(AlertDB)

        if severity:
            try:
                sev = SeverityEnum(severity)
                query = query.filter(AlertDB.severity == sev)
            except ValueError:
                pass

        total = query.count()
        alerts = query.order_by(AlertDB.timestamp.desc()).offset(skip).limit(limit).all()

        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "alerts": [
                {
                    "alert_id": alert.alert_id,
                    "attacked_address": alert.attacked_address,
                    "exploiter_address": alert.exploiter_address,
                    "severity": alert.severity.value,
                    "message": alert.message,
                    "timestamp": alert.timestamp.isoformat() if alert.timestamp else None,
                    "risk_score": alert.risk_score,
                    "chain_id": getattr(alert, 'chain_id', None)
                }
                for alert in alerts
            ]
        }

    finally:
        db.close()


@alertRouter.get("/stats")
async def get_stats(
        x_api_key: Optional[str] = Header(None),
        api_key: Optional[str] = None
):
    auth_key = x_api_key if x_api_key else api_key

    if not auth_key:
        raise HTTPException(status_code=401, detail="API key is required")

    if auth_key != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")

    db = SessionLocal()

    try:
        total = db.query(AlertDB).count()
        critical = db.query(AlertDB).filter(AlertDB.severity == SeverityEnum.CRITICAL).count()
        suspicious = db.query(AlertDB).filter(AlertDB.severity == SeverityEnum.SUSPICIOUS).count()
        unknown = db.query(AlertDB).filter(AlertDB.severity == SeverityEnum.UNKNOWN).count()

        scores = db.query(AlertDB.risk_score).filter(AlertDB.risk_score != "PENDING").all()
        avg_score = 0
        if scores:
            numeric_scores = [int(s[0]) for s in scores if s[0] and s[0].isdigit()]
            if numeric_scores:
                avg_score = sum(numeric_scores) // len(numeric_scores)

        return {
            "total": total,
            "critical": critical,
            "suspicious": suspicious,
            "unknown": unknown,
            "avg_score": avg_score
        }

    finally:
        db.close()
