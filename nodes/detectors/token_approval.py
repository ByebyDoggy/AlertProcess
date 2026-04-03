"""ERC20 授权检测器 — 迁移到新节点架构"""

from __future__ import annotations

from typing import Any

from nodes.base import NodeRegistry
from nodes.detectors.base import BaseDetector

MAX_UINT256 = 115792089237316195423570985008687907853269984665640564039457584007913129639935

APPROVAL_METHOD_SIGS: dict[str, str] = {
    "0x095ea7b3": "approve",
    "0x23b872dd": "transferFrom",
    "0xa22cb465": "setApprovalForAll",
}

SUSPICIOUS_APPROVAL_TARGETS: dict[str, str] = {
    "0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9": "Aave V2",
    "0x794a61358d6845594f94dc1db02a252b5b4814aa": "Aave V3",
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": "Uniswap V3",
}


class TokenApprovalDetector(BaseDetector):
    """
    ERC20 授权检测器 — 检测可疑的 ERC20 授权操作。

    评分:
    - 无限授权 (INFINITE_APPROVAL) → 80
    - 授权给已知协议 → 40
    - 授权给未知合约 → 50
    - setApprovalForAll → 60
    """

    name: str = "token_approval_detector"
    label: str = "ERC20 授权检测"
    description: str = "检测可疑的 ERC20 token 授权"
    icon: str = "\U0001f512"
    color: str = "#f97316"

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "threshold": {"type": "number", "minimum": 0, "maximum": 100, "default": 50},
                "check_approval_to_unknown": {"type": "boolean", "default": True},
                "check_infinite_approval": {"type": "boolean", "default": True},
            },
        }

    @classmethod
    def get_default_config(cls) -> dict[str, Any]:
        return {
            "threshold": 50,
            "check_approval_to_unknown": True,
            "check_infinite_approval": True,
        }

    @staticmethod
    def _parse_approval(input_data: str) -> dict[str, Any] | None:
        if not input_data or len(input_data) < 10:
            return None
        method_sig = input_data[:10].lower()
        if method_sig not in APPROVAL_METHOD_SIGS:
            return None
        try:
            if method_sig == "0x095ea7b3":
                return {"method": "approve", "spender": "0x" + input_data[34:74],
                        "amount": int(input_data[74:], 16) if len(input_data) > 74 else 0}
            elif method_sig == "0x23b872dd":
                return {"method": "transferFrom", "from": "0x" + input_data[34:74],
                        "to": "0x" + input_data[98:138],
                        "amount": int(input_data[138:], 16) if len(input_data) > 138 else 0}
            elif method_sig == "0xa22cb465":
                return {"method": "setApprovalForAll", "operator": "0x" + input_data[34:74],
                        "approved": input_data[136:138] == "01"}
        except Exception:
            pass
        return None

    @staticmethod
    def _is_infinite_approval(amount: int) -> bool:
        return amount >= MAX_UINT256 * 0.99

    async def detect(self, context: dict[str, Any]) -> tuple[float, dict[str, Any]]:
        input_data = context.get("input_data", "")
        approval = self._parse_approval(input_data)

        if not approval:
            return 0.0, {"error": "not an approval transaction"}

        issues: list[str] = []
        score = 0.0

        method = approval.get("method")
        if method in ("approve", "transferFrom"):
            spender = approval.get("spender") or approval.get("to", "")
            amount = approval.get("amount", 0)

            if self.config.get("check_infinite_approval", True) and self._is_infinite_approval(amount):
                issues.append("INFINITE_APPROVAL")
                score = max(score, 80)

            if spender.lower() in SUSPICIOUS_APPROVAL_TARGETS:
                issues.append(f"APPROVAL_TO_KNOWN_PROTOCOL:{SUSPICIOUS_APPROVAL_TARGETS[spender.lower()]}")
                score = max(score, 40)
            elif self.config.get("check_approval_to_unknown", True):
                issues.append("APPROVAL_TO_UNKNOWN_CONTRACT")
                score = max(score, 50)

        elif method == "setApprovalForAll":
            if approval.get("approved"):
                operator = approval.get("operator", "")
                if operator.lower() in SUSPICIOUS_APPROVAL_TARGETS:
                    issues.append(f"APPROVAL_FOR_ALL_KNOWN:{SUSPICIOUS_APPROVAL_TARGETS[operator.lower()]}")
                    score = max(score, 50)
                else:
                    issues.append("APPROVAL_FOR_ALL_UNKNOWN")
                    score = max(score, 60)

        labels = issues if score >= self.config.get("threshold", 50) else []
        return score, {
            "method": method,
            "approval_info": approval,
            "detected_issues": issues,
            "labels": labels,
        }


NodeRegistry.register(TokenApprovalDetector)
