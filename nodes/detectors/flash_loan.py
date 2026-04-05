"""闪电贷检测器 — 迁移到新节点架构"""

from __future__ import annotations

from typing import Any

from nodes.base import NodeRegistry
from nodes.detectors.base import BaseDetector

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
    description: str = "检测闪电贷攻击和可疑闪电贷模式"
    icon: str = "\u26a1"
    color: str = "#ef4444"

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "threshold": {"type": "number", "minimum": 0, "maximum": 100, "default": 50},
                "large_flash_loan_threshold_usd": {"type": "number", "default": 100000.0},
                "chain_id_to_native_token_price": {"type": "object", "default": {1: 2000, 56: 300, 137: 1}},
            },
        }

    @classmethod
    def get_default_config(cls) -> dict[str, Any]:
        return {
            "threshold": 50,
            "large_flash_loan_threshold_usd": 100000.0,
            "chain_id_to_native_token_price": {1: 2000.0, 56: 300.0, 137: 1.0},
        }

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

    async def detect(self, context: dict[str, Any]) -> tuple[float, dict[str, Any]]:
        to_address = context.get("to_address", "")
        input_data = context.get("input_data", "")
        value = context.get("value", 0)
        chain_id = context.get("chain_id", 1)

        # value 可能是字符串（JSON 存储），转换为 int
        if isinstance(value, str):
            try:
                value = int(value)
            except (ValueError, TypeError):
                value = 0

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

        return score, {
            "to_address": to_address,
            "value": value,
            "value_usd": round(value_usd, 2),
            "protocol": protocol,
            "has_flash_loan_method": has_method,
            "is_large": is_large,
            "detected_issues": issues,
            "labels": labels,
        }


NodeRegistry.register(FlashLoanDetector)
