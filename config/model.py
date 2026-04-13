import logging

from pydantic_settings import BaseSettings
from typing import Optional
import os
import json

logger = logging.getLogger(__name__)


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

    # MarketDataBase 服务地址 (用于获取代币价格和精度)
    market_db_url: str = "http://localhost:8002"

    # ── apipool-server 配置 (所有 RPC 调用统一通过 apipool-server 管理) ──
    # apipool-server 地址
    apipool_server_url: Optional[str] = None           # e.g. "http://localhost:8000"
    apipool_username: Optional[str] = None
    apipool_password: Optional[str] = None
    # 每条链对应的 pool_identifier, 未配置的链不可用
    # JSON 字符串格式: {"1": "ethereum-rpc", "56": "bsc-rpc", "137": "polygon-rpc"}
    # 也支持 Python dict 格式 (通过代码设置)
    apipool_pool_map: dict = {}

    # 日志接收 (EVMLogListener → AlertProcessor) 配置
    ingest_enabled: bool = True
    ingest_max_batch_size: int = 5000       # 单次推送最大日志数


    class Config:
        env_file = None if os.environ.get('DOCKER_ENV') == 'true' else ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        env_file_priority = "low"
        extra = "ignore"

    def model_post_init(self, __context) -> None:
        """解析 apipool_pool_map 的 JSON 字符串格式"""
        if isinstance(self.apipool_pool_map, str):
            try:
                self.apipool_pool_map = json.loads(self.apipool_pool_map)
            except (json.JSONDecodeError, TypeError):
                self.apipool_pool_map = {}

    # ── .env 持久化 ──

    @classmethod
    def _get_env_path(cls) -> str:
        """返回当前使用的 .env 文件路径"""
        env_file = cls.Config.env_file or ".env"
        return os.path.join(os.path.dirname(os.path.dirname(__file__)), env_file)

    def persist_to_env(self, key_mapping: dict[str, str]) -> None:
        """将指定的 setting 字段写回 .env 文件（原子替换）。

        Args:
            key_mapping: {setting字段名: .env中的key}，例如
                {"apipool_server_url": "apipool_server_url"}
        """
        env_path = self._get_env_path()
        if not os.path.exists(env_path):
            logger.warning(f"[settings] .env not found at {env_path}, skipping persist")
            return

        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        env_keys_needed = set(key_mapping.values())
        new_lines = []
        matched = set()

        for line in lines:
            stripped = line.strip()
            # 检查是否是目标 key (支持 "# key", "#key=", "key=value" 等格式)
            is_target = False
            target_key = None
            for ek in env_keys_needed:
                # 去掉行首的 "#" 和空白后检查是否以 ek 开头
                check = stripped
                if check.startswith("#"):
                    check = check[1:].lstrip()
                if check.startswith(ek) and (
                    len(check) == len(ek) or check[len(ek)] == "="
                ):
                    is_target = True
                    target_key = ek
                    break

            if is_target and target_key:
                attr_name = [k for k, v in key_mapping.items() if v == target_key][0]
                value = getattr(self, attr_name, None)
                if isinstance(value, dict):
                    value = json.dumps(value)
                elif value is None:
                    # 保留注释状态或空值
                    new_lines.append(line)
                    matched.add(target_key)
                    continue

                new_lines.append(f"{target_key}={value}\n")
                matched.add(target_key)
            else:
                new_lines.append(line)

        # 处理文件中不存在的 key → 追加到末尾
        missing = env_keys_needed - matched
        if missing:
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines.append("\n")
            for ek in sorted(missing):
                attr_name = [k for k, v in key_mapping.items() if v == ek][0]
                value = getattr(self, attr_name, "")
                if isinstance(value, dict):
                    value = json.dumps(value)
                new_lines.append(f"{ek}={value}\n")

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        logger.info(f"[settings] Persisted {len(matched)} config items to .env")


# 创建全局配置实例
settings = Settings()