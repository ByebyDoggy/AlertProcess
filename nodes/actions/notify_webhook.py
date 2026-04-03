"""Webhook 通知动作 — 异步发送 HTTP Webhook"""

from __future__ import annotations

from typing import Any

import httpx

from nodes.base import NodeRegistry
from nodes.actions.base import BaseAction


class NotifyWebhookAction(BaseAction):
    """
    Webhook 通知动作 — 异步发送 HTTP POST 请求到指定 URL。

    配置:
    - url: Webhook URL
    - method: HTTP 方法（默认 POST）
    - headers: 自定义请求头
    - timeout: 超时秒数（默认 10）
    - include_fields: 要包含的字段列表（默认发送完整 context）
    """

    name: str = "notify_webhook_action"
    label: str = "Webhook 通知"
    description: str = "异步发送 Webhook HTTP 请求"
    icon: str = "\U0001f517"
    color: str = "#3b82f6"

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "format": "uri",
                    "description": "Webhook URL",
                },
                "method": {
                    "type": "string",
                    "enum": ["POST", "PUT", "PATCH"],
                    "default": "POST",
                },
                "headers": {
                    "type": "object",
                    "default": {"Content-Type": "application/json"},
                    "description": "自定义请求头",
                },
                "timeout": {
                    "type": "number",
                    "minimum": 1,
                    "maximum": 60,
                    "default": 10,
                    "description": "超时秒数",
                },
                "include_fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": "要包含的字段（空列表=全部）",
                },
            },
        }

    @classmethod
    def get_default_config(cls) -> dict[str, Any]:
        return {
            "url": "",
            "method": "POST",
            "headers": {"Content-Type": "application/json"},
            "timeout": 10,
            "include_fields": [],
        }

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors = []
        if not config.get("url"):
            errors.append("url is required")
        method = config.get("method", "POST")
        if method not in ("POST", "PUT", "PATCH"):
            errors.append("method must be POST, PUT or PATCH")
        return errors

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        url = self.config.get("url", "")
        method = self.config.get("method", "POST")
        headers = self.config.get("headers", {"Content-Type": "application/json"})
        timeout = self.config.get("timeout", 10)
        include_fields = self.config.get("include_fields", [])

        if not url:
            return {"action": "notify_webhook", "success": False, "error": "url not configured"}

        # 构建请求体
        if include_fields:
            payload = {k: context[k] for k in include_fields if k in context}
        else:
            # 过滤掉内部字段
            payload = {k: v for k, v in context.items() if not k.startswith("_")}

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(method, url, json=payload, headers=headers)

            return {
                "action": "notify_webhook",
                "success": 200 <= response.status_code < 300,
                "status_code": response.status_code,
                "url": url,
            }
        except httpx.TimeoutException:
            return {"action": "notify_webhook", "success": False, "error": "timeout", "url": url}
        except Exception as e:
            return {"action": "notify_webhook", "success": False, "error": str(e), "url": url}


NodeRegistry.register(NotifyWebhookAction)
