from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    """应用配置类，使用pydantic-settings管理配置"""

    # API相关配置
    api_key: str = "default_secret_key_change_in_production"

    # 数据库配置
    database_url: str = "sqlite:///./alerts.db"

    # 应用配置
    app_name: str = "Alert Webhook Service"
    app_description: str = "用于接收和处理告警信息的Webhook服务"
    app_version: str = "1.0.0"

    # 服务器配置
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = True

    # 可信度检测配置
    risk_check_enabled: bool = True
    risk_check_default_score: str = "PENDING"

    # Moralis API配置
    moralis_api_key: Optional[str] = None

    # ARKM API配置
    arkm_cookie: Optional[str] = None

    # notify webhook url
    notify_webhook_url: Optional[str] = None

    # chainId_to_provider_url 映射表
    chainId_to_provider_url: dict = {
        1: "https://eth-mainnet.g.alchemy.com/v2/", # ETH
        56: "https://bsc-dataseed.binance.org/", # BNB
        137: "https://polygon-rpc.com/",
    }


    class Config:
        # 检查是否在Docker环境中（通过环境变量DOCKER_ENV判断）
        env_file = None if os.environ.get('DOCKER_ENV') == 'true' else ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False  # 环境变量不区分大小写
        # 始终优先使用环境变量，即使在使用.env文件的情况下
        env_file_priority = "low"


# 创建全局配置实例
settings = Settings()