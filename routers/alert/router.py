import requests
from fastapi import APIRouter, Header, HTTPException, BackgroundTasks
from processor.core import AlertInput
import uuid
from datetime import datetime
from typing import Optional
from config import settings
from database.models import SessionLocal, AlertDB, SeverityEnum
from processor import *
alertRouter = APIRouter(
    prefix="/alert",
    tags=["alert"]
)
exploiter_label_processor = ExploiterARKMLabelCheckAlertProcessor(
    config=ExploiterARKMLabelCheckAlertProcessorConfig(
        arkm_cookie=settings.arkm_cookie,
    ),
)
victim_label_processor = VictimARKMLabelCheckAlertProcessor(
    config=VictimARKMLabelCheckAlertProcessorConfig(
        arkm_cookie=settings.arkm_cookie,
    ),
)
exploiter_create_time_processor = ExploiterCreateTimeProcessor(
    config=ExploiterCreateTimeAlertProcessorConfig(
    ),
)
gas_price_check_processor = TransactionGasPriceCheckAlertProcessor(
    config=GasPriceCheckConfig(
        chain_id_to_provider_url=settings.chainId_to_provider_url,
    ),
)
chained_processor = ChainedAlertProcessor(
    config=ChainedProcessorConfig(
        processors=[
            exploiter_label_processor,
            victim_label_processor,
            exploiter_create_time_processor,
            gas_price_check_processor,
        ]
    )
)

async def process_alert(alert: AlertInput,alert_id: str):
    result = await chained_processor.process_alert(alert)
    db = SessionLocal()
    db_alert = db.query(AlertDB).filter(AlertDB.alert_id == alert_id).first()
    if db_alert:
        db_alert.risk_score = str(result.score)
    db.commit()
    db.refresh(db_alert)
    if settings.notify_webhook_url:
        if result.score>200:
            requests.post(settings.notify_webhook_url,json={
                "alert_id": alert_id,
                "attacked_address": alert.attacked_address,
                "exploiter_address": alert.exploiter_address,
                "risk_score": result.score,
                "result": result.model_dump(),
            })
    return result


# Webhook端点，接收alert数据并进行鉴权
@alertRouter.post("/submit")
async def receive_alert(
        alert: AlertInput,
        background_tasks: BackgroundTasks,
        x_api_key: Optional[str] = Header(None),
        api_key: Optional[str] = None
):
    # 鉴权逻辑：检查请求头中的x-api-key或查询参数中的api_key
    # 优先使用请求头中的api_key
    auth_key = x_api_key if x_api_key else api_key

    if not auth_key:
        raise HTTPException(status_code=401, detail="API key is required")

    if auth_key != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")

    # 生成唯一的alert_id
    alert_id = str(uuid.uuid4())

    # 创建数据库会话

    db = SessionLocal()

    try:
        # 将接收到的alert数据保存到数据库
        db_alert = AlertDB(
            alert_id=alert_id,
            attacked_address=alert.attacked_address,
            exploiter_address=alert.exploiter_address,
            severity=SeverityEnum.SUSPICIOUS,  # 默认设置为可疑，可根据需要修改
            message=f"Alert for transaction {alert.tx_hash}",
            timestamp=datetime.now(),
            risk_score="PENDING"  # 初始状态为待处理
        )

        db.add(db_alert)
        db.commit()
        db.refresh(db_alert)

        # 在后台启动可信度检测任务
        background_tasks.add_task(process_alert, alert, alert_id)

        # 立即返回响应
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


# 获取Alert详情的端点
@alertRouter.get("/alerts/{alert_id}")
async def get_alert(
        alert_id: str,
        x_api_key: Optional[str] = Header(None),
        api_key: Optional[str] = None
):
    # 鉴权逻辑
    auth_key = x_api_key if x_api_key else api_key

    if not auth_key:
        raise HTTPException(status_code=401, detail="API key is required")

    if auth_key != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")

    # 获取数据库会话
    db = SessionLocal()

    try:
        # 查询Alert
        alert = db.query(AlertDB).filter(AlertDB.alert_id == alert_id).first()

        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")

        # 返回Alert详情
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