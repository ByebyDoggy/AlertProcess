"""地址类型检测器 — 检测 null 地址交易和合约创建模式"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from nodes.base import NodeRegistry, score_to_severity
from nodes.detectors.base import BaseDetector, DetectorConfigMixin, DetectorOutputMixin
from nodes.models import TransactionContext


class AddressTypeOutput(DetectorOutputMixin):
    """地址类型检测器输出"""
    pass


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

    # ── Pydantic 配置模型 (继承 DetectorConfigMixin，包含共享的 threshold) ──
    class ConfigModel(DetectorConfigMixin):
        threshold: float = Field(default=30.0, ge=0, le=100, description="passed 阈值")
        check_null_to: bool = Field(default=True, description="检测 null 'to' 地址")
        check_null_from: bool = Field(default=True, description="检测 null 'from' 地址")
        check_contract_creation: bool = Field(default=True, description="检测合约创建模式")

    description: str = "检测可疑地址类型：null 地址转账（合约创建/销毁）、携带 ETH 的合约创建（85 分）、null 来源地址（90 分）。常用于识别部署攻击合约或资金销毁操作"
    icon: str = "\U0001f3e0"
    color: str = "#8b5cf6"

    # ── Pydantic 输出模型 ──
    OutputModel: type = AddressTypeOutput

    NULL_ADDRESS = "0x0000000000000000000000000000000000000000"

    async def process(self, tx_context: TransactionContext) -> AddressTypeOutput:
        to_addr = tx_context.to_address or ""
        from_addr = tx_context.from_address or ""
        value = tx_context.value or 0
        input_data = tx_context.input_data or "0x"

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
        threshold = self.config.get("threshold", 30.0)

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
        return AddressTypeOutput(
            score=score, passed=score >= threshold, severity=score_to_severity(score),
            labels=labels, detection=details,
        )


NodeRegistry.register(AddressTypeDetector)
