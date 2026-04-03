"""地址类型检测器 — 检测 null 地址交易和合约创建模式"""

from __future__ import annotations

from typing import Any

from nodes.base import NodeRegistry
from nodes.detectors.base import BaseDetector


class AddressTypeDetector(BaseDetector):
    """
    地址类型检测器。

    评分规则:
    - null 'to' 地址 + value > 0        → 85 分（合约创建携带资金）
    - null 'from' 地址                   → 90 分（异常来源）
    - null 'to' 地址 + input_data       → 30 分（合约创建）
    - 无异常                            → 0 分
    """

    name: str = "address_type_detector"
    label: str = "地址类型检测"
    description: str = "检测 null 地址交易和合约创建模式"
    icon: str = "\U0001f3e0"
    color: str = "#8b5cf6"

    NULL_ADDRESS = "0x0000000000000000000000000000000000000000"

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "threshold": {
                    "type": "number", "minimum": 0, "maximum": 100,
                    "default": 30, "description": "passed 阈值"
                },
                "check_null_to": {
                    "type": "boolean", "default": True,
                    "description": "检测 null 'to' 地址"
                },
                "check_null_from": {
                    "type": "boolean", "default": True,
                    "description": "检测 null 'from' 地址"
                },
                "check_contract_creation": {
                    "type": "boolean", "default": True,
                    "description": "检测合约创建模式"
                },
            },
        }

    @classmethod
    def get_default_config(cls) -> dict[str, Any]:
        return {
            "threshold": 30,
            "check_null_to": True,
            "check_null_from": True,
            "check_contract_creation": True,
        }

    async def detect(self, context: dict[str, Any]) -> tuple[float, dict[str, Any]]:
        to_addr = context.get("to_address", "")
        from_addr = context.get("from_address", "")
        value = context.get("value", 0)
        input_data = context.get("input_data", "0x")

        is_null_to = to_addr.lower() == self.NULL_ADDRESS.lower() if to_addr else False
        is_null_from = from_addr.lower() == self.NULL_ADDRESS.lower() if from_addr else False

        issues: list[str] = []
        score = 0.0
        alert_type = None

        # null from — 最异常
        if self.config.get("check_null_from", True) and is_null_from:
            issues.append("NULL_FROM_ADDRESS")
            score = 90.0
            alert_type = "NULL_FROM_ADDRESS"

        # null to + value — 合约创建携带资金
        if self.config.get("check_null_to", True) and is_null_to:
            if value and value > 0:
                issues.append("CONTRACT_CREATION_WITH_VALUE")
                score = max(score, 85.0)
                alert_type = "CONTRACT_CREATION_WITH_VALUE"

            # 合约创建模式
            if self.config.get("check_contract_creation", True):
                if input_data and input_data != "0x" and score < 85.0:
                    issues.append("CONTRACT_CREATION")
                    score = max(score, 30.0)
                    alert_type = "CONTRACT_CREATION"
                elif not issues:
                    issues.append("NULL_TO_ADDRESS")
                    score = max(score, 25.0)
                    alert_type = "NULL_TO_ADDRESS"

        labels = issues if score >= self.config.get("threshold", 30) else []

        details: dict[str, Any] = {
            "from_address": from_addr,
            "to_address": to_addr,
            "value": value,
            "is_null_to": is_null_to,
            "is_null_from": is_null_from,
            "detected_issues": issues,
            "alert_type": alert_type,
            "labels": labels,
        }
        return score, details


NodeRegistry.register(AddressTypeDetector)
