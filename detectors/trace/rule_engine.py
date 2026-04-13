"""
Ingest 数据模型
================
从 EVMLogListener 接收的原始 Event Logs 的数据结构定义。

规则检测逻辑已迁移至 engine/ + nodes/ 架构（前端可视化配置的 DAG 规则链）。
本模块仅保留数据传输对象（DTO），供 ingest_router 和测试使用。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    """告警严重级别"""
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class IngestedLog:
    """
    从 EVMLogListener 接收的单条 Event Log

    字段与 EVMLISTENER_INPUT_SPEC.md 中 LogObject 一致，
    所有数值字段均为 integer 类型。
    """
    address: str = ""              # 合约地址
    topics: list[str] = field(default_factory=list)
    data: str = "0x"               # hex string
    block_number: int = 0
    transaction_hash: str = ""
    log_index: int = 0
    transaction_index: int = 0
    block_hash: str = ""
    removed: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> IngestedLog:
        return cls(
            address=d.get("address", "").lower(),
            topics=[t.lower() if t else t for t in d.get("topics", [])],
            data=d.get("data", "0x") or "0x",
            block_number=int(d.get("block_number", 0)),
            transaction_hash=d.get("transaction_hash", ""),
            log_index=int(d.get("log_index", 0)),
            transaction_index=int(d.get("transaction_index", 0)),
            block_hash=d.get("block_hash", ""),
            removed=bool(d.get("removed", False)),
        )


@dataclass
class TxLogsGroup:
    """按 tx_hash 分组后的日志集合"""
    tx_hash: str
    chain_id: int
    logs: list[IngestedLog]
    block_number: int = 0

    @property
    def log_count(self) -> int:
        return len(self.logs)

    @property
    def unique_addresses(self) -> set[str]:
        return {log.address for log in self.logs if log.address}

    @property
    def unique_topics(self) -> set[str]:
        topics_set = set()
        for log in self.logs:
            for t in log.topics:
                if t:
                    topics_set.add(t.lower())
        return topics_set


@dataclass
class MatchedAlert:
    """规则链匹配结果 — 一笔可疑交易"""
    tx_hash: str
    chain_id: int
    block_number: int
    results: list[dict[str, Any]] = field(default_factory=list)  # 节点执行结果
    trigger_log_count: int = 0
    detected_at: float = 0.0
    # 从 ExecutionContext 聚合的结果
    final_score: float = 0.0
    final_severity: str = "UNKNOWN"
    labels: list[str] = field(default_factory=list)

    @property
    def best_match(self) -> dict[str, Any]:
        """返回最高严重级别的结果摘要"""
        if not self.results:
            return {
                "alert_type": "",
                "severity": Severity.INFO.value,
                "confidence": 0.0,
                "details": {},
            }
        # 返回分数最高的节点结果
        best = max(self.results, key=lambda r: r.get("score", 0))
        return {
            "alert_type": best.get("node_type", ""),
            "severity": best.get("severity", self.final_severity),
            "confidence": round(best.get("score", 0) / 100.0, 2),
            "details": best,
        }

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        bm = self.best_match
        return {
            "txHash": self.tx_hash,
            "chainId": self.chain_id,
            "blockNumber": self.block_number,
            "logCount": self.trigger_log_count,
            "finalScore": self.final_score,
            "finalSeverity": self.final_severity,
            "labels": self.labels,
            "bestAlertType": bm["alert_type"],
            "bestSeverity": bm["severity"],
            "detectedAt": self.detected_at or time.time(),
        }
