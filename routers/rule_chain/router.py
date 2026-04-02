from fastapi import APIRouter, Header, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid
import json

from database.models import SessionLocal, RuleChainDB


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