from __future__ import annotations

import asyncio

from starlette.responses import PlainTextResponse

from middleware.auth_middleware import JWTAuthMiddleware


class FakeVerifier:
    def verify_token(self, token: str) -> dict:
        if token != "valid-token":
            raise AssertionError(f"unexpected token: {token}")
        return {"username": "alice", "role": "admin"}


async def _call_middleware(path: str, headers: dict[str, str] | None = None):
    captured_scope = {}

    async def app(scope, receive, send):
        captured_scope.update(scope)
        response = PlainTextResponse("ok")
        await response(scope, receive, send)

    middleware = JWTAuthMiddleware(
        app,
        secret_key="test-secret",
        algorithm="HS256",
        public_paths=["/api/health"],
    )
    middleware.verifier = FakeVerifier()
    raw_headers = [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()]
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": raw_headers,
        "scheme": "http",
        "server": ("testserver", 80),
        "state": {},
    }
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await middleware(scope, receive, send)
    status = next(message["status"] for message in messages if message["type"] == "http.response.start")
    return status, captured_scope


def test_protected_route_rejects_missing_bearer_token():
    status, _ = asyncio.run(_call_middleware("/protected"))

    assert status == 401


def test_protected_route_rejects_legacy_api_key_without_bearer_token():
    status, _ = asyncio.run(_call_middleware("/protected", {"X-API-Key": "default_secret_key_change_in_production"}))

    assert status == 401


def test_protected_route_accepts_valid_bearer_token():
    token = "valid-token"

    status, scope = asyncio.run(_call_middleware("/protected", {"Authorization": f"Bearer {token}"}))

    assert status == 200
    assert scope["state"]["user"]["username"] == "alice"


def test_public_route_ignores_legacy_api_key():
    status, _ = asyncio.run(_call_middleware("/api/health", {"X-API-Key": "anything"}))

    assert status == 200
