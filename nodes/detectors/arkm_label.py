"""ARKM 实体标签检测器

通过 ARKM Intelligence 检测恶意实体标签。标签数据通过 ARKMLabelProviderNode 节点预先填充。
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from nodes.base import NodeRegistry, score_to_severity
from nodes.detectors.base import BaseDetector, DetectorConfigMixin, DetectorOutputMixin
from nodes.models import TransactionContext


class ARKMLabelOutput(DetectorOutputMixin):
    """ARKM 标签检测器输出"""
    pass


class ARKMLabelDetector(BaseDetector):
    """
    ARKM 实体标签检测器 — 通过 ARKM Intelligence 检测恶意实体标签。

    标签数据通过 ARKMLabelProviderNode 节点预先填充到 tx_context.extra:
      - entity_type: 实体类型 (hacker, exchange, etc.)
      - entity_id: 实体 ID
      - entity_name: 实体名称
      - entity_confidence: 置信度

    评分:
    - 黑名单实体类型 (hacker) → 95
    - 已知实体但非黑名单 → 20
    - 无标签 → 0
    """

    name: str = "arkm_label_detector"
    label: str = "ARKM 标签检测"
    description: str = "通过 ARKM Intelligence 实体标签库检测恶意实体：黑名单类型（如 hacker）直接给 95 分，已知实体 20 分。需连接 ARKMLabelProviderNode 节点"
    icon: str = "\U0001f50d"
    color: str = "#7c3aed"

    # ── Pydantic 配置模型 (继承 DetectorConfigMixin，包含共享的 threshold) ──
    class ConfigModel(DetectorConfigMixin):
        blacklist_entity_types: list[str] = Field(default=["hacker"], description="黑名单实体类型列表")
        ignored_entity_types: list[str] = Field(default=[], description="忽略的实体类型列表")

    # ── Pydantic 输出模型 ──
    OutputModel: type = ARKMLabelOutput

    async def process(self, tx_context: TransactionContext) -> ARKMLabelOutput:
        address = tx_context.extra.get("exploiter_address") or tx_context.from_address or ""
        if not address:
            return ARKMLabelOutput(score=0.0, passed=True, severity="UNKNOWN", labels=[],
                                   detection={"error": "no address available"})

        # 从 tx_context.extra 获取 ARKMLabelProviderNode 预先填充的数据
        entity_type = tx_context.extra.get("entity_type")
        entity_id = tx_context.extra.get("entity_id")
        entity_name = tx_context.extra.get("entity_name")
        entity_confidence = tx_context.extra.get("entity_confidence")

        if not entity_type:
            return ARKMLabelOutput(score=0.0, passed=True, severity="UNKNOWN", labels=[],
                                   detection={"address": address, "reason": "no entity data (ARKMLabelProviderNode not connected or unavailable)"})

        blacklist = self.config.get("blacklist_entity_types", ["hacker"])
        ignored = self.config.get("ignored_entity_types", [])
        issues: list[str] = []

        if entity_type in blacklist:
            score = 95
            issues.append(f"BLACKLISTED_ENTITY:{entity_type}")
        elif entity_type not in ignored:
            score = 20
            issues.append(f"KNOWN_ENTITY:{entity_type}")
        else:
            score = 5
            issues = []

        labels = issues if score >= self.config.get("threshold", 50) else []
        threshold = self.config.get("threshold", 50.0)
        return ARKMLabelOutput(
            score=score, passed=score >= threshold, severity=score_to_severity(score),
            labels=labels,
            detection={
                "address": address,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "entity_name": entity_name,
                "entity_confidence": entity_confidence,
                "is_blacklisted": entity_type in blacklist,
                "detected_issues": issues,
                "labels": labels,
            },
        )


NodeRegistry.register(ARKMLabelDetector)
