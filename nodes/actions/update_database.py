from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from nodes.base import NodeRegistry
from nodes.actions.base import BaseAction, ActionInputMixin, ActionOutputMixin


class UpdateDatabaseAction(BaseAction):
    """
    更新数据库动作 — 将规则链执行结果写入本地数据库。
    """

    name: str = "update_database_action"
    label: str = "更新数据库"
    description: str = "将规则链执行结果写入数据库表，支持 insert 和 upsert 两种模式。通过字段映射将 context 中的数据映射到数据库列，用于告警持久化存储"
    icon: str = "\U0001f4be"
    color: str = "#8b5cf6"

    # ── Pydantic 配置模型 ──
    class ConfigModel(BaseModel):
        table: str = Field(default="alerts", description="目标表名")
        fields: dict[str, str] = Field(default={}, description="字段映射 {context_key: column_name}")
        update_mode: str = Field(default="insert", description="写入模式")

        @field_validator("table")
        @classmethod
        def _table_required(cls, v):
            return v

        @field_validator("update_mode")
        @classmethod
        def _valid_mode(cls, v):
            if v not in ("insert", "upsert"):
                raise ValueError("update_mode must be 'insert' or 'upsert'")
            return v

    async def process(self, input: ActionInputMixin) -> ActionOutputMixin:
        context = input.context
        table = self.config.get("table", "alerts")
        fields = self.config.get("fields", {})
        update_mode = self.config.get("update_mode", "insert")

        if not table:
            return ActionOutputMixin(
                score=0.0, passed=False, severity="UNKNOWN", labels=[],
                action_result={"action": "update_database", "success": False, "error": "table not configured"},
            )

        # 从 context 中提取要写入的字段
        row = {}
        for ctx_key, col_name in fields.items():
            if ctx_key in context:
                row[col_name] = context[ctx_key]

        # 框架实现 — 实际数据库操作需要数据库连接
        # 当前只记录意图，不执行实际 DB 操作
        return ActionOutputMixin(
            score=0.0, passed=True, severity="UNKNOWN", labels=[],
            action_result={
                "action": "update_database",
                "success": True,
                "table": table,
                "update_mode": update_mode,
                "row_keys": list(row.keys()),
                "row_count": len(row),
                "note": "framework implementation - no actual DB operation",
            },
        )


NodeRegistry.register(UpdateDatabaseAction)
