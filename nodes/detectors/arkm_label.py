"""ARKM 实体标签检测器 — 迁移到新节点架构（框架实现，需外部 API）"""

from __future__ import annotations

from typing import Any

from nodes.base import NodeRegistry
from nodes.detectors.base import BaseDetector


class ARKMLabelDetector(BaseDetector):
    """
    ARKM 实体标签检测器 — 通过 ARKM Intelligence 检测恶意实体标签。

    评分:
    - 黑名单实体类型 (hacker) → 95
    - 已知实体但非黑名单 → 20
    - 无标签 → 0

    注意: 此检测器需要 ARKM API 支持或数据库缓存。
    当前为框架实现，优先使用 context 中的 `entity_type` 字段。
    """

    name: str = "arkm_label_detector"
    label: str = "ARKM 标签检测"
    description: str = "通过 ARKM Intelligence 检测恶意实体标签"
    icon: str = "\U0001f50d"
    color: str = "#7c3aed"

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "threshold": {"type": "number", "minimum": 0, "maximum": 100, "default": 50},
                "blacklist_entity_types": {"type": "array", "items": {"type": "string"},
                                             "default": ["hacker"]},
                "ignored_entity_types": {"type": "array", "items": {"type": "string"}, "default": []},
            },
        }

    @classmethod
    def get_default_config(cls) -> dict[str, Any]:
        return {
            "threshold": 50,
            "blacklist_entity_types": ["hacker"],
            "ignored_entity_types": [],
        }

    async def detect(self, context: dict[str, Any]) -> tuple[float, dict[str, Any]]:
        address = context.get("exploiter_address") or context.get("from_address", "")
        if not address:
            return 0.0, {"error": "no address available"}

        # 优先使用 context 中的 entity_type
        entity_type = context.get("entity_type")
        entity_id = context.get("entity_id")
        entity_name = context.get("entity_name")

        if not entity_type:
            return 0.0, {"address": address, "reason": "no entity data in context"}

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
        return score, {
            "address": address,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "entity_name": entity_name,
            "is_blacklisted": entity_type in blacklist,
            "detected_issues": issues,
            "labels": labels,
        }


NodeRegistry.register(ARKMLabelDetector)
