"""知识库路由 — CRUD + 搜索 + 导入/导出"""

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime
import json
import uuid

from database.models import SessionLocal, KnowledgeBaseDB


knowledgeBaseRouter = APIRouter(
    prefix="/knowledge-base",
    tags=["knowledge-base"]
)


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class KnowledgeBaseCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category: str = "uncategorized"
    tags: list[str] = []
    chain_id: int = 1
    tx_hash: str
    attacked_address: Optional[str] = None
    exploiter_address: Optional[str] = None
    alert_data: dict[str, Any]
    expected_severity: Optional[str] = None
    expected_labels: list[str] = []
    expected_min_score: Optional[int] = None
    source: str = "manual"
    tx_explorer_url: Optional[str] = None


class KnowledgeBaseUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    chain_id: Optional[int] = None
    tx_hash: Optional[str] = None
    attacked_address: Optional[str] = None
    exploiter_address: Optional[str] = None
    alert_data: Optional[dict[str, Any]] = None
    expected_severity: Optional[str] = None
    expected_labels: Optional[list[str]] = None
    expected_min_score: Optional[int] = None
    source: Optional[str] = None
    tx_explorer_url: Optional[str] = None


class KnowledgeBaseResponse(BaseModel):
    id: str
    title: str
    description: Optional[str]
    category: str
    tags: list[str]
    chain_id: int
    tx_hash: str
    attacked_address: Optional[str]
    exploiter_address: Optional[str]
    alert_data: dict[str, Any]
    expected_severity: Optional[str]
    expected_labels: list[str]
    expected_min_score: Optional[int]
    source: str
    tx_explorer_url: Optional[str]
    created_at: datetime
    updated_at: datetime


class ImportRequest(BaseModel):
    samples: list[KnowledgeBaseCreate]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _auth(x_api_key: Optional[str] = None, api_key: Optional[str] = None):
    auth_key = x_api_key if x_api_key else api_key
    if not auth_key:
        raise HTTPException(status_code=401, detail="API key is required")


def _row_to_response(row: KnowledgeBaseDB) -> KnowledgeBaseResponse:
    return KnowledgeBaseResponse(
        id=row.id,
        title=row.title,
        description=row.description,
        category=row.category,
        tags=json.loads(row.tags) if isinstance(row.tags, str) else (row.tags or []),
        chain_id=row.chain_id,
        tx_hash=row.tx_hash,
        attacked_address=row.attacked_address,
        exploiter_address=row.exploiter_address,
        alert_data=json.loads(row.alert_data) if isinstance(row.alert_data, str) else row.alert_data,
        expected_severity=row.expected_severity,
        expected_labels=json.loads(row.expected_labels) if isinstance(row.expected_labels, str) else (row.expected_labels or []),
        expected_min_score=row.expected_min_score,
        source=row.source,
        tx_explorer_url=row.tx_explorer_url,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# ---------------------------------------------------------------------------
# CRUD Endpoints
# ---------------------------------------------------------------------------

@knowledgeBaseRouter.get("/", response_model=list[KnowledgeBaseResponse])
async def list_samples(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    chain_id: Optional[int] = None,
    search: Optional[str] = None,
    tag: Optional[str] = None,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,
):
    _auth(x_api_key, api_key)

    db = SessionLocal()
    try:
        query = db.query(KnowledgeBaseDB)

        if category:
            query = query.filter(KnowledgeBaseDB.category == category)
        if chain_id is not None:
            query = query.filter(KnowledgeBaseDB.chain_id == chain_id)
        if search:
            query = query.filter(KnowledgeBaseDB.title.ilike(f"%{search}%"))
        if tag:
            query = query.filter(KnowledgeBaseDB.tags.ilike(f"%{tag}%"))

        rows = query.order_by(KnowledgeBaseDB.updated_at.desc()).offset(skip).limit(limit).all()
        return [_row_to_response(r) for r in rows]
    finally:
        db.close()


@knowledgeBaseRouter.get("/{sample_id}", response_model=KnowledgeBaseResponse)
async def get_sample(
    sample_id: str,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,
):
    _auth(x_api_key, api_key)

    db = SessionLocal()
    try:
        row = db.query(KnowledgeBaseDB).filter(KnowledgeBaseDB.id == sample_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="Sample not found")
        return _row_to_response(row)
    finally:
        db.close()


@knowledgeBaseRouter.post("/", response_model=KnowledgeBaseResponse)
async def create_sample(
    data: KnowledgeBaseCreate,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,
):
    _auth(x_api_key, api_key)

    sample_id = str(uuid.uuid4())
    db = SessionLocal()
    try:
        row = KnowledgeBaseDB(
            id=sample_id,
            title=data.title,
            description=data.description,
            category=data.category,
            tags=json.dumps(data.tags),
            chain_id=data.chain_id,
            tx_hash=data.tx_hash,
            attacked_address=data.attacked_address,
            exploiter_address=data.exploiter_address,
            alert_data=json.dumps(data.alert_data),
            expected_severity=data.expected_severity,
            expected_labels=json.dumps(data.expected_labels),
            expected_min_score=data.expected_min_score,
            source=data.source,
            tx_explorer_url=data.tx_explorer_url,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return _row_to_response(row)
    finally:
        db.close()


@knowledgeBaseRouter.put("/{sample_id}", response_model=KnowledgeBaseResponse)
async def update_sample(
    sample_id: str,
    data: KnowledgeBaseUpdate,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,
):
    _auth(x_api_key, api_key)

    db = SessionLocal()
    try:
        row = db.query(KnowledgeBaseDB).filter(KnowledgeBaseDB.id == sample_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="Sample not found")

        update_fields = data.model_dump(exclude_unset=True)
        for field, value in update_fields.items():
            if field in ("tags", "expected_labels") and isinstance(value, list):
                value = json.dumps(value)
            if field == "alert_data" and isinstance(value, dict):
                value = json.dumps(value)
            setattr(row, field, value)

        row.updated_at = datetime.now()
        db.commit()
        db.refresh(row)
        return _row_to_response(row)
    finally:
        db.close()


@knowledgeBaseRouter.delete("/{sample_id}")
async def delete_sample(
    sample_id: str,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,
):
    _auth(x_api_key, api_key)

    db = SessionLocal()
    try:
        row = db.query(KnowledgeBaseDB).filter(KnowledgeBaseDB.id == sample_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="Sample not found")

        db.delete(row)
        db.commit()
        return {"status": "success", "message": "Sample deleted"}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Import / Export
# ---------------------------------------------------------------------------

@knowledgeBaseRouter.post("/import")
async def import_samples(
    data: ImportRequest,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,
):
    _auth(x_api_key, api_key)

    db = SessionLocal()
    try:
        created = []
        for sample in data.samples:
            row = KnowledgeBaseDB(
                id=str(uuid.uuid4()),
                title=sample.title,
                description=sample.description,
                category=sample.category,
                tags=json.dumps(sample.tags),
                chain_id=sample.chain_id,
                tx_hash=sample.tx_hash,
                attacked_address=sample.attacked_address,
                exploiter_address=sample.exploiter_address,
                alert_data=json.dumps(sample.alert_data),
                expected_severity=sample.expected_severity,
                expected_labels=json.dumps(sample.expected_labels),
                expected_min_score=sample.expected_min_score,
                source=sample.source or "import",
                tx_explorer_url=sample.tx_explorer_url,
            )
            db.add(row)
            created.append(row)

        db.commit()
        for r in created:
            db.refresh(r)

        return {
            "status": "success",
            "imported": len(created),
            "samples": [_row_to_response(r) for r in created],
        }
    finally:
        db.close()


@knowledgeBaseRouter.get("/export/all")
async def export_samples(
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,
):
    _auth(x_api_key, api_key)

    db = SessionLocal()
    try:
        rows = db.query(KnowledgeBaseDB).order_by(KnowledgeBaseDB.created_at.desc()).all()
        samples = [_row_to_response(r).model_dump() for r in rows]
        return {"total": len(samples), "samples": samples}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

@knowledgeBaseRouter.get("/meta/categories")
async def list_categories(
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,
):
    _auth(x_api_key, api_key)

    PRESET_CATEGORIES = [
        {"value": "flash_loan", "label": "闪电贷攻击"},
        {"value": "gas_manipulation", "label": "Gas 价格操纵"},
        {"value": "rug_pull", "label": "跑路 / Rug Pull"},
        {"value": "token_exploit", "label": "Token 合约漏洞利用"},
        {"value": "approval_phishing", "label": "授权钓鱼"},
        {"value": "address_spoofing", "label": "地址伪造"},
        {"value": "phishing", "label": "钓鱼攻击"},
        {"value": "mev", "label": "MEV / 三明治攻击"},
        {"value": "unknown", "label": "未分类"},
    ]

    db = SessionLocal()
    try:
        used = [
            r[0] for r in
            db.query(KnowledgeBaseDB.category).distinct().all()
            if r[0]
        ]
        return {"preset": PRESET_CATEGORIES, "used": used}
    finally:
        db.close()
