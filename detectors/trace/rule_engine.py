"""
Ingest 数据模型（兼容层）
========================

⚠️ 已迁移至统一模型: models.ingest

本模块保留 dataclass 定义作为**向后兼容层**，
所有新代码应使用:
  - models.ingest.EventLog       (替代 IngestedLog)
  - models.ingest.TxLogsGroup    (替代 TxLogsGroup)
  - models.ingest.AlertData      (替代 _build_alert_data)
  - models.ingest.TransferEvent  (新增)

迁移完成后可移除此文件。
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
    [兼容] 从 EVMLogListener 接收的单条 Event Log

    新代码请使用 models.ingest.EventLog。
    此 dataclass 保留用于 ingest_router 等尚未迁移的调用方。
    """
    address: str = ""
    topics: list[str] = field(default_factory=list)
    data: str = "0x"
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
    """
    [兼容] 按 tx_hash 分组后的日志集合

    新代码请使用 models.ingest.TxLogsGroup (Pydantic)。
    此 dataclass 保留用于 ingest_router 等尚未迁移的调用方。
    """
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
    results: list[dict[str, Any]] = field(default_factory=list)
    trigger_log_count: int = 0
    detected_at: float = 0.0
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
