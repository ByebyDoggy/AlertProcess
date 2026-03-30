import asyncio
import requests
from fastapi import APIRouter, Header, HTTPException, BackgroundTasks
from models import AlertInput
import uuid
from datetime import datetime
from typing import Optional

from config import settings
from database.models import SessionLocal, AlertDB, SeverityEnum

from detectors.base import DetectorRegistry, Detector
from detectors.implementations.arkm_label_detector import ARKMLabelDetector, ARKMLabelDetectorConfig
from detectors.implementations.address_age_detector import AddressAgeDetector, AddressAgeDetectorConfig
from detectors.implementations.gas_price_detector import GasPriceDetector, GasPriceDetectorConfig
from detectors.implementations.address_type_detector import AddressTypeDetector, AddressTypeDetectorConfig
from detectors.implementations.flash_loan_detector import FlashLoanDetector, FlashLoanDetectorConfig
from detectors.implementations.token_approval_detector import TokenApprovalDetector, TokenApprovalDetectorConfig
from detectors.implementations.token_anomaly_detector import TokenAnomalyDetector, TokenAnomalyDetectorConfig
from detectors.implementations.address_graph_detector import AddressGraphDetector, AddressGraphDetectorConfig

from data_providers.context_builder import TransactionContextBuilder
from scoring.engine import ScoringEngine, ScoringConfig, DefaultScoringConfig
from rules.engine import RuleEngine, Rule, RuleConfig
from models import FinalAlert, SeverityEnum as ModelSeverityEnum
from database.models import SeverityEnum


alertRouter = APIRouter(
    prefix="/alert",
    tags=["alert"]
)


class AlertProcessingPipeline:
    """
    Unified pipeline using Detector-based architecture
    Replaces the old Processor chain
    """
    
    def __init__(self):
        self.context_builder = TransactionContextBuilder(
            chain_id_to_provider_url=settings.chainId_to_provider_url
        )
        self._init_detectors()
        self._init_scoring_engine()
        self._init_rule_engine()
    
    def _init_detectors(self):
        """Initialize all detectors"""
        self.detectors: list[Detector] = []
        
        if settings.arkm_cookie:
            self.detectors.append(ARKMLabelDetector(
                config=ARKMLabelDetectorConfig(arkm_cookie=settings.arkm_cookie)
            ))
        
        self.detectors.append(AddressAgeDetector(
            config=AddressAgeDetectorConfig(new_address_threshold_days=7)
        ))
        
        self.detectors.append(GasPriceDetector(
            config=GasPriceDetectorConfig(
                threshold_usd=100.0,
                chain_id_to_native_token_price={
                    1: 2000.0,
                    56: 700.0,
                    137: 1.0,
                }
            )
        ))
        
        self.detectors.append(AddressTypeDetector(
            config=AddressTypeDetectorConfig()
        ))

        self.detectors.append(FlashLoanDetector(
            config=FlashLoanDetectorConfig(
                large_flash_loan_threshold_usd=100000.0,
                chain_id_to_native_token_price={
                    1: 2000.0,
                    56: 300.0,
                    137: 1.0,
                }
            )
        ))

        self.detectors.append(TokenApprovalDetector(
            config=TokenApprovalDetectorConfig(
                check_infinite_approval=True,
                check_approval_to_unknown=True,
            )
        ))

        self.detectors.append(TokenAnomalyDetector(
            config=TokenAnomalyDetectorConfig(
                large_transfer_threshold=1000000.0,
            )
        ))

        self.detectors.append(AddressGraphDetector(
            config=AddressGraphDetectorConfig(
                centralization_threshold=5,
            )
        ))
    
    def _init_scoring_engine(self):
        """Initialize scoring engine with exploit analysis config"""
        self.scoring_engine = ScoringEngine(
            config=DefaultScoringConfig.exploit_analysis()
        )
    
    def _init_rule_engine(self):
        """Initialize rule engine"""
        self.rule_engine = RuleEngine()
    
    async def process(self, alert: AlertInput) -> FinalAlert:
        """Execute full detection pipeline"""
        alert_id = str(uuid.uuid4())
        
        context = await self.context_builder.build(alert)
        
        detections = []
        for detector in self.detectors:
            try:
                result = await detector.detect_with_cache(alert, context)
                detections.append(result)
            except Exception as e:
                pass
        
        scoring_result = self.scoring_engine.calculate(context, detections)
        
        rule_results = await self.rule_engine.evaluate(context, detections)
        
        matched_rules = [r.rule_name for r in rule_results if r.matched]
        
        severity = scoring_result.severity
        
        final_alert = FinalAlert(
            alert_id=alert_id,
            chain_id=alert.chain_id,
            tx_hash=alert.tx_hash,
            severity=severity,
            score=scoring_result.total_score,
            detections=detections,
            matched_rules=matched_rules,
            context=context,
            timestamp=datetime.now(),
            metadata={
                "scoring_details": scoring_result.dimension_scores,
                "rule_results": [r.model_dump() for r in rule_results],
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
