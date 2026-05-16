from __future__ import annotations

from backend.mcp_server.rule_chain_tools import (
    rule_chain_create,
    rule_chain_generate_draft,
    rule_chain_get_schema,
    rule_chain_update,
    rule_chain_validate_draft,
)

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover
    FastMCP = None


def create_server():
    if FastMCP is None:
        raise RuntimeError("mcp package is not installed")
    mcp = FastMCP("alert-processor-rule-chain")
    mcp.tool()(rule_chain_get_schema)
    mcp.tool()(rule_chain_generate_draft)
    mcp.tool()(rule_chain_validate_draft)
    mcp.tool()(rule_chain_create)
    mcp.tool()(rule_chain_update)
    return mcp


if __name__ == "__main__":
    create_server().run()
