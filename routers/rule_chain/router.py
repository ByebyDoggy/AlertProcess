from fastapi import APIRouter, Header, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid
import json

from database.models import SessionLocal, RuleChainDB
from rules.chain_engine import ChainParser, ChainExecutor, ChainConfig, ChainNode, ChainEdge
from detectors.base import DetectorRegistry


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
    target: str
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


class ValidateResponse(BaseModel):
    valid: bool
    errors: list[str] = []
    rule_tree: Optional[dict] = None


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
    验证规则链配置是否合法, 并返回规则树描述
    前端在保存前可先调用此接口做实时校验
    """
    chain_nodes = [ChainNode(**n) for n in data.nodes]
    chain_edges = [ChainEdge(**e) for e in data.edges]

    config = ChainConfig(name="_validate", nodes=chain_nodes, edges=chain_edges)
    parser = ChainParser(config)

    valid, errors = parser.validate()
    rule_tree = parser.to_rule_config() if valid else None

    return ValidateResponse(valid=valid, errors=errors, rule_tree=rule_tree)


@ruleChainRouter.get("/schema/node-types")
async def get_node_types():
    """返回前端可用的节点类型及配置 schema (无需认证, 检测器列表动态从注册表获取)"""
    detectors = DetectorRegistry.get_all_detector_info()

    detector_options = [
        {"value": d["type_key"], "label": d["description"]}
        for d in detectors
    ]

    return {
        "node_types": [
            {
                "label": "触发器",
                "icon": "⚡",
                "color": "yellow",
                "description": "规则链入口",
                "config_fields": []
            },
            {
                "type": "detector",
                "label": "检测器",
                "icon": "🛡️",
                "color": "green",
                "description": "执行安全检测",
                "config_fields": [
                    {
                        "key": "detectorType",
                        "label": "检测器类型",
                        "type": "select",
                        "options": detector_options
                    }
                ]
            },
            {
                "type": "condition",
                "label": "条件判断",
                "icon": "🔍",
                "color": "blue",
                "description": "根据条件分支",
                "config_fields": [
                    {"key": "field", "label": "条件字段", "type": "text", "placeholder": "detector.flash_loan_detector"},
                    {"key": "operator", "label": "操作符", "type": "select",
                     "options": [
                        {"value": "equals", "label": "等于"},
                        {"value": "not_equals", "label": "不等于"},
                        {"value": "contains", "label": "包含"},
                        {"value": "greater_than", "label": "大于"},
                        {"value": "less_than", "label": "小于"},
                    ]},
                    {"key": "value", "label": "比较值", "type": "text"}
                ]
            },
            {
                "type": "filter",
                "label": "过滤器",
                "icon": "🔽",
                "color": "orange",
                "description": "过滤不符合条件的告警",
                "config_fields": [
                    {"key": "expression", "label": "过滤条件", "type": "text",
                     "placeholder": "detector.flash_loan_detector"}
                ]
            },
            {
                "type": "action",
                "label": "执行动作",
                "icon": "⚙️",
                "color": "purple",
                "description": "设置属性或标记",
                "config_fields": [
                    {"key": "actionType", "label": "操作类型", "type": "select",
                     "options": [
                        {"value": "set_severity", "label": "设置严重级别"},
                        {"value": "set_score", "label": "设置风险评分"},
                        {"value": "add_tag", "label": "添加标签"},
                    ]},
                    {"key": "actionValue", "label": "参数值", "type": "text",
                     "placeholder": "CRITICAL / 80 / suspicious"}
                ]
            },
            {
                "type": "scorer",
                "label": "评分",
                "icon": "📊",
                "color": "cyan",
                "description": "计算风险评分",
                "config_fields": [
                    {"key": "severity_weight", "label": "严重程度权重", "type": "number", "default": 1},
                    {"key": "detector_weight", "label": "检测器权重", "type": "number", "default": 1},
                ]
            },
            {
                "type": "notifier",
                "label": "通知",
                "icon": "📢",
                "color": "red",
                "description": "发送告警通知",
                "config_fields": [
                    {"key": "notifierType", "label": "通知类型", "type": "select",
                     "options": [
                        {"value": "webhook", "label": "Webhook"},
                        {"value": "telegram", "label": "Telegram"},
                    ]},
                    {"key": "targetUrl", "label": "目标地址", "type": "text",
                     "placeholder": "https://example.com/webhook"}
                ]
            },
        ]
    }


@ruleChainRouter.get("/schema/detectors")
async def get_detectors():
    """
    获取所有已注册检测器的详细信息, 包括配置参数 schema 和默认值。
    前端可在用户选择检测器节点时调用此接口, 动态渲染对应的配置表单。
    """
    detectors = DetectorRegistry.get_all_detector_info()
    return {
        "detectors": detectors,
        "type_map": DetectorRegistry.build_detector_type_map(),
    }