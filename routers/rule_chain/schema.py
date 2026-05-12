"""
规则链路由 - Schema 和元数据

提供节点类型、连接规则、MCP Schema 等元数据。
"""

from typing import Any
from fastapi import APIRouter
from fastapi.responses import JSONResponse
import logging

from nodes.base import (
    ALLOWED_TYPE_MAPPING,
    CATEGORY_ALLOWED_INPUTS,
    NodeCategory,
    NodeRegistry,
)


router = APIRouter()
logger = logging.getLogger(__name__)


def _get_connection_rules() -> dict[str, Any]:
    """获取连接规则"""
    return {
        "allowed_type_mapping": {
            src: sorted(targets) for src, targets in ALLOWED_TYPE_MAPPING.items()
        },
        "category_allowed_inputs": {
            cat.value: sorted(inputs) for cat, inputs in CATEGORY_ALLOWED_INPUTS.items()
        },
    }


def _get_mcp_schema_bundle() -> dict[str, Any]:
    """获取 MCP Schema 包"""
    import nodes

    nodes.init_registry()
    return {
        "standard_payload": {
            "nodes": [
                {
                    "id": "unique_node_id",
                    "type": "node_type_from_schema",
                    "label": "optional display name",
                    "config": {},
                    "position": {"x": 0, "y": 0},
                }
            ],
            "edges": [
                {
                    "id": "unique_edge_id",
                    "source": "source_node_id",
                    "sourcePort": "output_port_key",
                    "target": "target_node_id",
                    "targetPort": "input_port_key",
                }
            ],
        },
        "nodes": NodeRegistry.get_schema_for_frontend(),
        "connection_rules": _get_connection_rules(),
        "endpoints": {
            "validate": "POST /rule-chain/validate",
            "create": "POST /rule-chain/",
            "update": "PUT /rule-chain/{chain_id}",
            "test_run": "POST /rule-chain/{chain_id}/test-run",
            "test_node": "POST /rule-chain/test-node",
        },
    }


@router.get("/node-types")
async def get_node_types_alias():
    """返回前端可用的节点类型及配置 schema (无需认证，兼容旧入口)"""
    return NodeRegistry.get_schema_for_frontend()


@router.get("/detectors")
async def get_detectors():
    """
    获取所有已注册检测器节点的详细信息, 包括配置参数 schema 和默认值。
    """
    detector_nodes = NodeRegistry.get_by_category(NodeCategory.DETECTION)
    return {
        "detectors": [
            {
                "name": cls.name,
                "label": cls.label,
                "description": cls.description,
                "config_schema": cls.get_config_schema(),
                "default_config": cls.get_default_config(),
            }
            for cls in detector_nodes
        ],
    }


@router.get("/nodes")
async def get_node_types():
    """
    返回新引擎 NodeRegistry 中所有已注册节点的完整 Schema 信息。
    前端据此动态渲染节点面板、端口、配置表单。
    """
    return NodeRegistry.get_schema_for_frontend()


@router.get("/nodes-docs")
async def get_node_docs():
    """
    返回所有节点的详细文档信息（含 required_providers / provides / config_schema_raw 等）。
    供前端文档页面动态渲染，新增节点自动出现。
    """
    return NodeRegistry.get_docs_for_frontend()


@router.get("/connection-rules")
async def get_connection_rules():
    """
    返回数据类型兼容性矩阵, 供前端连线校验使用。
    """
    return _get_connection_rules()


@router.get("/mcp")
async def get_mcp_schema():
    """
    返回 AI/MCP 构造规则链所需的最小稳定 schema 包。
    """
    try:
        return JSONResponse(content=_get_mcp_schema_bundle())
    except Exception as e:
        logger.exception("[rule-chain] Failed to build MCP schema bundle")
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"Failed to build MCP schema bundle: {e}") from e
