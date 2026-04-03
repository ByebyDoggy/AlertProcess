"""
执行上下文

管理整个规则链执行过程中的数据流，记录每个节点的输出、执行日志和最终结果。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from nodes.base import NodeOutput


@dataclass
class ExecutionLogEntry:
    """单条执行日志"""
    node_id: str
    node_type: str
    score: float
    passed: bool
    duration_ms: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error: str | None = None


@dataclass
class ExecutionContext:
    """
    异步执行上下文。

    在整个规则链执行过程中跟踪:
    - 各节点的输出
    - 执行日志
    - 聚合的标签和严重级别
    - 已执行的动作列表
    """

    # 原始告警数据
    alert_data: dict[str, Any] = field(default_factory=dict)

    # 各节点的输出（包含端口路由信息）
    node_outputs: dict[str, NodeOutput] = field(default_factory=dict)

    # 执行日志
    logs: list[ExecutionLogEntry] = field(default_factory=list)

    # 聚合结果
    collected_labels: list[str] = field(default_factory=list)
    final_severity: str = "UNKNOWN"
    final_score: float = 0.0

    # 已执行的动作
    actions_executed: list[dict[str, Any]] = field(default_factory=list)

    # 错误列表
    errors: list[str] = field(default_factory=list)

    def set_output(self, node_id: str, output: NodeOutput) -> None:
        """记录节点输出"""
        self.node_outputs[node_id] = output

        # 聚合标签
        for label in output.labels:
            if label not in self.collected_labels:
                self.collected_labels.append(label)

        # 更新最高严重级别
        severity_order = {"UNKNOWN": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
        if severity_order.get(output.severity, 0) > severity_order.get(self.final_severity, 0):
            self.final_severity = output.severity

        # 更新最高分数
        if output.score > self.final_score:
            self.final_score = output.score

    def add_log(self, entry: ExecutionLogEntry) -> None:
        """添加执行日志"""
        self.logs.append(entry)

    def add_error(self, error: str) -> None:
        """添加错误"""
        self.errors.append(error)

    def get_output(self, node_id: str) -> NodeOutput | None:
        """获取指定节点的输出"""
        return self.node_outputs.get(node_id)

    def get_success(self) -> bool:
        """规则链是否成功执行（无致命错误）"""
        return len(self.errors) == 0
