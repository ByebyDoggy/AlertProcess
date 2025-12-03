from datetime import datetime
from sqlalchemy import Enum, Text, DateTime, Column, String, Integer
from sqlalchemy.ext.declarative import declarative_base
import enum
from config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
# 创建基类
Base = declarative_base()


# 定义数据库模型
class SeverityEnum(str, enum.Enum):
    UNKNOWN = "UNKNOWN"
    SUSPICIOUS = "SUSPICIOUS"
    CRITICAL = "CRITICAL"
    UNDEFINED = "UNDEFINED"


class AlertDB(Base):
    __tablename__ = "alerts"

    alert_id = Column(String, primary_key=True, index=True)
    attacked_address = Column(String, index=True)
    exploiter_address = Column(String, index=True)
    severity = Column(Enum(SeverityEnum), default=SeverityEnum.UNKNOWN)
    message = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.now)
    risk_score = Column(String, nullable=True, default="PENDING")  # 新增字段用于存储可信度评分


class ContractAddressDB(Base):
    __tablename__ = "contract_addresses"

    contract_address = Column(String, primary_key=True, index=True)
    chain_id = Column(Integer, index=True)
    entity_id = Column(String,nullable=True)
    entity_type = Column(String,nullable=True)
    entity_name = Column(String,nullable=True)
    labels = Column(Text,nullable=True)  # 存储为JSON字符串
    address_create_time = Column(DateTime, nullable=True)


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)
