from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Any, Literal
from datetime import datetime
import uuid
import json
import time
import logging

from database.models import SessionLocal, RuleChainDB, KnowledgeBaseDB
from engine.parser import ChainParser
from engine.validator import ChainValidator
from engine.executor import ChainExecutor
from nodes.base import (
    ALLOWED_TYPE_MAPPING,
    CATEGORY_ALLOWED_INPUTS,
    NodeCategory,
    NodeRegistry,
)


ruleChainRouter = APIRouter(
    prefix="/rule-chain",
    tags=["rule-chain"]
)
logger = logging.getLogger(__name__)


class RuleNode(BaseModel):
    id: str
    type: str
    label: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    position: dict[str, Any] = Field(default_factory=lambda: {"x": 0, "y": 0})


class RuleEdge(BaseModel):
    id: str = ""
    source: str
    source_port: str = Field(default="output", alias="sourcePort")
    target: str
    target_port: str = Field(default="input", alias="targetPort")
    label: str = ""
    input_transformer: Optional[dict[str, Any]] = Field(default=None, alias="inputTransformer")

    model_config = {"populate_by_name": True}


class RuleChainCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    enabled: bool = True
    nodes: list[RuleNode] = Field(default_factory=list)
    edges: list[RuleEdge] = Field(default_factory=list)


class RuleChainUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    nodes: Optional[list[RuleNode]] = None
    edges: Optional[list[RuleEdge]] = None


class RuleChainResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    enabled: bool
    chain_config: dict
    created_at: datetime
    updated_at: datetime


class ValidateRequest(BaseModel):
    nodes: list[RuleNode]
    edges: list[RuleEdge] = Field(default_factory=list)


class ValidateError(BaseModel):
    type: Literal["error", "warning"] = "error"
    code: str
    severity: Literal["error", "warning"] = "error"
    field: str = ""
    field_path: str = ""
    message: str
    node_id: Optional[str] = None
    edge_id: Optional[str] = None
    suggestion: Optional[str] = None


class ValidateResponse(BaseModel):
    valid: bool
    errors: list[ValidateError] = Field(default_factory=list)
    warnings: list[ValidateError] = Field(default_factory=list)
    normalized_config: Optional[dict[str, Any]] = None
    stats: Optional[dict[str, Any]] = None


# ── 单节点测试模型 ──

class TestNodeRequest(BaseModel):
    nodes: list[RuleNode]
    edges: list[RuleEdge] = Field(default_factory=list)
    target_node_id: str
    upstream_outputs: dict[str, Any] = Field(default_factory=dict)
    alert_data: Optional[dict[str, Any]] = None


class TestNodeResponse(BaseModel):
    success: bool
    node_id: str
    node_type: str
    label: str
    output: Optional[dict[str, Any]] = None
    duration_ms: float = 0.0
    error: Optional[str] = None


class AIRuleChainGenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    mode: Literal["new", "replace", "append", "modify"] = "new"
    current_chain: dict[str, Any] = Field(default_factory=lambda: {"nodes": [], "edges": []})
    constraints: dict[str, Any] = Field(default_factory=dict)


class AIRuleChainError(BaseModel):
    code: str
    message: str
    suggestion: Optional[str] = None


class AIRuleChainGenerateResponse(BaseModel):
    success: bool
    draft: Optional[dict[str, Any]] = None
    validation: Optional[dict[str, Any]] = None
    explanation: str = ""
    assumptions: list[str] = Field(default_factory=list)
    generation_meta: dict[str, Any] = Field(default_factory=dict)
    error: Optional[AIRuleChainError] = None
    raw_model_output: Optional[str] = None


def get_db():
    db = SessionLocal()
    try:
        return db
    finally:
        pass


def _auth_with_key(x_api_key: Optional[str], api_key: Optional[str]) -> None:
    from config import settings

    auth_key = x_api_key if x_api_key else api_key
    if not auth_key or auth_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


def _node_to_storage(node: RuleNode) -> dict[str, Any]:
    return node.model_dump(by_alias=True, exclude_none=True)


def _edge_to_storage(edge: RuleEdge) -> dict[str, Any]:
    return edge.model_dump(by_alias=True, exclude_none=True)


def build_chain_config(nodes: list[RuleNode], edges: list[RuleEdge]) -> dict[str, Any]:
    return {
        "nodes": [_node_to_storage(node) for node in nodes],
        "edges": [_edge_to_storage(edge) for edge in edges],
    }


def _parse_chain_payload(nodes: list[RuleNode], edges: list[RuleEdge]):
    normalized_config = build_chain_config(nodes, edges)
    return normalized_config, ChainParser.parse(normalized_config)


def _validate_error_code(field: str, message: str) -> str:
    if field == "topology" and "node type" in message.lower():
        return "UNKNOWN_NODE_TYPE"
    if field == "topology" and ("未知节点类型" in message or "δ֪" in message):
        return "UNKNOWN_NODE_TYPE"
    if field:
        return field.upper()
    return "VALIDATION"


def _validate_field_path(error) -> str:
    if error.node_id:
        return f"nodes.{error.node_id}.{error.field or 'validation'}"
    if error.edge_id:
        return f"edges.{error.edge_id}.{error.field or 'validation'}"
    return error.field or "chain"


def _suggest_fix(error) -> str | None:
    if error.field == "topology" and "未知节点类型" in error.message:
        return "调用 /rule-chain/schema/mcp 获取可用 node_type 后替换。"
    if error.field == "port":
        return "检查 sourcePort/targetPort 是否存在于对应节点 schema 的 outputs/inputs。"
    if error.field == "data_type":
        return "调用 /rule-chain/schema/connection-rules 检查端口 data_type 是否兼容。"
    if error.field == "config":
        return "按节点 config_schema 修正 config 字段。"
    if error.field == "structure":
        return "确保规则链包含且只包含一个 input 节点，并且所有必要节点从 trigger 可达。"
    return None


def _to_validate_error(error) -> ValidateError:
    severity = "warning" if error.level == "warning" else "error"
    return ValidateError(
        type=severity,
        severity=severity,
        code=_validate_error_code(error.field, error.message),
        field=error.field,
        field_path=_validate_field_path(error),
        message=error.message,
        node_id=error.node_id,
        edge_id=error.edge_id,
        suggestion=_suggest_fix(error),
    )


def _get_connection_rules() -> dict[str, Any]:
    return {
        "allowed_type_mapping": {
            src: sorted(targets) for src, targets in ALLOWED_TYPE_MAPPING.items()
        },
        "category_allowed_inputs": {
            cat.value: sorted(inputs) for cat, inputs in CATEGORY_ALLOWED_INPUTS.items()
        },
    }


def _get_mcp_schema_bundle() -> dict[str, Any]:
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



@ruleChainRouter.get("/", response_model=list[RuleChainResponse])
async def list_rule_chains(
        x_api_key: Optional[str] = Header(None),
        api_key: Optional[str] = None
):
    _auth_with_key(x_api_key, api_key)

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
    _auth_with_key(x_api_key, api_key)

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
    _auth_with_key(x_api_key, api_key)

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
    _auth_with_key(x_api_key, api_key)

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
            nodes = [RuleNode.model_validate(node) for node in existing_config.get("nodes", [])]
            edges = [RuleEdge.model_validate(edge) for edge in existing_config.get("edges", [])]
            if chain_data.nodes is not None:
                nodes = chain_data.nodes
            if chain_data.edges is not None:
                edges = chain_data.edges
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
    _auth_with_key(x_api_key, api_key)

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


# ──────────────── 测试运行端点 ────────────────

class TestRunRequest(BaseModel):
    sample_ids: list[str] = []
    alert_data: Optional[dict[str, Any]] = None


class TestRunResultItem(BaseModel):
    sample_id: Optional[str] = None
    sample_title: Optional[str] = None
    chain_id: str
    chain_name: str
    success: bool
    final_score: float = 0.0
    final_severity: str = "UNKNOWN"
    labels: list[str] = []
    actions_executed: list[dict] = []
    node_results: list[dict] = []
    errors: list[str] = []
    duration_ms: float = 0.0
    expected_matched: Optional[bool] = None
    expected_details: Optional[dict] = None


def _check_expectations(ctx, sample: KnowledgeBaseDB | None) -> tuple[bool, dict]:
    """对比执行结果与预期结果"""
    if sample is None:
        return None, None

    severity_order = {"UNKNOWN": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

    details: dict[str, bool | str] = {}

    # 严重级别匹配
    severity_match = True
    if sample.expected_severity:
        expected_order = severity_order.get(sample.expected_severity, 0)
        actual_order = severity_order.get(ctx.final_severity, 0)
        severity_match = actual_order >= expected_order
        details["severity"] = f"expected>={sample.expected_severity}, got={ctx.final_severity}"

    # 标签匹配
    labels_match = True
    expected_labels = json.loads(sample.expected_labels) if isinstance(sample.expected_labels, str) else (sample.expected_labels or [])
    if expected_labels:
        missing = [l for l in expected_labels if l not in ctx.collected_labels]
        labels_match = len(missing) == 0
        details["labels"] = f"expected={expected_labels}, got={ctx.collected_labels}, missing={missing}"

    # 最低评分匹配
    score_match = True
    if sample.expected_min_score is not None:
        score_match = ctx.final_score >= sample.expected_min_score
        details["score"] = f"expected>={sample.expected_min_score}, got={ctx.final_score}"

    matched = severity_match and labels_match and score_match
    return matched, details


@ruleChainRouter.post("/{chain_id}/test-run")
async def test_run_chain(
    chain_id: str,
    body: TestRunRequest,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,
):
    """
    用知识库样本或自定义数据测试运行规则链（dry-run 模式）。
    Action 节点仅模拟执行，不会产生实际副作用。
    """
    _auth_with_key(x_api_key, api_key)

    db = SessionLocal()
    try:
        chain = db.query(RuleChainDB).filter(RuleChainDB.id == chain_id).first()
        if not chain:
            raise HTTPException(status_code=404, detail="Rule chain not found")

        chain_config = json.loads(chain.chain_config) if isinstance(chain.chain_config, str) else chain.chain_config
        parsed_chain = ChainParser.parse(chain_config)

        # 准备测试数据
        test_cases: list[tuple[str | None, str | None, dict]] = []

        if body.alert_data:
            test_cases.append((None, None, body.alert_data))
        elif body.sample_ids:
            samples = db.query(KnowledgeBaseDB).filter(
                KnowledgeBaseDB.id.in_(body.sample_ids)
            ).all()
            for s in samples:
                alert_data = json.loads(s.alert_data) if isinstance(s.alert_data, str) else s.alert_data
                test_cases.append((s.id, s.title, alert_data))
        else:
            raise HTTPException(status_code=400, detail="Provide sample_ids or alert_data")

        # 逐个执行
        executor = ChainExecutor()
        results = []

        for sample_id, sample_title, alert_data in test_cases:
            # 加载关联的知识库样本（用于预期比对）
            sample = None
            if sample_id:
                sample = db.query(KnowledgeBaseDB).filter(KnowledgeBaseDB.id == sample_id).first()

            start_time = time.monotonic()
            ctx = await executor.execute(parsed_chain, alert_data, dry_run=True)
            duration_ms = (time.monotonic() - start_time) * 1000

            # 清理 alert_data 中的 dry_run 标记（避免污染输出）
            alert_data_clean = {k: v for k, v in alert_data.items() if k != "__dry_run__"}

            expected_matched, expected_details = _check_expectations(ctx, sample)

            node_results = []
            for log in ctx.logs:
                node_def = parsed_chain.get_node(log.node_id)
                node_results.append({
                    "node_id": log.node_id,
                    "node_type": log.node_type,
                    "label": node_def.node_type if node_def else log.node_type,
                    "score": log.score,
                    "passed": log.passed,
                    "duration_ms": round(log.duration_ms, 2),
                    "error": log.error,
                })

            results.append(TestRunResultItem(
                sample_id=sample_id,
                sample_title=sample_title,
                chain_id=chain_id,
                chain_name=chain.name,
                success=ctx.get_success(),
                final_score=ctx.final_score,
                final_severity=ctx.final_severity,
                labels=ctx.collected_labels,
                actions_executed=ctx.actions_executed,
                node_results=node_results,
                errors=ctx.errors,
                duration_ms=round(duration_ms, 2),
                expected_matched=expected_matched,
                expected_details=expected_details,
            ))

        return {"results": [r.model_dump() for r in results]}
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
        error = ValidateError(
            type="error",
            severity="error",
            code="EMPTY_CHAIN",
            field="nodes",
            field_path="nodes",
            message="规则链至少需要一个节点",
            suggestion="添加一个 input 类节点作为规则链入口。",
        )
        return ValidateResponse(valid=False, errors=[error], normalized_config={"nodes": [], "edges": []})

    normalized_config, parsed_chain = _parse_chain_payload(data.nodes, data.edges)
    validation_errors = ChainValidator().validate(parsed_chain)

    for validation_error in validation_errors:
        target = errors if validation_error.level == "error" else warnings
        target.append(_to_validate_error(validation_error))

    trigger_count = sum(
        1 for node in parsed_chain.nodes
        if NodeRegistry.get(node.node_type)
        and NodeRegistry.get(node.node_type).category == NodeCategory.INPUT
    )

    stats = {
        "node_count": len(data.nodes),
        "edge_count": len(data.edges),
        "trigger_count": trigger_count,
        "error_count": len(errors),
        "warning_count": len(warnings),
    }

    return ValidateResponse(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        normalized_config=normalized_config,
        stats=stats,
    )


# ──────────────── 单节点测试端点 ────────────────

@ruleChainRouter.post("/test-node", response_model=TestNodeResponse)
async def test_single_node(data: TestNodeRequest):
    """
    测试执行规则链中的单个节点（n8n 式逐节点调试）。

    支持两种输入模式:
    1. 上游输出: upstream_outputs 中包含上游节点的缓存结果
    2. 原始数据: 无上游时使用 alert_data 作为输入
    """
    from engine.context import ExecutionContext, ExecutionLogEntry

    raw_config, parsed_chain = _parse_chain_payload(data.nodes, data.edges)

    target_node = parsed_chain.get_node(data.target_node_id)
    if not target_node:
        return TestNodeResponse(
            success=False,
            node_id=data.target_node_id,
            node_type="",
            label="",
            error=f"节点 '{data.target_node_id}' 未找到",
        )

    # 实例化目标节点
    try:
        node = NodeRegistry.create(
            target_node.node_type,
            node_id=target_node.node_id,
            config=target_node.config,
        )
    except ValueError as e:
        return TestNodeResponse(
            success=False,
            node_id=data.target_node_id,
            node_type=target_node.node_type,
            label=target_node.label or target_node.node_type,
            error=f"实例化失败: {e}",
        )

    # 构建执行上下文，预填上游输出
    ctx = ExecutionContext(alert_data=data.alert_data or {}, dry_run=True)

    # 将上游缓存的 NodeOutput 恢复到 ctx.node_outputs
    for nid, out_dict in data.upstream_outputs.items():
        if isinstance(out_dict, dict):
            from nodes.base import NodeOutput
            # 兼容前端传入的序列化 NodeOutput
            try:
                restored = NodeOutput(**out_dict)
                ctx.set_output(nid, restored)
            except Exception:
                pass

    # 收集上游输入（应用 input_transformer）
    incoming_edges = parsed_chain.get_incoming_edges(data.target_node_id)
    inputs: dict[str, list] = {}
    executor_for_transformer = ChainExecutor()
    for edge in incoming_edges:
        src_output = ctx.get_output(edge.source_id)
        if src_output is not None:
            transformed = executor_for_transformer._apply_transformer(
                src_output, edge.input_transformer
            )
            inputs.setdefault(edge.target_port, []).append(transformed)

    # 如果无上游输出且提供了 alert_data，直接用它作为上下文
    if not inputs and data.alert_data:
        ctx.alert_data = data.alert_data

    # @require 上下文注入
    required_providers = node.get_required_providers()
    if required_providers:
        from nodes.context.resolver import get_context_resolver
        resolver = get_context_resolver()
        merged_for_resolver = {**ctx.alert_data}
        # 从第一个上游输出的 context 补充
        if inputs:
            for port_inputs in inputs.values():
                if port_inputs:
                    merged_for_resolver.update(port_inputs[0].context or {})
                    break
        extra_context = await resolver.resolve(list(required_providers), merged_for_resolver)
        if extra_context:
            ctx.alert_data.update(extra_context)

    # 执行节点
    import time as _time
    start_time = _time.monotonic()
    try:
        output = await node.execute(ctx.alert_data, inputs)
        duration_ms = (_time.monotonic() - start_time) * 1000

        # 记录到 context
        ctx.set_output(data.target_node_id, output)

        # 统一检查：提取错误信息到 error 字段，避免前端多处判断
        error_msg = _extract_node_error(output)

        return TestNodeResponse(
            success=error_msg is None,
            node_id=data.target_node_id,
            node_type=target_node.node_type,
            label=target_node.label or target_node.node_type,
            output=output.model_dump(),
            duration_ms=round(duration_ms, 2),
            error=error_msg,
        )
    except Exception as e:
        duration_ms = (_time.monotonic() - start_time) * 1000
        return TestNodeResponse(
            success=False,
            node_id=data.target_node_id,
            node_type=target_node.node_type,
            label=target_node.label or target_node.node_type,
            duration_ms=round(duration_ms, 2),
            error=f"执行异常: {e}",
        )


def _extract_node_error(output) -> str | None:
    """
    从 NodeOutput 中统一提取错误信息。

    检查优先级:
    1. passed == False → 提取原因
    2. context 中含 _xxx_error 键 → 提取具体报错
    3. detection.details 含 error 键 → 提取
    """
    parts = []

    # 1. 业务未通过
    if output.passed is False:
        ctx = output.context or {}
        det = ctx.get("detection", {})

        # detection 中的 reason/error 信息
        if isinstance(det, dict):
            reason = det.get("reason")
            if reason:
                parts.append(reason)
            elif det.get("error"):
                parts.append(det["error"])

        # 如果没从 detection 取到有用信息，补充 score 说明
        if not parts:
            parts.append(f"未通过阈值 (score={output.score})")

    # 2. context 中的 _xxx_error 键（如 _moralis_address_error）
    if output.context:
        for key, val in output.context.items():
            if key.endswith("_error") and val and key != "detection":
                label = key.lstrip("_").removesuffix("_error")
                parts.append(f"{label}: {val}")

    return "\n".join(parts) if parts else None


@ruleChainRouter.get("/schema/node-types")
async def get_node_types_alias():
    """返回前端可用的节点类型及配置 schema (无需认证，兼容旧入口)"""
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


@ruleChainRouter.get("/schema/nodes-docs")
async def get_node_docs():
    """
    返回所有节点的详细文档信息（含 required_providers / provides / config_schema_raw 等）。
    供前端文档页面动态渲染，新增节点自动出现。
    """
    return NodeRegistry.get_docs_for_frontend()


@ruleChainRouter.get("/schema/connection-rules")
async def get_connection_rules():
    """
    返回数据类型兼容性矩阵, 供前端连线校验使用。
    """
    return _get_connection_rules()


@ruleChainRouter.get("/schema/mcp")
async def get_mcp_schema():
    """
    返回 AI/MCP 构造规则链所需的最小稳定 schema 包。
    """
    try:
        return JSONResponse(content=_get_mcp_schema_bundle())
    except Exception as e:
        logger.exception("[rule-chain] Failed to build MCP schema bundle")
        raise HTTPException(status_code=500, detail=f"Failed to build MCP schema bundle: {e}") from e


@ruleChainRouter.post("/ai/generate", response_model=AIRuleChainGenerateResponse)
async def generate_rule_chain_with_ai(
    data: AIRuleChainGenerateRequest,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,
):
    _auth_with_key(x_api_key, api_key)
    from services.ai.client import AIClientError
    from services.ai.rule_chain_generator import RuleChainGenerationError, generate_rule_chain_draft

    try:
        result = await generate_rule_chain_draft(
            prompt=data.prompt,
            mode=data.mode,
            current_chain=data.current_chain,
            constraints=data.constraints,
            schema_bundle=_get_mcp_schema_bundle(),
        )
        return AIRuleChainGenerateResponse(success=True, **result)
    except AIClientError as e:
        return AIRuleChainGenerateResponse(
            success=False,
            error=AIRuleChainError(code=e.code, message=e.message, suggestion="请检查系统 AI 配置后重试。"),
        )
    except RuleChainGenerationError as e:
        return AIRuleChainGenerateResponse(
            success=False,
            error=AIRuleChainError(code=e.code, message=e.message, suggestion=e.suggestion),
        )
    except Exception as e:
        logger.exception("[rule-chain] Unexpected AI generation failure")
        return AIRuleChainGenerateResponse(
            success=False,
            error=AIRuleChainError(
                code="RULE_CHAIN_GENERATION_FAILED",
                message=str(e),
                suggestion="请检查规则链 schema、节点注册表和 AI 服务状态后重试。",
            ),
        )


# ──────────────── 输入转换器 (Input Transformer) 端点 ────────────────

class TransformerValidateRequest(BaseModel):
    expression: str
    language: str = "python"  # python | javascript


class TransformerValidateResponse(BaseModel):
    valid: bool
    error: Optional[str] = None
    translated: Optional[str] = None  # JS 翻译后的 Python 表达式


class TransformerPreviewRequest(BaseModel):
    expression: str
    language: str = "python"
    sample_input: dict[str, Any] = {}


class TransformerPreviewResponse(BaseModel):
    success: bool
    output: Optional[dict] = None
    error: Optional[str] = None
    translated: Optional[str] = None


@ruleChainRouter.post("/transformer/validate", response_model=TransformerValidateResponse)
async def validate_transformer(data: TransformerValidateRequest):
    """
    校验输入转换表达式语法（不执行）。

    对于 JS 表达式，还会返回翻译后的 Python 等价形式。
    """
    from engine.transformer import InputTransformer

    result = InputTransformer.validate(data.expression, data.language)
    translated = None
    if data.language == "javascript" and data.expression.strip():
        try:
            translated = InputTransformer._translate_js_to_python(data.expression.strip())
        except Exception:
            pass

    return TransformerValidateResponse(
        valid=result["valid"],
        error=result.get("error"),
        translated=translated,
    )


@ruleChainRouter.post("/transformer/preview", response_model=TransformerPreviewResponse)
async def preview_transformer(data: TransformerPreviewRequest):
    """
    预览输入转换表达式的执行结果。

    使用示例输入数据执行表达式，返回变换后的输出。
    用于前端实时预览。
    """
    from engine.transformer import InputTransformer

    result = InputTransformer.preview(
        data.expression,
        data.language,
        data.sample_input,
    )
    translated = None
    if data.language == "javascript" and data.expression.strip():
        try:
            translated = InputTransformer._translate_js_to_python(data.expression.strip())
        except Exception:
            pass

    return TransformerPreviewResponse(
        success=result["success"],
        output=result.get("output"),
        error=result.get("error"),
        translated=translated,
    )