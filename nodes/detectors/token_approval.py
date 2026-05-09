"""ERC20 授权检测器 — 迁移到新节点架构"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from nodes.base import NodeRegistry
from nodes.detectors.base import BaseDetector, DetectorConfigMixin, DetectorOutputMixin
from nodes.models import TransactionContext

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


class TokenApprovalOutput(DetectorOutputMixin):
    """ERC20 授权检测器输出"""
    pass


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

    # ── Pydantic 配置模型 (继承 DetectorConfigMixin，包含共享的 threshold) ──
    class ConfigModel(DetectorConfigMixin):
        check_approval_to_unknown: bool = Field(default=True, description="检测向未知合约授权")
        check_infinite_approval: bool = Field(default=True, description="检测无限授权")

    label: str = "ERC20 授权检测"
    description: str = "[数据需求: 仅交易基础字段] 检测危险的 ERC20 授权操作：无限授权 approve(MAX_UINT256) 给 80 分、setApprovalForAll 60 分、授权给未知合约 50 分。是识别盗币/钓鱼攻击前兆的关键检测器"
    icon: str = "\U0001f512"
    color: str = "#f97316"

    # ── Pydantic 输出模型 ──
    OutputModel: type = TokenApprovalOutput

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

    async def process(self, tx_context: TransactionContext) -> TokenApprovalOutput:
        input_data = tx_context.input_data or tx_context.extra.get("input_data", "")
        approval = self._parse_approval(input_data)

        if not approval:
            return TokenApprovalOutput(
                score=0.0, passed=True, severity="UNKNOWN", labels=[],
                detection={"error": "not an approval transaction"}
            )

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
        threshold = self.config.get("threshold", 50.0)
        from nodes.base import score_to_severity
        return TokenApprovalOutput(
            score=score, passed=score >= threshold, severity=score_to_severity(score),
            labels=labels,
            detection={
                "method": method,
                "approval_info": approval,
                "detected_issues": issues,
                "labels": labels,
            },
        )


NodeRegistry.register(TokenApprovalDetector)
