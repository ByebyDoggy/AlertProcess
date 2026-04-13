"""ARKM 实体标签检测器 — 通过 @require("arkm_label") 自动获取上下文"""

from __future__ import annotations

from typing import Any

from nodes.base import NodeRegistry
from nodes.context.require import require
from nodes.detectors.base import BaseDetector


@require("arkm_label")
class ARKMLabelDetector(BaseDetector):
    """
    ARKM 实体标签检测器 — 通过 ARKM Intelligence 检测恶意实体标签。

    上下文需求:
      @require("arkm_label")
      → 执行前自动注入: entity_type, entity_id, entity_name, entity_confidence

    评分:
    - 黑名单实体类型 (hacker) → 95
    - 已知实体但非黑名单 → 20
    - 无标签 → 0
    """

    name: str = "arkm_label_detector"
    label: str = "ARKM 标签检测"
    description: str = "通过 ARKM Intelligence 检测恶意实体标签（需 ARKM API 上下文）"
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

        # @require("arkm_label") 已自动注入以下字段:
        # - entity_type: 实体类型 (hacker, exchange, etc.)
        # - entity_id, entity_name, entity_confidence
        entity_type = context.get("entity_type")
        entity_id = context.get("entity_id")
        entity_name = context.get("entity_name")
        entity_confidence = context.get("entity_confidence")

        if not entity_type:
            # ARKM API 未配置或调用失败
            return 0.0, {
                "address": address,
                "reason": "no entity data (ARKM API not configured or unavailable)",
            }

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
            "entity_confidence": entity_confidence,
            "is_blacklisted": entity_type in blacklist,
            "detected_issues": issues,
            "labels": labels,
        }


NodeRegistry.register(ARKMLabelDetector)
