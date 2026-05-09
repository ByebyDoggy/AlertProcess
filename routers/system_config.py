from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
systemConfigRouter = APIRouter(prefix="/system", tags=["system-config"])


class AIConfigResponse(BaseModel):
    enabled: bool = False
    provider: str = "openai-compatible"
    base_url: str = ""
    api_key: str = ""
    has_api_key: bool = False
    model: str = "gpt-4.1-mini"
    timeout_seconds: int = 60
    temperature: float = 0.2
    max_tokens: int = 4096


class AIConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    timeout_seconds: Optional[int] = Field(default=None, ge=3, le=300)
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=256, le=32768)


class AIConfigTestRequest(BaseModel):
    prompt: str = "Return a short JSON health check message."


class AIConfigTestResponse(BaseModel):
    success: bool
    message: str
    model: str = ""
    latency_ms: Optional[float] = None
    error: Optional[dict] = None


def _auth_with_key(x_api_key: Optional[str], api_key: Optional[str]) -> None:
    auth_key = x_api_key if x_api_key else api_key
    if not auth_key:
        raise HTTPException(status_code=401, detail="API key is required")


def _masked_ai_config() -> AIConfigResponse:
    from config.model import settings

    return AIConfigResponse(
        enabled=bool(settings.ai_enabled),
        base_url=settings.ai_base_url or "",
        api_key="******" if settings.ai_api_key else "",
        has_api_key=bool(settings.ai_api_key),
        model=settings.ai_model,
        timeout_seconds=settings.ai_timeout_seconds,
        temperature=settings.ai_temperature,
        max_tokens=settings.ai_max_tokens,
    )


@systemConfigRouter.get("/ai-config", response_model=AIConfigResponse)
async def get_ai_config(x_api_key: Optional[str] = Header(None), api_key: Optional[str] = None):
    _auth_with_key(x_api_key, api_key)
    return _masked_ai_config()


@systemConfigRouter.put("/ai-config", response_model=AIConfigResponse)
async def update_ai_config(
    body: AIConfigUpdate,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,
):
    _auth_with_key(x_api_key, api_key)
    from config.model import settings

    if body.enabled is not None:
        settings.ai_enabled = body.enabled
    if body.base_url is not None:
        settings.ai_base_url = body.base_url.rstrip("/") if body.base_url else ""
    if body.api_key is not None and body.api_key and body.api_key != "******":
        settings.ai_api_key = body.api_key
    if body.model is not None:
        settings.ai_model = body.model
    if body.timeout_seconds is not None:
        settings.ai_timeout_seconds = body.timeout_seconds
    if body.temperature is not None:
        settings.ai_temperature = body.temperature
    if body.max_tokens is not None:
        settings.ai_max_tokens = body.max_tokens

    try:
        settings.persist_to_env({
            "ai_enabled": "ai_enabled",
            "ai_base_url": "ai_base_url",
            "ai_api_key": "ai_api_key",
            "ai_model": "ai_model",
            "ai_timeout_seconds": "ai_timeout_seconds",
            "ai_temperature": "ai_temperature",
            "ai_max_tokens": "ai_max_tokens",
        })
    except Exception as e:
        logger.warning("[system-config] Persist AI config to .env failed: %s", e, exc_info=True)

    return _masked_ai_config()


@systemConfigRouter.post("/ai-config/test", response_model=AIConfigTestResponse)
async def test_ai_config(
    body: AIConfigTestRequest,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,
):
    _auth_with_key(x_api_key, api_key)
    from services.ai.client import AIClientError, OpenAICompatibleClient
    import time

    try:
        client = OpenAICompatibleClient.from_settings()
        started_at = time.monotonic()
        content = await client.chat_json(
            messages=[
                {"role": "system", "content": "You are a health check endpoint. Return JSON only."},
                {"role": "user", "content": body.prompt},
            ],
            max_tokens=128,
        )
        latency_ms = round((time.monotonic() - started_at) * 1000, 2)
        return AIConfigTestResponse(success=True, message=content[:500], model=client.model, latency_ms=latency_ms)
    except AIClientError as e:
        return AIConfigTestResponse(
            success=False,
            message="AI configuration test failed",
            error={"code": e.code, "message": e.message},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI configuration test failed: {e}") from e
