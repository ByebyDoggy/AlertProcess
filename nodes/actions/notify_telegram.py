"""Telegram 通知动作 — 异步发送 Telegram 消息"""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, Field, field_validator

from nodes.base import NodeRegistry
from nodes.actions.base import BaseAction, ActionInputMixin, ActionOutputMixin


class NotifyTelegramAction(BaseAction):
    """
    Telegram 通知动作 — 异步发送 Telegram Bot 消息。
    """

    TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

    name: str = "notify_telegram_action"
    label: str = "Telegram 通知"
    description: str = "通过 Telegram Bot API 异步发送告警消息，支持 HTML/Markdown 格式和模板变量替换（{severity}/{score}/{tx_hash} 等）。需配置 bot_token 和 chat_id"
    icon: str = "\u2708"
    color: str = "#0ea5e9"

    # ── Pydantic 配置模型 ──
    class ConfigModel(BaseModel):
        bot_token: str = Field(default="", description="Telegram Bot Token")
        chat_id: str = Field(default="", description="目标聊天 ID")
        message_template: str = Field(
            default="\u26a0 Alert: [{severity}] Score={score} Tx={tx_hash}",
            description="消息模板",
        )
        parse_mode: str = Field(default="HTML", description="消息格式")
        timeout: int = Field(default=10, ge=1, le=60, description="超时秒数")

        @field_validator("bot_token")
        @classmethod
        def _token_required(cls, v):
            return v

        @field_validator("chat_id")
        @classmethod
        def _chat_required(cls, v):
            return v

        @field_validator("parse_mode")
        @classmethod
        def _valid_parse(cls, v):
            if v not in ("HTML", "Markdown", "MarkdownV2"):
                raise ValueError("parse_mode must be HTML, Markdown or MarkdownV2")
            return v

    def _render_message(self, context: dict[str, Any]) -> str:
        """用 context 变量填充消息模板"""
        template = self.config.get("message_template", "")
        try:
            return template.format(
                severity=context.get("final_severity", context.get("severity", "UNKNOWN")),
                score=context.get("final_score", context.get("score", 0)),
                tx_hash=context.get("tx_hash", "N/A"),
                from_address=context.get("from_address", "N/A"),
                to_address=context.get("to_address", "N/A"),
                chain_id=context.get("chain_id", "N/A"),
                labels=", ".join(context.get("final_labels", context.get("labels", []))),
            )
        except KeyError:
            return template

    async def process(self, input: ActionInputMixin) -> ActionOutputMixin:
        context = input.context
        bot_token = self.config.get("bot_token", "")
        chat_id = self.config.get("chat_id", "")
        parse_mode = self.config.get("parse_mode", "HTML")
        timeout = self.config.get("timeout", 10)

        if not bot_token or not chat_id:
            return ActionOutputMixin(
                score=0.0, passed=True, severity="UNKNOWN", labels=[],
                action_result={
                    "action": "notify_telegram",
                    "success": False,
                    "error": "bot_token and chat_id are required",
                },
            )

        message = self._render_message(context)
        url = self.TELEGRAM_API.format(token=bot_token)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    url,
                    json={
                        "chat_id": chat_id,
                        "text": message,
                        "parse_mode": parse_mode,
                    },
                )

            return ActionOutputMixin(
                score=0.0, passed=True, severity="UNKNOWN", labels=[],
                action_result={
                    "action": "notify_telegram",
                    "success": response.status_code == 200,
                    "status_code": response.status_code,
                    "chat_id": chat_id,
                },
            )
        except httpx.TimeoutException:
            return ActionOutputMixin(
                score=0.0, passed=True, severity="UNKNOWN", labels=[],
                action_result={"action": "notify_telegram", "success": False, "error": "timeout"},
            )
        except Exception as e:
            return ActionOutputMixin(
                score=0.0, passed=True, severity="UNKNOWN", labels=[],
                action_result={"action": "notify_telegram", "success": False, "error": str(e)},
            )


NodeRegistry.register(NotifyTelegramAction)
