"""
依赖注入 - 统一管理数据库会话和 Service 实例

FastAPI 依赖注入系统，用于在 Router 中注入 Service 实例。
"""

from typing import Generator
from sqlalchemy.orm import Session
from fastapi import Depends

from database.models import SessionLocal
from services import RuleChainService, AlertService


# ============================================
# 数据库会话依赖
# ============================================

def get_db() -> Generator[Session, None, None]:
    """
    获取数据库会话

    使用方式:
        @router.get("/")
        async def endpoint(db: Session = Depends(get_db)):
            # 使用 db
            pass

    会话会在请求结束后自动关闭。
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================
# Service 依赖
# ============================================

def get_rule_chain_service(db: Session = Depends(get_db)) -> RuleChainService:
    """
    获取规则链 Service

    使用方式:
        @router.get("/")
        async def endpoint(service: RuleChainService = Depends(get_rule_chain_service)):
            return service.list_chains()
    """
    return RuleChainService(db)


def get_alert_service(db: Session = Depends(get_db)) -> AlertService:
    """
    获取告警 Service

    使用方式:
        @router.post("/")
        async def endpoint(service: AlertService = Depends(get_alert_service)):
            return service.submit_alert(request)
    """
    return AlertService(db)
