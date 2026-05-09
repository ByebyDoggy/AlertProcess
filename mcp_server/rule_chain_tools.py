from __future__ import annotations

from typing import Any

from mcp_server.client import AlertProcessorClient


async def rule_chain_get_schema() -> dict[str, Any]:
    return await AlertProcessorClient().get_schema()


async def rule_chain_generate_draft(
    prompt: str,
    current_chain: dict[str, Any] | None = None,
    constraints: dict[str, Any] | None = None,
    mode: str = "new",
) -> dict[str, Any]:
    return await AlertProcessorClient().generate_draft({
        "prompt": prompt,
        "mode": mode,
        "current_chain": current_chain or {"nodes": [], "edges": []},
        "constraints": constraints or {},
    })


async def rule_chain_validate_draft(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    return await AlertProcessorClient().validate_draft(nodes, edges)


async def rule_chain_create(
    name: str,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    description: str = "",
    enabled: bool = True,
) -> dict[str, Any]:
    return await AlertProcessorClient().create_chain({
        "name": name,
        "description": description,
        "enabled": enabled,
        "nodes": nodes,
        "edges": edges,
    })


async def rule_chain_update(chain_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return await AlertProcessorClient().update_chain(chain_id, payload)
