import logging

from pydantic_settings import BaseSettings
from typing import Optional
import os
import json

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """应用配置类，使用pydantic-settings管理配置

    配置优先级（从高到低）：
    1. 环境变量
    2. .env.local（本地覆盖，不提交到 Git）
    3. .env.{DEVELOPER_NAME}（开发者个人配置，不提交到 Git）
    4. .env（全局配置，提交到 Git）
    5. 默认值
    """

    # ── 开发者配置 ──
    developer_name: Optional[str] = None  # 开发者名称，用于隔离数据库和配置
    developer_db_suffix: Optional[str] = None  # 数据库文件后缀，如 "_alice"

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

    # Moralis API 配置（支持多 Key 轮换，优先级从高到低自动切换）
    # 兼容旧格式：单个字符串；新格式：JSON 数组 ["key1", "key2"]
    moralis_api_key: Optional[str | list[str]] = None

    # ARKM API配置
    arkm_cookie: Optional[str] = None

    # BlockSec API配置
    blocksec_cookie: Optional[str] = None

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

    # ── Moralis API Key 池 (从 apipool-server 加载) ──
    # 指定 apipool-server 上存储 Moralis API Key 的 pool identifier
    moralis_pool_identifier: Optional[str] = None      # e.g. "moralis-keys"

    # ── 区块时间配置（用于地址年龄的区块差估算） ──
    # JSON 字符串格式: {"1": 12, "56": 3, "137": 2}
    # key=chain_id, value=单块时间(秒)
    # 未配置的链使用默认值，也可通过前端页面修改
    block_time_config: dict = {}

    # 日志接收 (EVMLogListener → AlertProcessor) 配置
    ingest_enabled: bool = True
    ingest_max_batch_size: int = 5000       # 单次推送最大日志数

    # ── OpenAI 兼容 AI 配置（规则链 AI 生成 / MCP 工具） ──
    ai_enabled: bool = False
    ai_base_url: Optional[str] = None
    ai_api_key: Optional[str] = None
    ai_model: str = "gpt-4.1-mini"
    ai_timeout_seconds: int = 60
    ai_temperature: float = 0.2
    ai_max_tokens: int = 4096


    class Config:
        # 支持多环境配置文件，优先级从高到低
        env_file = None if os.environ.get('DOCKER_ENV') == 'true' else (
            ".env.local",  # 本地覆盖（最高优先级）
            f".env.{os.environ.get('DEVELOPER_NAME', '')}",  # 开发者个人配置
            ".env"  # 全局配置
        )
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"

    def model_post_init(self, __context) -> None:
        """解析 apipool_pool_map / block_time_config 的 JSON 字符串格式

        并应用开发者数据库后缀
        """
        # 解析 JSON 字符串格式的配置
        for attr in ("apipool_pool_map", "block_time_config"):
            val = getattr(self, attr)
            if isinstance(val, str):
                try:
                    setattr(self, attr, json.loads(val))
                except (json.JSONDecodeError, TypeError):
                    setattr(self, attr, {})

        # 应用开发者数据库后缀
        self._apply_developer_db_suffix()

    def _apply_developer_db_suffix(self) -> None:
        """为数据库 URL 应用开发者后缀

        示例:
            database_url = "sqlite:///./alerts.db"
            developer_db_suffix = "_alice"
            结果: "sqlite:///./alerts_alice.db"
        """
        # 优先使用 developer_db_suffix，其次使用 developer_name
        suffix = self.developer_db_suffix or (
            f"_{self.developer_name}" if self.developer_name else ""
        )

        if suffix and self.database_url:
            # 处理 SQLite URL
            if self.database_url.startswith("sqlite:///"):
                db_path = self.database_url.replace("sqlite:///", "")
                if db_path.endswith(".db"):
                    db_path = db_path[:-3] + suffix + ".db"
                    self.database_url = f"sqlite:///{db_path}"
                    logger.info(f"[Settings] Applied developer DB suffix: {self.database_url}")
            # 可以扩展支持其他数据库类型
            elif "postgresql" in self.database_url or "mysql" in self.database_url:
                # 对于 PostgreSQL/MySQL，可以修改数据库名
                # 例如: postgresql://user:pass@localhost/alerts -> postgresql://user:pass@localhost/alerts_alice
                if "/" in self.database_url:
                    parts = self.database_url.rsplit("/", 1)
                    if len(parts) == 2:
                        db_name = parts[1].split("?")[0]  # 移除查询参数
                        query_params = "?" + parts[1].split("?")[1] if "?" in parts[1] else ""
                        new_db_name = db_name + suffix
                        self.database_url = f"{parts[0]}/{new_db_name}{query_params}"
                        logger.info(f"[Settings] Applied developer DB suffix: {self.database_url}")

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