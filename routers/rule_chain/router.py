from fastapi import APIRouter, Header, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid
import json

from database.models import SessionLocal, RuleChainDB
from engine.parser import ChainParser
from engine.validator import ChainValidator
from nodes.base import NodeCategory, NodeRegistry


ruleChainRouter = APIRouter(
    prefix="/rule-chain",
    tags=["rule-chain"]
)


class RuleNode(BaseModel):
    id: str
    type: str
    label: str
    config: dict = {}
    position: dict = {"x": 0, "y": 0}


class RuleEdge(BaseModel):
    id: str
    source: str
    source_port: str = "output"
    target: str
    target_port: str = "input"
    label: str = ""


class RuleChainCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    enabled: bool = True
    nodes: list = []
    edges: list = []


class RuleChainUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    nodes: Optional[list] = None
    edges: Optional[list] = None


class RuleChainResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    enabled: bool
    chain_config: dict
    created_at: datetime
    updated_at: datetime


class ValidateRequest(BaseModel):
    nodes: list
    edges: list


class ValidateError(BaseModel):
    type: str = "error"  # error | warning
    message: str
    node_id: Optional[str] = None
    edge_id: Optional[str] = None


class ValidateResponse(BaseModel):
    valid: bool
    errors: list[ValidateError] = []
    warnings: list[ValidateError] = []
    rule_tree: Optional[dict] = None
    stats: Optional[dict] = None


def get_db():
    db = SessionLocal()
    try:
        return db
    finally:
        pass


def build_chain_config(nodes: list, edges: list) -> dict:
    return {
        "nodes": nodes,
        "edges": edges
    }


@ruleChainRouter.get("/", response_model=list[RuleChainResponse])
async def list_rule_chains(
        x_api_key: Optional[str] = Header(None),
        api_key: Optional[str] = None
):
    auth_key = x_api_key if x_api_key else api_key
    if not auth_key:
        raise HTTPException(status_code=401, detail="API key is required")

    db = SessionLocal()
    try:
        chains = db.query(RuleChainDB).order_by(RuleChainDB.updated_at.desc()).all()
        result = []
        for chain in chains:
            chain_config = json.loads(chain.chain_config) if isinstance(chain.chain_config, str) else chain.chain_config
            result.append(RuleChainResponse(
                id=chain.id,
                name=chain.name,
                description=chain.description,
                enabled=bool(chain.enabled),
                chain_config=chain_config,
                created_at=chain.created_at,
                updated_at=chain.updated_at
            ))
        return result
    finally:
        db.close()


@ruleChainRouter.get("/{chain_id}", response_model=RuleChainResponse)
async def get_rule_chain(
        chain_id: str,
        x_api_key: Optional[str] = Header(None),
        api_key: Optional[str] = None
):
    auth_key = x_api_key if x_api_key else api_key
    if not auth_key:
        raise HTTPException(status_code=401, detail="API key is required")

    db = SessionLocal()
    try:
        chain = db.query(RuleChainDB).filter(RuleChainDB.id == chain_id).first()
        if not chain:
            raise HTTPException(status_code=404, detail="Rule chain not found")

        chain_config = json.loads(chain.chain_config) if isinstance(chain.chain_config, str) else chain.chain_config
        return RuleChainResponse(
            id=chain.id,
            name=chain.name,
            description=chain.description,
            enabled=bool(chain.enabled),
            chain_config=chain_config,
            created_at=chain.created_at,
            updated_at=chain.updated_at
        )
    finally:
        db.close()


@ruleChainRouter.post("/", response_model=RuleChainResponse)
async def create_rule_chain(
        chain_data: RuleChainCreate,
        x_api_key: Optional[str] = Header(None),
        api_key: Optional[str] = None
):
    auth_key = x_api_key if x_api_key else api_key
    if not auth_key:
        raise HTTPException(status_code=401, detail="API key is required")

    chain_id = str(uuid.uuid4())
    chain_config = build_chain_config(chain_data.nodes, chain_data.edges)

    db = SessionLocal()
    try:
        db_chain = RuleChainDB(
            id=chain_id,
            name=chain_data.name,
            description=chain_data.description,
            chain_config=json.dumps(chain_config),
            enabled=1 if chain_data.enabled else 0
        )
        db.add(db_chain)
        db.commit()
        db.refresh(db_chain)

        return RuleChainResponse(
            id=db_chain.id,
            name=db_chain.name,
            description=db_chain.description,
            enabled=bool(db_chain.enabled),
            chain_config=chain_config,
            created_at=db_chain.created_at,
            updated_at=db_chain.updated_at
        )
    finally:
        db.close()


@ruleChainRouter.put("/{chain_id}", response_model=RuleChainResponse)
async def update_rule_chain(
        chain_id: str,
        chain_data: RuleChainUpdate,
        x_api_key: Optional[str] = Header(None),
        api_key: Optional[str] = None
):
    auth_key = x_api_key if x_api_key else api_key
    if not auth_key:
        raise HTTPException(status_code=401, detail="API key is required")

    db = SessionLocal()
    try:
        chain = db.query(RuleChainDB).filter(RuleChainDB.id == chain_id).first()
        if not chain:
            raise HTTPException(status_code=404, detail="Rule chain not found")

        if chain_data.name is not None:
            chain.name = chain_data.name
        if chain_data.description is not None:
            chain.description = chain_data.description
        if chain_data.enabled is not None:
            chain.enabled = 1 if chain_data.enabled else 0
        if chain_data.nodes is not None or chain_data.edges is not None:
            existing_config = json.loads(chain.chain_config) if isinstance(chain.chain_config, str) else chain.chain_config
            nodes = chain_data.nodes if chain_data.nodes is not None else existing_config.get("nodes", [])
            edges = chain_data.edges if chain_data.edges is not None else existing_config.get("edges", [])
            chain.chain_config = json.dumps(build_chain_config(nodes, edges))

        chain.updated_at = datetime.now()
        db.commit()
        db.refresh(chain)

        chain_config = json.loads(chain.chain_config) if isinstance(chain.chain_config, str) else chain.chain_config
        return RuleChainResponse(
            id=chain.id,
            name=chain.name,
            description=chain.description,
            enabled=bool(chain.enabled),
            chain_config=chain_config,
            created_at=chain.created_at,
            updated_at=chain.updated_at
        )
    finally:
        db.close()


@ruleChainRouter.delete("/{chain_id}")
async def delete_rule_chain(
        chain_id: str,
        x_api_key: Optional[str] = Header(None),
        api_key: Optional[str] = None
):
    auth_key = x_api_key if x_api_key else api_key
    if not auth_key:
        raise HTTPException(status_code=401, detail="API key is required")

    db = SessionLocal()
    try:
        chain = db.query(RuleChainDB).filter(RuleChainDB.id == chain_id).first()
        if not chain:
            raise HTTPException(status_code=404, detail="Rule chain not found")

        db.delete(chain)
        db.commit()
        return {"status": "success", "message": "Rule chain deleted"}
    finally:
        db.close()


# ──────────────── 验证 & 元数据端点 ────────────────

@ruleChainRouter.post("/validate", response_model=ValidateResponse)
async def validate_chain(
        data: ValidateRequest,
        x_api_key: Optional[str] = Header(None),
        api_key: Optional[str] = None
):
    """
    验证规则链配置是否合法。
    使用新引擎 ChainParser + ChainValidator 进行完整校验。
    """
    errors = []
    warnings = []

    if not data.nodes:
        errors.append(ValidateError(type="error", message="规则链至少需要一个节点"))
        return ValidateResponse(valid=False, errors=errors)

    # 使用新引擎解析和校验
    raw_config = {"nodes": [dict(n) for n in data.nodes], "edges": [dict(e) for e in data.edges]}
    parsed_chain = ChainParser.parse(raw_config)
    validator = ChainValidator()
    validation_errors = validator.validate(parsed_chain)

    for ve in validation_errors:
        target = errors if ve.level == "error" else warnings
        target.append(ValidateError(
            type=ve.level,
            message=ve.message,
            node_id=ve.node_id,
            edge_id=ve.edge_id,
        ))

    # 统计信息
    trigger_count = sum(
        1 for n in data.nodes
        if NodeRegistry.get(n.get("type", ""))
        and NodeRegistry.get(n["type"]).category == NodeCategory.INPUT
    )

    stats = {
        "node_count": len(data.nodes),
        "edge_count": len(data.edges),
        "trigger_count": trigger_count,
        "is_reachable": len(errors) == 0,
    }

    return ValidateResponse(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        rule_tree=None,
        stats=stats,
    )


@ruleChainRouter.get("/schema/node-types")
async def get_node_types():
    """返回前端可用的节点类型及配置 schema (无需认证)"""
    return NodeRegistry.get_schema_for_frontend()


@ruleChainRouter.get("/schema/detectors")
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


@ruleChainRouter.get("/schema/nodes")
async def get_node_types():
    """
    返回新引擎 NodeRegistry 中所有已注册节点的完整 Schema 信息。
    前端据此动态渲染节点面板、端口、配置表单。
    """
    return NodeRegistry.get_schema_for_frontend()


@ruleChainRouter.get("/schema/connection-rules")
async def get_connection_rules():
    """
    返回数据类型兼容性矩阵, 供前端连线校验使用。
    """
    from nodes.base import ALLOWED_TYPE_MAPPING, CATEGORY_ALLOWED_INPUTS, NodeCategory

    return {
        "allowed_type_mapping": {
            src: list(targets) for src, targets in ALLOWED_TYPE_MAPPING.items()
        },
        "category_allowed_inputs": {
            cat.value: list(inputs) for cat, inputs in CATEGORY_ALLOWED_INPUTS.items()
        },
    }