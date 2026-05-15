from __future__ import annotations

import os
from typing import Any

import httpx


class AlertProcessorClient:
    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("ALERT_PROCESSOR_BASE_URL") or "http://localhost:8000").rstrip("/")
        self.token = token or os.getenv("ALERT_PROCESSOR_TOKEN") or ""

    async def request(self, method: str, path: str, json_body: dict[str, Any] | None = None) -> Any:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.request(method, f"{self.base_url}{path}", headers=headers, json=json_body)
        resp.raise_for_status()
        return resp.json()

    async def get_schema(self) -> dict[str, Any]:
        return await self.request("GET", "/rule-chain/schema/mcp")

    async def generate_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", "/rule-chain/ai/generate", payload)

    async def validate_draft(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
        return await self.request("POST", "/rule-chain/validate", {"nodes": nodes, "edges": edges})

    async def create_chain(self, payload: dict[str, Any]) -> dict[str, Any]:
        validation = await self.validate_draft(payload.get("nodes", []), payload.get("edges", []))
        if not validation.get("valid"):
            return {"created": False, "validation": validation}
        created = await self.request("POST", "/rule-chain/", payload)
        return {"created": True, "chain": created, "validation": validation}

    async def update_chain(self, chain_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if "nodes" in payload or "edges" in payload:
            validation = await self.validate_draft(payload.get("nodes", []), payload.get("edges", []))
            if not validation.get("valid"):
                return {"updated": False, "validation": validation}
        else:
            validation = None
        updated = await self.request("PUT", f"/rule-chain/{chain_id}", payload)
        return {"updated": True, "chain": updated, "validation": validation}
