"""更新数据库动作 — 将执行结果写入数据库"""

from __future__ import annotations

from typing import Any

from nodes.base import NodeRegistry
from nodes.actions.base import BaseAction


class UpdateDatabaseAction(BaseAction):
    """
    更新数据库动作 — 将规则链执行结果写入本地数据库。

    配置:
    - table: 目标表名
    - fields: 要写入的字段映射 {context_key: column_name}
    - update_mode: "insert" 或 "upsert"（默认 "insert"）
    """

    name: str = "update_database_action"
    label: str = "更新数据库"
    description: str = "将执行结果写入数据库"
    icon: str = "\U0001f4be"
    color: str = "#8b5cf6"

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "table": {
                    "type": "string",
                    "default": "alerts",
                    "description": "目标表名",
                },
                "fields": {
                    "type": "object",
                    "default": {},
                    "description": "字段映射 {context_key: column_name}",
                },
                "update_mode": {
                    "type": "string",
                    "enum": ["insert", "upsert"],
                    "default": "insert",
                    "description": "写入模式",
                },
            },
        }

    @classmethod
    def get_default_config(cls) -> dict[str, Any]:
        return {
            "table": "alerts",
            "fields": {},
            "update_mode": "insert",
        }

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors = []
        if not config.get("table"):
            errors.append("table is required")
        mode = config.get("update_mode", "insert")
        if mode not in ("insert", "upsert"):
            errors.append("update_mode must be 'insert' or 'upsert'")
        return errors

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        table = self.config.get("table", "alerts")
        fields = self.config.get("fields", {})
        update_mode = self.config.get("update_mode", "insert")

        if not table:
            return {"action": "update_database", "success": False, "error": "table not configured"}

        # 从 context 中提取要写入的字段
        row = {}
        for ctx_key, col_name in fields.items():
            if ctx_key in context:
                row[col_name] = context[ctx_key]

        # 框架实现 — 实际数据库操作需要数据库连接
        # 当前只记录意图，不执行实际 DB 操作
        return {
            "action": "update_database",
            "success": True,
            "table": table,
            "update_mode": update_mode,
            "row_keys": list(row.keys()),
            "row_count": len(row),
            "note": "framework implementation - no actual DB operation",
        }


NodeRegistry.register(UpdateDatabaseAction)
