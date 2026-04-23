"""重入攻击检测器

检测 ERC20 logs 中体现出的重入攻击特征：
  - 同一交易内同一合约地址被调用超过阈值次数（调用风暴）
  - 事件日志中同一合约重复 Transfer / 重复 approval 密集序列
  - Reentrancy 经典特征：合约 A 调用合约 B，B 在 A 完成前再次调用 A
    （本 Detector 通过 logs 信号识别，深层调用树分析在 behaviors 层完成）

评分矩阵:
  - 同一合约 log 出现 ≥ extreme_count 次   → 95
  - 同一合约 log 出现 ≥ high_count 次      → 70
  - 同一合约 log 出现 ≥ medium_count 次    → 40
  - 所有合约单次出现                       → 0
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from pydantic import Field

from nodes.base import NodeRegistry, score_to_severity
from nodes.detectors.base import BaseDetector, DetectorConfigMixin, DetectorOutputMixin
from nodes.models import TransactionContext


class ReentrancyOutput(DetectorOutputMixin):
    """重入攻击检测器输出"""
    pass


class ReentrancyDetector(BaseDetector):
    """
    重入攻击检测器 — 通过 logs 中合约地址的出现频率识别重入模式。

    核心思路:
      重入攻击的典型特征是在单笔交易中，某一合约地址会被反复触发产生大量相同事件（如
      Transfer / Withdraw），形成事件日志中的「高频重复」信号。

    评分:
    - 某合约地址 log 数 >= extreme_count(默认20) → 95
    - 某合约地址 log 数 >= high_count(默认10)    → 70
    - 某合约地址 log 数 >= medium_count(默认5)   → 40
    - 无重复迹象                                 → 0
    """

    name: str = "reentrancy_detector"
    label: str = "重入攻击检测"

    # ── Pydantic 配置模型 (继承 DetectorConfigMixin，包含共享的 threshold) ──
    class ConfigModel(DetectorConfigMixin):
        threshold: float = Field(default=40.0, ge=0, le=100, description="passed 阈值")
        medium_count: int = Field(default=5, ge=2, description="触发 medium(40分) 的最小 log 数量")
        high_count: int = Field(default=10, ge=3, description="触发 high(70分) 的最小 log 数量")
        extreme_count: int = Field(default=20, ge=5, description="触发 extreme(95分) 的最小 log 数量")

    description: str = (
        "检测重入攻击：通过 logs 中合约地址的高频重复出现识别重入模式。"
        "同一合约 ≥20 次日志给 95 分，≥10 次给 70 分，≥5 次给 40 分。"
        "是识别 DAO-style 重入、ERC777 回调重入等经典漏洞利用的基础检测器。"
    )
    icon: str = "🔄"
    color: str = "#dc2626"

    # ── Pydantic 输出模型 ──
    OutputModel: type = ReentrancyOutput

    async def process(self, input: DetectorInputMixin) -> ReentrancyOutput:
        logs: list[dict] = input.logs

        if not logs:
            return ReentrancyOutput(score=0.0, passed=True, severity="UNKNOWN", labels=[],
                                    detection={"reason": "no logs in context"})

        medium_count = self.config.get("medium_count", 5)
        high_count = self.config.get("high_count", 10)
        extreme_count = self.config.get("extreme_count", 20)

        # 统计每个合约地址的 log 出现次数
        address_counter: Counter[str] = Counter()
        for log in logs:
            addr = (log.get("address") or "").lower()
            if addr:
                address_counter[addr] += 1

        if not address_counter:
            return ReentrancyOutput(score=0.0, passed=True, severity="UNKNOWN", labels=[],
                                    detection={"reason": "no contract addresses in logs"})

        # 找到最高频次的合约
        top_addr, top_count = address_counter.most_common(1)[0]
        issues: list[str] = []
        score = 0.0

        if top_count >= extreme_count:
            issues.append(f"EXTREME_REENTRANCY_SIGNAL:{top_addr}:{top_count}")
            score = 95.0
        elif top_count >= high_count:
            issues.append(f"HIGH_REENTRANCY_SIGNAL:{top_addr}:{top_count}")
            score = 70.0
        elif top_count >= medium_count:
            issues.append(f"MEDIUM_REENTRANCY_SIGNAL:{top_addr}:{top_count}")
            score = 40.0

        # 额外检测：多个合约同时重复（分散式重入）
        repeated_contracts = [
            (addr, cnt) for addr, cnt in address_counter.items()
            if cnt >= medium_count
        ]
        if len(repeated_contracts) > 1 and score < 70:
            issues.append(f"MULTI_CONTRACT_REPEAT:{len(repeated_contracts)}")
            score = max(score, 55.0)

        labels = issues if score >= self.config.get("threshold", 40) else []
        threshold = self.config.get("threshold", 40.0)
        from nodes.base import score_to_severity

        return ReentrancyOutput(
            score=score, passed=score >= threshold, severity=score_to_severity(score),
            labels=labels,
            detection={
                "top_contract": top_addr,
                "top_count": top_count,
                "total_logs": len(logs),
                "unique_contracts": len(address_counter),
                "repeated_contracts": [
                    {"address": addr, "count": cnt}
                    for addr, cnt in address_counter.most_common(5)
                    if cnt >= medium_count
                ],
                "detected_issues": issues,
                "labels": labels,
            },
        )


NodeRegistry.register(ReentrancyDetector)
