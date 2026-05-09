from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from engine.parser import ChainParser
from engine.validator import ChainValidator
from routers.rule_chain.router import RuleEdge, RuleNode, _to_validate_error, build_chain_config
from services.ai.client import AIClientError, OpenAICompatibleClient
from services.ai.prompts import build_rule_chain_messages


class RuleChainDraft(BaseModel):
    name: str = "AI 生成规则链"
    description: str = ""
    nodes: list[RuleNode] = Field(default_factory=list)
    edges: list[RuleEdge] = Field(default_factory=list)


class RuleChainAIOutput(RuleChainDraft):
    explanation: str = ""
    assumptions: list[str] = Field(default_factory=list)


class RuleChainGenerationError(Exception):
    def __init__(self, code: str, message: str, suggestion: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.suggestion = suggestion


async def generate_rule_chain_draft(
    prompt: str,
    mode: Literal["new", "replace", "append", "modify"],
    current_chain: dict[str, Any] | None,
    constraints: dict[str, Any],
    schema_bundle: dict[str, Any],
) -> dict[str, Any]:
    client = OpenAICompatibleClient.from_settings()
    messages = build_rule_chain_messages(prompt, schema_bundle, current_chain, constraints, mode)
    try:
        content = await client.chat_json(messages=messages)
    except AIClientError:
        raise

    try:
        payload = json.loads(content)
    except json.JSONDecodeError as e:
        raise RuleChainGenerationError(
            "AI_RESPONSE_NOT_JSON",
            "AI 未返回合法 JSON",
            "请重试，或降低 prompt 复杂度。",
        ) from e

    try:
        ai_output = RuleChainAIOutput.model_validate(payload)
    except ValidationError as e:
        raise RuleChainGenerationError(
            "AI_DRAFT_INVALID_SCHEMA",
            f"AI 草稿结构不合法: {e.errors()[0]['msg']}",
            "请重新生成，或要求 AI 使用 /rule-chain/schema/mcp 中的标准 payload。",
        ) from e

    normalized_config = build_chain_config(ai_output.nodes, ai_output.edges)
    parsed_chain = ChainParser.parse(normalized_config)
    validation_errors = ChainValidator().validate(parsed_chain)
    errors = [_to_validate_error(e) for e in validation_errors if e.level == "error"]
    warnings = [_to_validate_error(e) for e in validation_errors if e.level != "error"]

    trigger_count = 0
    from nodes.base import NodeCategory, NodeRegistry
    for node in parsed_chain.nodes:
        node_class = NodeRegistry.get(node.node_type)
        if node_class and node_class.category == NodeCategory.INPUT:
            trigger_count += 1

    validation = {
        "valid": len(errors) == 0,
        "errors": [e.model_dump() for e in errors],
        "warnings": [w.model_dump() for w in warnings],
        "normalized_config": normalized_config,
        "stats": {
            "node_count": len(ai_output.nodes),
            "edge_count": len(ai_output.edges),
            "trigger_count": trigger_count,
            "error_count": len(errors),
            "warning_count": len(warnings),
        },
    }

    return {
        "draft": {
            "name": ai_output.name,
            "description": ai_output.description,
            "nodes": [n.model_dump(by_alias=True, exclude_none=True) for n in ai_output.nodes],
            "edges": [e.model_dump(by_alias=True, exclude_none=True) for e in ai_output.edges],
        },
        "validation": validation,
        "explanation": ai_output.explanation,
        "assumptions": ai_output.assumptions,
        "generation_meta": {
            "mode": mode,
            "model": client.model,
            "used_current_chain": bool((current_chain or {}).get("nodes") or (current_chain or {}).get("edges")),
        },
    }
