from fastapi import APIRouter, Header, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime
import uuid
import json
import time

from database.models import SessionLocal, RuleChainDB, KnowledgeBaseDB
from engine.parser import ChainParser
from engine.validator import ChainValidator
from engine.executor import ChainExecutor
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


# ── 单节点测试模型 ──

class TestNodeRequest(BaseModel):
    """单节点测试请求"""
    nodes: list                              # 完整的节点列表
    edges: list                              # 完整的边列表
    target_node_id: str                      # 要测试的目标节点 ID
    upstream_outputs: dict[str, Any] = {}   # 上游节点的缓存输出 {node_id: output_dict}
    alert_data: Optional[dict] = None        # 原始告警数据（Trigger 节点或无上游时使用）


class TestNodeResponse(BaseModel):
    """单节点测试响应"""
    success: bool
    node_id: str
    node_type: str
    label: str
    output: Optional[dict] = None           # 节点输出（NodeOutput 序列化）
    duration_ms: float = 0.0
    error: Optional[str] = None


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
    auth_key = x_api_key if x_api_key else api_key
    if not auth_key:
        raise HTTPException(status_code=401, detail="API key is required")

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

    raw_config = {"nodes": [dict(n) for n in data.nodes], "edges": [dict(e) for e in data.edges]}
    parsed_chain = ChainParser.parse(raw_config)

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
        executor = ChainExecutor()
        merged_for_resolver = {**ctx.alert_data}
        # 从第一个上游输出的 context 补充
        if inputs:
            for port_inputs in inputs.values():
                if port_inputs:
                    merged_for_resolver.update(port_inputs[0].context or {})
                    break
        extra_context = await executor._resolve_context(required_providers, merged_for_resolver)
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