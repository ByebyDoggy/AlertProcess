"""代币异常转账检测器 — 迁移到新节点架构"""

from __future__ import annotations

from typing import Any

from nodes.base import NodeRegistry
from nodes.detectors.base import BaseDetector


class TokenAnomalyDetector(BaseDetector):
    """
    代币异常检测器 — 检测大额转账、新代币活动、异常合约交互。

    评分:
    - 大额转账 → 80
    - 新代币活动 → 60
    - 异常合约交互 → 30
    """

    name: str = "token_anomaly_detector"
    label: str = "代币异常检测"
    description: str = "检测异常代币转账模式"
    icon: str = "\U0001f4b0"
    color: str = "#ec4899"

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "threshold": {"type": "number", "minimum": 0, "maximum": 100, "default": 50},
                "large_transfer_threshold": {"type": "number", "default": 1000000.0},
                "new_token_block": {"type": "object", "default": {1: 17000000, 56: 25000000, 137: 45000000}},
            },
        }

    @classmethod
    def get_default_config(cls) -> dict[str, Any]:
        return {
            "threshold": 50,
            "large_transfer_threshold": 1000000.0,
            "new_token_block": {1: 17000000, 56: 25000000, 137: 45000000},
        }

    @staticmethod
    def _parse_transfer_data(input_data: str) -> dict[str, Any] | None:
        if not input_data or len(input_data) < 10:
            return None
        method_sig = input_data[:10].lower()
        try:
            if method_sig == "0xa9059cbb":
                return {"method": "transfer", "to": "0x" + input_data[34:74],
                        "amount": int(input_data[74:], 16) if len(input_data) > 74 else 0}
            elif method_sig == "0x23b872dd":
                return {"method": "transferFrom", "from": "0x" + input_data[34:74],
                        "to": "0x" + input_data[98:138],
                        "amount": int(input_data[138:], 16) if len(input_data) > 138 else 0}
        except Exception:
            pass
        return None

    async def detect(self, context: dict[str, Any]) -> tuple[float, dict[str, Any]]:
        to_address = context.get("to_address", "")
        input_data = context.get("input_data", "")
        value = context.get("value", 0)
        block_number = context.get("block_number")
        chain_id = context.get("chain_id", 1)

        issues: list[str] = []
        score = 0.0
        large_threshold = self.config.get("large_transfer_threshold", 1000000)

        # Large ETH transfer
        null_addr = "0x0000000000000000000000000000000000000000"
        if to_address and to_address.lower() == null_addr:
            value_eth = value / 10**18 if value else 0
            if value_eth > large_threshold:
                issues.append(f"LARGE_ETH_TRANSFER:{value_eth:.2f} ETH")
                score = max(score, 80)

        # ERC20 transfer
        transfer_info = self._parse_transfer_data(input_data)
        if transfer_info:
            amount = transfer_info.get("amount", 0)
            if amount > large_threshold:
                issues.append(f"LARGE_TOKEN_TRANSFER:{amount}")
                score = max(score, 80)

        # Unusual contract interaction
        if input_data and input_data != "0x" and not transfer_info:
            if not (to_address and to_address.lower() == null_addr):
                issues.append("UNUSUAL_CONTRACT_INTERACTION")
                score = max(score, 30)

        # New token activity
        if block_number:
            block_thresholds = self.config.get("new_token_block", {})
            threshold = block_thresholds.get(chain_id, block_thresholds.get(str(chain_id), 0))
            if threshold and block_number < threshold + 1000000:
                issues.append("NEW_TOKEN_ACTIVITY")
                score = max(score, 60)

        labels = issues if score >= self.config.get("threshold", 50) else []
        return score, {
            "to_address": to_address,
            "value": value,
            "transfer_info": transfer_info,
            "block_number": block_number,
            "detected_issues": issues,
            "labels": labels,
        }


NodeRegistry.register(TokenAnomalyDetector)
