from __future__ import annotations

import json
from typing import Any

import httpx


class AIClientError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class OpenAICompatibleClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int = 60,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.max_tokens = max_tokens

    @classmethod
    def from_settings(cls) -> "OpenAICompatibleClient":
        from config.model import settings

        if not settings.ai_enabled:
            raise AIClientError("AI_CONFIG_MISSING", "AI 功能未启用")
        if not settings.ai_base_url or not settings.ai_api_key or not settings.ai_model:
            raise AIClientError("AI_CONFIG_MISSING", "AI 配置缺少 Base URL、API Key 或模型名")
        return cls(
            base_url=settings.ai_base_url,
            api_key=settings.ai_api_key,
            model=settings.ai_model,
            timeout_seconds=settings.ai_timeout_seconds,
            temperature=settings.ai_temperature,
            max_tokens=settings.ai_max_tokens,
        )

    async def chat_json(
        self,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": max_tokens or self.max_tokens,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
        except httpx.TimeoutException as e:
            raise AIClientError("AI_TIMEOUT", "AI 请求超时") from e
        except httpx.HTTPError as e:
            raise AIClientError("AI_REQUEST_FAILED", f"AI 请求失败: {e}") from e

        if resp.status_code >= 400:
            message = _extract_error_message(resp)
            raise AIClientError("AI_REQUEST_FAILED", message)

        try:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
            raise AIClientError("AI_RESPONSE_NOT_JSON", "AI 响应格式不符合 OpenAI Chat Completions 结构") from e

        if not isinstance(content, str) or not content.strip():
            raise AIClientError("AI_RESPONSE_NOT_JSON", "AI 响应内容为空")
        return content.strip()


def _extract_error_message(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        error = data.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
        if data.get("detail"):
            return str(data["detail"])
    except Exception:
        pass
    return f"AI 请求失败: HTTP {resp.status_code}"
