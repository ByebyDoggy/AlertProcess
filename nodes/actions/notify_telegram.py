"""Telegram 通知动作 — 异步发送 Telegram 消息"""

from __future__ import annotations

from typing import Any

import httpx

from nodes.base import NodeRegistry
from nodes.actions.base import BaseAction


class NotifyTelegramAction(BaseAction):
    """
    Telegram 通知动作 — 异步发送 Telegram Bot 消息。

    配置:
    - bot_token: Telegram Bot Token
    - chat_id: 目标聊天 ID
    - message_template: 消息模板（支持 {severity}, {score}, {tx_hash} 等占位符）
    - parse_mode: 消息格式（HTML/Markdown/MarkdownV2）
    - timeout: 超时秒数（默认 10）
    """

    TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

    name: str = "notify_telegram_action"
    label: str = "Telegram 通知"
    description: str = "异步发送 Telegram Bot 消息"
    icon: str = "\u2708"
    color: str = "#0ea5e9"

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "bot_token": {
                    "type": "string",
                    "description": "Telegram Bot Token",
                },
                "chat_id": {
                    "type": "string",
                    "description": "目标聊天 ID",
                },
                "message_template": {
                    "type": "string",
                    "default": "\u26a0 Alert: [{severity}] Score={score} Tx={tx_hash}",
                    "description": "消息模板",
                },
                "parse_mode": {
                    "type": "string",
                    "enum": ["HTML", "Markdown", "MarkdownV2"],
                    "default": "HTML",
                },
                "timeout": {
                    "type": "number",
                    "minimum": 1,
                    "maximum": 60,
                    "default": 10,
                },
            },
        }

    @classmethod
    def get_default_config(cls) -> dict[str, Any]:
        return {
            "bot_token": "",
            "chat_id": "",
            "message_template": "\u26a0 Alert: [{severity}] Score={score} Tx={tx_hash}",
            "parse_mode": "HTML",
            "timeout": 10,
        }

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors = []
        if not config.get("bot_token"):
            errors.append("bot_token is required")
        if not config.get("chat_id"):
            errors.append("chat_id is required")
        return errors

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

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        bot_token = self.config.get("bot_token", "")
        chat_id = self.config.get("chat_id", "")
        parse_mode = self.config.get("parse_mode", "HTML")
        timeout = self.config.get("timeout", 10)

        if not bot_token or not chat_id:
            return {
                "action": "notify_telegram",
                "success": False,
                "error": "bot_token and chat_id are required",
            }

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

            return {
                "action": "notify_telegram",
                "success": response.status_code == 200,
                "status_code": response.status_code,
                "chat_id": chat_id,
            }
        except httpx.TimeoutException:
            return {"action": "notify_telegram", "success": False, "error": "timeout"}
        except Exception as e:
            return {"action": "notify_telegram", "success": False, "error": str(e)}


NodeRegistry.register(NotifyTelegramAction)
