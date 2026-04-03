"""地址年龄检测器 — 迁移到新节点架构（框架实现，需外部 API）"""

from __future__ import annotations

from typing import Any

from nodes.base import NodeRegistry
from nodes.detectors.base import BaseDetector


class AddressAgeDetector(BaseDetector):
    """
    地址年龄检测器 — 检测新建地址的交易行为。

    评分:
    - 地址创建 < 1 天 → 90
    - 地址创建 < 阈值天数 → 70
    - 地址创建 < 2x阈值 → 40
    - 无数据 → 0

    注意: 此检测器需要外部 API（Moralis）或数据库缓存支持。
    当前为框架实现，优先使用 context 中的 `address_create_time` 字段。
    """

    name: str = "address_age_detector"
    label: str = "地址年龄检测"
    description: str = "检测可疑的新建地址"
    icon: str = "\U0001f4c5"
    color: str = "#14b8a6"

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "threshold": {"type": "number", "minimum": 0, "maximum": 100, "default": 50},
                "new_address_threshold_days": {"type": "integer", "default": 7},
            },
        }

    @classmethod
    def get_default_config(cls) -> dict[str, Any]:
        return {"threshold": 50, "new_address_threshold_days": 7}

    async def detect(self, context: dict[str, Any]) -> tuple[float, dict[str, Any]]:
        address = context.get("exploiter_address") or context.get("from_address", "")
        if not address:
            return 0.0, {"error": "no address available"}

        # 优先使用 context 中的 create_time
        create_time_str = context.get("address_create_time")
        age_days = context.get("address_age_days")

        if age_days is not None:
            score, details = self._score_by_age(age_days)
        elif create_time_str:
            from datetime import datetime, timezone
            try:
                ct = datetime.fromisoformat(str(create_time_str))
                if ct.tzinfo is None:
                    ct = ct.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                days = (now - ct).days
                score, details = self._score_by_age(days)
            except Exception:
                return 0.0, {"error": "invalid create_time format", "address": address}
        else:
            # 无年龄数据，尝试从 chain_id 获取
            return 0.0, {"address": address, "reason": "no age data in context"}

        details["address"] = address
        return score, details

    def _score_by_age(self, age_days: int) -> tuple[float, dict[str, Any]]:
        threshold = self.config.get("new_address_threshold_days", 7)
        issues: list[str] = []

        if age_days < 1:
            score = 90
            issues.append("VERY_NEW_ADDRESS")
        elif age_days < threshold:
            score = 70
            issues.append("NEW_ADDRESS")
        elif age_days < threshold * 2:
            score = 40
            issues.append("RECENTLY_CREATED_ADDRESS")
        else:
            score = 10
            issues = []

        labels = issues if score >= self.config.get("threshold", 50) else []
        return score, {
            "age_days": age_days,
            "threshold_days": threshold,
            "detected_issues": issues,
            "labels": labels,
        }


NodeRegistry.register(AddressAgeDetector)
