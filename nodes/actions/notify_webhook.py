from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, Field, field_validator

from nodes.base import NodeRegistry
from nodes.actions.base import BaseAction, ActionInputMixin, ActionOutputMixin


class NotifyWebhookAction(BaseAction):
    """
    Webhook 通知动作 — 异步发送 HTTP POST 请求到指定 URL。
    """

    name: str = "notify_webhook_action"
    label: str = "Webhook 通知"
    description: str = "异步发送 HTTP 请求到指定 Webhook URL，支持 POST/PUT/PATCH 方法和自定义 Headers。可筛选要包含的字段，适用于对接外部告警平台或 Slack/Discord"
    icon: str = "\U0001f517"
    color: str = "#3b82f6"

    # ── Pydantic 配置模型 ──
    class ConfigModel(BaseModel):
        url: str = Field(default="", description="Webhook URL")
        method: str = Field(default="POST", description="HTTP 方法")
        headers: dict[str, str] = Field(
            default={"Content-Type": "application/json"}, description="自定义请求头"
        )
        timeout: int = Field(default=10, ge=1, le=60, description="超时秒数")
        include_fields: list[str] = Field(default=[], description="要包含的字段（空列表=全部）")

        @field_validator("url")
        @classmethod
        def _url_required(cls, v):
            return v

        @field_validator("method")
        @classmethod
        def _valid_method(cls, v):
            if v not in ("POST", "PUT", "PATCH"):
                raise ValueError("method must be POST, PUT or PATCH")
            return v

    async def process(self, input: ActionInputMixin) -> ActionOutputMixin:
        context = input.context
        url = self.config.get("url", "")
        method = self.config.get("method", "POST")
        headers = self.config.get("headers", {"Content-Type": "application/json"})
        timeout = self.config.get("timeout", 10)
        include_fields = self.config.get("include_fields", [])

        if not url:
            return ActionOutputMixin(
                score=0.0, passed=True, severity="UNKNOWN", labels=[],
                action_result={"action": "notify_webhook", "success": False, "error": "url not configured"},
            )

        # 构建请求体
        if include_fields:
            payload = {k: context[k] for k in include_fields if k in context}
        else:
            # 过滤掉内部字段
            payload = {k: v for k, v in context.items() if not k.startswith("_")}

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(method, url, json=payload, headers=headers)

            return ActionOutputMixin(
                score=0.0, passed=True, severity="UNKNOWN", labels=[],
                action_result={
                    "action": "notify_webhook",
                    "success": 200 <= response.status_code < 300,
                    "status_code": response.status_code,
                    "url": url,
                },
            )
        except httpx.TimeoutException:
            return ActionOutputMixin(
                score=0.0, passed=True, severity="UNKNOWN", labels=[],
                action_result={"action": "notify_webhook", "success": False, "error": "timeout", "url": url},
            )
        except Exception as e:
            return ActionOutputMixin(
                score=0.0, passed=True, severity="UNKNOWN", labels=[],
                action_result={"action": "notify_webhook", "success": False, "error": str(e), "url": url},
            )


NodeRegistry.register(NotifyWebhookAction)
