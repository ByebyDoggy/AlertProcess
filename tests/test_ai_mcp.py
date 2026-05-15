from __future__ import annotations

import pytest

from mcp_server.client import AlertProcessorClient
from mcp_server import rule_chain_tools
from services.ai.rule_chain_generator import RuleChainGenerationError, generate_rule_chain_draft


@pytest.mark.asyncio
async def test_mcp_client_uses_bearer_token_header(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True}

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers, json):
            captured.update({"method": method, "url": url, "headers": headers, "json": json})
            return Response()

    monkeypatch.setattr("mcp_server.client.httpx.AsyncClient", FakeAsyncClient)

    result = await AlertProcessorClient(base_url="http://alert", token="jwt-token").request("GET", "/rule-chain/schema/mcp")

    assert result == {"ok": True}
    assert captured["headers"] == {
        "Content-Type": "application/json",
        "Authorization": "Bearer jwt-token",
    }
    assert "X-API-Key" not in captured["headers"]


@pytest.mark.asyncio
async def test_mcp_generate_tool_forwards_mode_current_chain_and_constraints(monkeypatch):
    captured = {}

    class FakeClient:
        async def generate_draft(self, payload):
            captured.update(payload)
            return {"success": True}

    monkeypatch.setattr(rule_chain_tools, "AlertProcessorClient", FakeClient)

    result = await rule_chain_tools.rule_chain_generate_draft(
        prompt="detect bridge exploit",
        current_chain={"nodes": [{"id": "t1"}], "edges": []},
        constraints={"max_nodes": 5},
        mode="modify",
    )

    assert result == {"success": True}
    assert captured == {
        "prompt": "detect bridge exploit",
        "mode": "modify",
        "current_chain": {"nodes": [{"id": "t1"}], "edges": []},
        "constraints": {"max_nodes": 5},
    }


@pytest.mark.asyncio
async def test_ai_generator_rejects_non_json_model_output(monkeypatch):
    class FakeClient:
        model = "fake-model"

        async def chat_json(self, messages):
            return "not-json"

    monkeypatch.setattr("services.ai.rule_chain_generator.OpenAICompatibleClient.from_settings", lambda: FakeClient())

    with pytest.raises(RuleChainGenerationError) as exc:
        await generate_rule_chain_draft(
            prompt="build a chain",
            mode="new",
            current_chain={"nodes": [], "edges": []},
            constraints={},
            schema_bundle={"nodes": []},
        )

    assert exc.value.code == "AI_RESPONSE_NOT_JSON"
