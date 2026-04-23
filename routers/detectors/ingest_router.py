"""
Ingest Router — 接收 EVMLogListener 推送的增量日志
================================================
端点:
  POST /ingest/logs          — 接收增量 Event Logs
  POST /ingest/logs/replay   — 断线补传历史日志
  GET  /ingest/status        — 查询消费进度
  GET  /ingest/alerts/recent — 最近匹配的告警
  GET  /ingest/rules/stats   — 规则链运行统计

数据流:
  EVMLogListener → [POST logs] → IngestRouter
    → 从 DB 加载启用的规则链 → ChainExecutor 执行 → MatchedAlert

注意: 规则检测完全由前端配置的 DAG 规则链驱动，
      不再使用任何硬编码检测逻辑。
"""

import json
import logging
import time
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from detectors.trace.rule_engine import IngestedLog, TxLogsGroup, MatchedAlert  # noqa: F401 — 兼容保留
from engine.executor import ChainExecutor

# 统一模型（新代码使用）
from models.ingest import EventLog as _EventLog
from models.ingest import TxLogsGroup as _UnifiedTxGroup
from models.ingest import AlertData as _AlertData

logger = logging.getLogger(__name__)

ingest_router = APIRouter(prefix="/ingest", tags=["log-ingest"])


# ================================================================
# 内存状态追踪（生产环境应替换为持久化存储）
# ================================================================

class _IngestState:
    """消费进度追踪"""

    def __init__(self):
        self._last_block: dict[int, int] = {}       # chain_id -> 已处理到的最大区块
        self._total_logs_received: dict[int, int] = defaultdict(int)
        self._total_matched_alerts: dict[int, int] = defaultdict(int)
        self._recent_alerts: list[MatchedAlert] = []  # 最近 200 条告警
        self._max_recent_alerts = 200
        # 规则链统计
        self._evaluated_txs: int = 0
        self._by_rule: dict[str, int] = defaultdict(int)

    def update_block(self, chain_id: int, to_block: int):
        current = self._last_block.get(chain_id, 0)
        if to_block > current:
            self._last_block[chain_id] = to_block

    def add_stats(self, chain_id: int, log_count: int, alert_count: int):
        self._total_logs_received[chain_id] += log_count
        self._total_matched_alerts[chain_id] += alert_count

    def add_alert(self, alert: MatchedAlert):
        self._recent_alerts.append(alert)
        if len(self._recent_alerts) > self._max_recent_alerts:
            self._recent_alerts.pop(0)

    @property
    def recent_alerts(self) -> list[MatchedAlert]:
        return list(self._recent_alerts)

    def status_dict(self) -> dict:
        chains_status = {}
        for cid in sorted(self._last_block.keys()):
            chains_status[str(cid)] = {
                "last_block": self._last_block[cid],
                "total_logs_received": self._total_logs_received[cid],
                "total_matched_alerts": self._total_matched_alerts[cid],
            }
        return chains_status


# 全局状态实例
_state = _IngestState()


# ================================================================
# Request/Response 模型
# ================================================================

class LogObject(BaseModel):
    """单条 Event Log — 与 EVMLISTENER_INPUT_SPEC 一致"""
    address: str = Field(..., description="合约地址")
    topics: list[str] = Field(default_factory=list, description="事件主题数组")
    data: str = Field(default="0x", description="事件编码数据 (hex)")
    block_number: int = Field(..., ge=0, description="区块号 (integer)")
    transaction_hash: str = Field(..., min_length=66, max_length=66, description="交易 hash")
    log_index: int = Field(..., ge=0, description="在交易内的日志序号")
    transaction_index: int = Field(Field(0), ge=0, description="交易在区块中的索引")
    block_hash: str = Field(default="", description="区块哈希")
    removed: bool = Field(default=False, description="是否因链重组移除")


class IngestLogsRequest(BaseModel):
    """增量日志推送请求体"""
    chain_id: int = Field(..., ge=1, description="链 ID")
    chain_name: str = Field(default="", description="链名称")
    logs: list[LogObject] = Field(..., min_length=1, max_length=5000, description="增量日志列表")
    from_block: int = Field(..., ge=0, description="本批次起始区块号")
    to_block: int = Field(..., ge=0, description="本批次结束区块号")
    log_count: int = Field(default=0, ge=0, description="logs 数组长度 (用于校验)")
    pushed_at: str = Field(default="", description="EVMLogListener 推送时间戳")

    @field_validator("logs", mode="before")
    @classmethod
    def ensure_list(cls, v):
        if v is None:
            return []
        return v


class ReplayLogsRequest(BaseModel):
    """断线补传请求体"""
    chain_id: int = Field(..., ge=1, description="链 ID")
    from_block: int = Field(..., ge=0, description="补传起始区块")
    to_block: int = Field(..., ge=0, description="补传结束区块")
    reason: str = Field(default="reconnection_gap", description="补传原因")
    logs: list[LogObject] = Field(..., min_length=1)


class IngestResponse(BaseModel):
    """接收响应"""
    status: str = "accepted"
    received_log_count: int = 0
    from_block: int = 0
    to_block: int = 0
    matched_alert_count: int = 0
    processed_at: str = ""
    next_push_after_seconds: int = 5
    active_chain_count: int = 0   # 当前使用的规则链数量


class StatusResponse(BaseModel):
    """状态查询响应"""
    is_connected: bool = True
    last_received_at: str = ""
    consumed_blocks: dict[str, dict] = {}


# ================================================================
# 规则链管理器（从数据库加载 + 缓存）
# ================================================================

class _ChainManager:
    """
    管理启用的规则链，支持热更新。

    启动时和收到请求时检查数据库中的启用规则链，
    有变化则重新解析缓存。
    """

    def __init__(self):
        self._chains: list[tuple[str, str, object]] = []  # (id, name, ParsedChain)
        self._loaded_at: float = 0.0
        self._cache_ttl: float = 30.0  # 秒，定期刷新以获取前端最新配置
        self._executor = None           # 延迟初始化 ChainExecutor

    @property
    def executor(self):
        if self._executor is None:
            self._executor = ChainExecutor()
        return self._executor

    async def get_active_chains(self) -> list[tuple[str, str, object]]:
        """获取当前启用的规则链 [(chain_id, chain_name, ParsedChain)]"""
        now = time.time()
        if self._chains and (now - self._loaded_at) < self._cache_ttl:
            return self._chains

        from database.models import SessionLocal, RuleChainDB
        db = SessionLocal()
        try:
            rows = (
                db.query(RuleChainDB)
                .filter(RuleChainDB.enabled == 1)
                .order_by(RuleChainDB.updated_at.desc())
                .all()
            )
            chains = []
            for row in rows:
                try:
                    config = (
                        json.loads(row.chain_config)
                        if isinstance(row.chain_config, str)
                        else row.chain_config
                    )
                    if not config.get("nodes"):
                        continue
                    from engine.parser import ChainParser
                    parsed = ChainParser.parse(config)
                    chains.append((row.id, row.name, parsed))
                except Exception as e:
                    logger.warning(f"[ingest] Failed to parse rule chain '{row.name}': {e}")
                    continue

            self._chains = chains
            self._loaded_at = now
            logger.info(
                f"[ingest] Loaded {len(chains)} active rule chains from DB"
            )
            return chains
        finally:
            db.close()

    def invalidate_cache(self):
        """强制下次请求重新加载"""
        self._loaded_at = 0.0

    @property
    def active_chain_count(self) -> int:
        return len(self._chains)


_chain_manager = _ChainManager()


def _build_alert_data(group: TxLogsGroup, *, chain_name: str = "") -> dict:
    """
    将 TxLogsGroup 转换为 alert_data 字典格式。

    现在委托给统一模型 AlertData.from_tx_group()，
    保证实时处理与回测/测试使用完全一致的数据格式。

    Args:
        group: 兼容层 TxLogsGroup (dataclass)
        chain_name: 链名称（从请求体传入，补充到 alert_data 中）
    """
    # 将兼容层 IngestedLog 列表转换为统一 EventLog 列表
    unified_logs = [
        _EventLog(
            address=log.address,
            topics=log.topics,
            data=log.data,
            block_number=log.block_number,
            transaction_hash=log.transaction_hash,
            log_index=log.log_index,
            transaction_index=log.transaction_index,
            block_hash=log.block_hash,
            removed=log.removed,
        )
        for log in group.logs
    ]

    # 构建统一的 TxLogsGroup (Pydantic)
    unified_group = _UnifiedTxGroup.from_event_logs(
        event_logs=unified_logs,
        tx_hash=group.tx_hash,
        chain_id=group.chain_id,
        chain_name=chain_name or "",
        block_number=group.block_number,
    )

    # 通过统一 builder 生成 alert_data，返回 .model_dump() 保持裸字典接口不变
    return _AlertData.from_tx_group(unified_group).model_dump()


async def _evaluate_group_with_chains(
    group: TxLogsGroup,
    chain_name: str = "",
) -> Optional[MatchedAlert]:
    """
    用所有启用的规则链评估一个 TxLogsGroup。

    Returns:
        MatchedAlert 如果有任一规则链判定为可疑，否则 None。
    """
    from engine.context import ExecutionContext

    chains = await _chain_manager.get_active_chains()

    if not chains:
        return None

    alert_data = _build_alert_data(group, chain_name=chain_name)

    best_score = 0.0
    best_severity = "UNKNOWN"
    best_labels: list[str] = []
    best_results: list[dict] = []
    any_matched = False

    executor = _chain_manager.executor

    for chain_id, chain_name, parsed_chain in chains:
        try:
            ctx = await executor.execute(parsed_chain, alert_data)

            # 收集结果
            node_results = []
            for log_entry in ctx.logs:
                node_def = parsed_chain.get_node(log_entry.node_id)
                node_results.append({
                    "node_id": log_entry.node_id,
                    "node_type": log_entry.node_type,
                    "label": node_def.node_type if node_def else log_entry.node_type,
                    "score": log_entry.score,
                    "passed": log_entry.passed,
                    "duration_ms": round(log_entry.duration_ms, 2),
                    "severity": log_entry.severity if hasattr(log_entry, 'severity') else "UNKNOWN",
                })

            # 判断是否命中：最终 score > 0 或有 action 执行
            is_match = ctx.final_score > 0 or ctx.actions_executed

            if is_match:
                any_matched = True
                if ctx.final_score > best_score:
                    best_score = ctx.final_score
                    best_severity = ctx.final_severity
                    best_labels = ctx.collected_labels[:]
                    best_results = node_results

            # 统计各规则链命中情况
            if ctx.final_score > 0:
                _state._by_rule[chain_name] += 1

        except Exception as e:
            logger.warning(f"[ingest] Rule chain '{chain_name}' execution error: {e}")

    if not any_matched:
        return None

    _state._evaluated_txs += 1

    return MatchedAlert(
        tx_hash=group.tx_hash,
        chain_id=group.chain_id,
        block_number=group.block_number,
        trigger_log_count=group.log_count,
        detected_at=time.time(),
        final_score=best_score,
        final_severity=best_severity,
        labels=best_labels,
        results=best_results,
    )


# ================================================================
# 端点实现
# ================================================================

@ingest_router.post(
    "/logs",
    response_model=None,
    responses={
        202: {"model": IngestResponse},
        400: {"description": "参数错误"},
        429: {"description": "限流"},
    },
)
async def ingest_logs(req: IngestLogsRequest):
    """
    接收 EVMLogListener 推送的增量 Event Logs

    流程:
      1. 接收入库/缓冲区
      2. 按 tx_hash 分组
      3. 从数据库加载前端配置的启用规则链
      4. 对每个交易组执行规则链 (ChainExecutor)
      5. 命中的交易记录为可疑告警
    """
    t_start = time.time()

    # 校验 log_count 与实际一致
    if req.log_count and len(req.logs) != req.log_count:
        logger.warning(
            f"[ingest] log_count mismatch: header={req.log_count}, actual={len(req.logs)}"
        )

    # 转换为内部格式
    ingested_logs = [IngestedLog.from_dict(l.model_dump()) for l in req.logs]

    # 按 tx_hash 分组
    tx_groups: dict[str, list[IngestedLog]] = defaultdict(list)
    for log in ingested_logs:
        if not log.transaction_hash:
            continue
        tx_groups[log.transaction_hash].append(log)

    # 构建 TxLogsGroup 列表
    groups: list[TxLogsGroup] = [
        TxLogsGroup(
            tx_hash=h,
            chain_id=req.chain_id,
            logs=logs,
            block_number=req.to_block,
        )
        for h, logs in tx_groups.items()
    ]

    # 用规则链引擎评估每个交易组
    alerts: list[MatchedAlert] = []

    if groups:
        # 并发评估（控制并发数避免资源耗尽）
        import asyncio
        semaphore = asyncio.Semaphore(20)

        async def eval_one(group):
            async with semaphore:
                return await _evaluate_group_with_chains(group, chain_name=req.chain_name)

        results = await asyncio.gather(*(*[eval_one(g) for g in groups],), return_exceptions=True)
        for result in results:
            if isinstance(result, MatchedAlert):
                alerts.append(result)
            elif isinstance(result, Exception):
                logger.error(f"[ingest] Evaluate error: {result}")

    # 更新全局状态
    _state.update_block(req.chain_id, req.to_block)
    _state.add_stats(req.chain_id, len(ingested_logs), len(alerts))
    for alert in alerts:
        _state.add_alert(alert)

    elapsed_ms = (time.time() - t_start) * 1000

    resp = IngestResponse(
        status="accepted",
        received_log_count=len(ingested_logs),
        from_block=req.from_block,
        to_block=req.to_block,
        matched_alert_count=len(alerts),
        processed_at=time.strftime("%Y-%m-%dT%H:%M:%S.") + f"{time.time() % 1:.3f}Z",
        active_chain_count=_chain_manager.active_chain_count,
    )

    logger.info(
        f"[ingest] Received {len(ingested_logs)} logs "
        f"(blocks {req.from_block}-{req.to_block}, {len(groups)} txs, "
        f"{_chain_manager.active_chain_count} chains) "
        f"-> {len(alerts)} alerts in {elapsed_ms:.1f}ms"
    )

    # 命中详情日志（仅在 debug 级别输出）
    if alerts and logger.isEnabledFor(logging.DEBUG):
        for a in alerts[:5]:
            bm = a.best_match
            logger.debug(
                f"[ingest] ALERT: {a.tx_hash[:16]}... "
                f"type={bm['alert_type']} severity={bm['severity']} "
                f"score={a.final_score:.1f}"
            )

    return resp.model_dump(), 202


@ingest_router.post("/logs/replay", response_model=None)
async def ingest_replay_logs(req: ReplayLogsRequest):
    """断线恢复后的历史日志补传。与主接口逻辑相同，额外记录 reason 用于审计。"""
    t_start = time.time()

    ingested_logs = [IngestedLog.from_dict(l.model_dump()) for l in req.logs]

    tx_groups: dict[str, list[IngestedLog]] = defaultdict(list)
    for log in ingested_logs:
        if log.transaction_hash:
            tx_groups[log.transaction_hash].append(log)

    groups = [
        TxLogsGroup(tx_hash=h, chain_id=req.chain_id, logs=logs, block_number=req.to_block)
        for h, logs in tx_groups.items()
    ]

    alerts: list[MatchedAlert] = []

    for g in groups:
        alert = await _evaluate_group_with_chains(g, chain_name="")
        if alert:
            alerts.append(alert)

    _state.update_block(req.chain_id, req.to_block)
    _state.add_stats(req.chain_id, len(ingested_logs), len(alerts))
    for alert in alerts:
        _state.add_alert(alert)

    elapsed_ms = (time.time() - t_start) * 1000

    logger.info(
        f"[ingest/replay] Replayed {len(ingested_logs)} logs "
        f"(blocks {req.from_block}-{req.to_block}, reason={req.reason}) "
        f"-> {len(alerts)} alerts in {elapsed_ms:.1f}ms"
    )

    return {
        "status": "accepted",
        "received_log_count": len(ingested_logs),
        "from_block": req.from_block,
        "to_block": req.to_block,
        "reason": req.reason,
        "matched_alert_count": len(alerts),
        "processed_at": time.strftime("%Y-%m-%dT%H:%M:%S.") + f"{time.time() % 1:.3f}Z",
    }, 202


@ingest_router.get("/status", response_model=StatusResponse)
async def get_ingest_status():
    """查询日志消费进度和统计信息"""
    recent_alert_dicts = [a.to_dict() for a in _state.recent_alerts[-20:]]

    return StatusResponse(
        is_connected=True,
        last_received_at=time.strftime("%Y-%m-%dT%H:%M:%S") + "Z",
        consumed_blocks=_state.status_dict(),
    ).model_dump()


@ingest_router.get("/alerts/recent")
async def get_recent_alerts(limit: int = Query(default=20, ge=1, le=100)):
    """获取最近的匹配告警列表，用于前端 Dashboard 实时展示。"""
    recent = _state.recent_alerts[-limit:]
    return {
        "total": len(_state.recent_alerts),
        "items": [a.to_dict() for a in reversed(recent)],
    }


@ingest_router.get("/rules/stats")
async def get_rule_stats():
    """获取规则链运行统计"""
    return {
        "evaluated_txs": _state._evaluated_txs,
        "matched": sum(_state._matched_alerts.values()),
        "active_chains": _chain_manager.active_chain_count,
        "by_rule": dict(_state._by_rule),
    }
