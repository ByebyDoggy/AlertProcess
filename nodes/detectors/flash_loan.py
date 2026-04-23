"""闪电贷检测器 — 迁移到新节点架构"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from nodes.base import NodeRegistry, score_to_severity
from nodes.detectors.base import BaseDetector, DetectorConfigMixin, DetectorOutputMixin
from nodes.models import TransactionContext

KNOWN_FLASH_LOAN_PROTOCOLS: dict[str, str] = {
    "0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9": "Aave V2",
    "0x794a61358d6845594f94dc1db02a252b5b4814aa": "Aave V3",
    "0x1e0447b19bb6ecfdae1e4ae1694b0c3659614e4e": "dYdX",
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": "Uniswap V3",
    "0x3d9819210a31b4961b30ef54be2aed79b9c9cd3b": "Compound",
}

FLASH_LOAN_METHOD_SIGS: dict[str, str] = {
    "0x0906f8c8": "flash",
    "0x5c7d2920": "flashLoan",
    "0x016602d8": "flashswap",
    "0xab9c4b5d": "initiateFlashLoan",
}


class FlashLoanOutput(DetectorOutputMixin):
    """闪电贷检测器输出"""
    pass


class FlashLoanDetector(BaseDetector):
    """
    闪电贷检测器 — 检测闪电贷攻击和可疑闪电贷模式。

    评分:
    - 已知闪电贷协议 + 大额交易 → 95
    - 已知闪电贷协议交互 → 70
    - 闪电贷方法签名 → 60
    - 大额交易（非闪电贷协议）→ 50
    """

    name: str = "flash_loan_detector"
    label: str = "闪电贷检测"
    description: str = "检测闪电贷攻击：通过已知协议地址（Aave/dYdX/Uniswap/Compound）和方法签名（flash/flashLoan/flashswap）识别。大额闪电贷交互给 95 分，纯方法签名 60 分"
    icon: str = "\u26a1"
    color: str = "#ef4444"

    # ── Pydantic 配置模型 (继承 DetectorConfigMixin，包含共享的 threshold) ──
    class ConfigModel(DetectorConfigMixin):
        large_flash_loan_threshold_usd: float = Field(default=100000.0, ge=0, description="大额闪电贷阈值（USD）")
        chain_id_to_native_token_price: dict[str, float] = Field(
            default={1: 2000.0, 56: 300.0, 137: 1.0},
            description="原生代币价格映射",
        )

    # ── Pydantic 输出模型 ──
    OutputModel: type = FlashLoanOutput

    @staticmethod
    def _has_flash_loan_method(input_data: str) -> bool:
        if not input_data or input_data == "0x" or len(input_data) < 10:
            return False
        return input_data[:10].lower() in FLASH_LOAN_METHOD_SIGS

    @staticmethod
    def _get_protocol_name(to_address: str) -> str | None:
        if not to_address:
            return None
        return KNOWN_FLASH_LOAN_PROTOCOLS.get(to_address.lower())

    async def process(self, tx_context: TransactionContext) -> FlashLoanOutput:
        to_address = tx_context.to_address or ""
        input_data = tx_context.input_data or ""
        value = tx_context.value or 0
        chain_id = tx_context.chain_id or 1

        issues: list[str] = []
        score = 0.0

        protocol = self._get_protocol_name(to_address)
        has_method = self._has_flash_loan_method(input_data)

        price_map = self.config.get("chain_id_to_native_token_price", {})
        native_price = price_map.get(chain_id, price_map.get(str(chain_id), 0))
        value_usd = (value / 10**18) * native_price if value else 0
        large_threshold = self.config.get("large_flash_loan_threshold_usd", 100000)
        is_large = value_usd > large_threshold

        if protocol and is_large:
            issues.append(f"LARGE_FLASH_LOAN_ATTACK:{protocol}")
            score = 95
        elif protocol and has_method:
            issues.append(f"FLASH_LOAN_PROTOCOL_METHOD:{protocol}")
            score = 80
        elif protocol:
            issues.append(f"FLASH_LOAN_PROTOCOL:{protocol}")
            score = 70
        elif has_method:
            issues.append("FLASH_LOAN_METHOD_SIGNATURE")
            score = 60
        elif is_large:
            issues.append(f"LARGE_FLASH_LOAN:{value_usd:,.0f}")
            score = 50

        labels = issues if score >= self.config.get("threshold", 50) else []
        threshold = self.config.get("threshold", 50.0)

        return FlashLoanOutput(
            score=score, passed=score >= threshold, severity=score_to_severity(score),
            labels=labels,
            detection={
                "to_address": to_address,
                "value": value,
                "value_usd": round(value_usd, 2),
                "protocol": protocol,
                "has_flash_loan_method": has_method,
                "is_large": is_large,
                "detected_issues": issues,
                "labels": labels,
            },
        )


NodeRegistry.register(FlashLoanDetector)
