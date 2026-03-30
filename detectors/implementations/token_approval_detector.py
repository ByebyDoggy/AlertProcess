"""
Token Approval Detector
Detects suspicious ERC20 token approvals
"""
from typing import Any
from detectors.base import Detector, DetectorConfig
from models import AlertInput, DetectionResult, TransactionContext, SeverityEnum


MAX_UINT256 = 115792089237316195423570985008687907853269984665640564039457584007913129639935

APPROVAL_METHOD_SIGS = {
    "0x095ea7b3": "approve",
    "0x23b872dd": "transferFrom",
    "0xa22cb465": "setApprovalForAll",
}

SUSPICIOUS_APPROVAL_TARGETS = {
    "0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9": "Aave V2",
    "0x794a61358d6845594f94dc1db02a252b5b4814aa": "Aave V3",
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": "Uniswap V3",
    "0xe592427a0aece92de3edee1f18e0157c05861564": "Uniswap V3 Router",
    "0xdef1c0ded9bec7f1a1670819833240f027b25eff": "0x Router",
}

UNKNOWN_CONTRACT_RISK_SCORE = 0.3


class TokenApprovalDetectorConfig(DetectorConfig):
    """Token approval detector configuration"""
    name: str = "token_approval_detector"
    infinite_approval_threshold: int = MAX_UINT256
    check_approval_to_unknown: bool = True
    check_infinite_approval: bool = True


class TokenApprovalDetector(Detector):
    """
    Detector for suspicious token approvals
    
    This detector checks:
    1. Infinite approvals (approval for max uint256)
    2. Approvals to unknown/suspicious contracts
    3. Unusual approval amounts
    """
    
    def __init__(self, config: TokenApprovalDetectorConfig | None = None):
        super().__init__(config or TokenApprovalDetectorConfig())
        self.config: TokenApprovalDetectorConfig = self.config
    
    @property
    def name(self) -> str:
        return self.config.name
    
    @property
    def description(self) -> str:
        return "Detects suspicious ERC20 token approvals"
    
    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "check_approval_to_unknown": {
                    "type": "boolean",
                    "description": "Flag approvals to unknown contracts"
                },
                "check_infinite_approval": {
                    "type": "boolean",
                    "description": "Flag infinite approvals"
                }
            }
        }
    
    def _parse_approval(self, input_data: str) -> dict | None:
        """Parse approval function call from input data"""
        if not input_data or len(input_data) < 10:
            return None
        
        method_sig = input_data[:10].lower()
        if method_sig not in APPROVAL_METHOD_SIGS:
            return None
        
        try:
            if method_sig == "0x095ea7b3":
                return {
                    "method": "approve",
                    "spender": "0x" + input_data[34:74],
                    "amount": int(input_data[74:], 16) if len(input_data) > 74 else 0
                }
            elif method_sig == "0x23b872dd":
                return {
                    "method": "transferFrom",
                    "from": "0x" + input_data[34:74],
                    "to": "0x" + input_data[98:138],
                    "amount": int(input_data[138:], 16) if len(input_data) > 138 else 0
                }
            elif method_sig == "0xa22cb465":
                return {
                    "method": "setApprovalForAll",
                    "operator": "0x" + input_data[34:74],
                    "approved": input_data[138:139] == "1"
                }
        except Exception:
            pass
        
        return None
    
    def _is_infinite_approval(self, amount: int) -> bool:
        """Check if approval amount is infinite or very large"""
        if amount >= self.config.infinite_approval_threshold:
            return True
        if amount > MAX_UINT256 * 0.99:
            return True
        return False
    
    def _is_suspicious_target(self, address: str) -> tuple[bool, str | None]:
        """Check if approval target is suspicious"""
        addr = address.lower()
        if addr in SUSPICIOUS_APPROVAL_TARGETS:
            return True, SUSPICIOUS_APPROVAL_TARGETS[addr]
        return False, None
    
    async def detect(
        self, 
        alert: AlertInput, 
        context: TransactionContext
    ) -> DetectionResult:
        """
        Detect suspicious token approvals
        
        Returns DetectionResult with:
        - detected: True if suspicious approval detected
        - metadata: approval details, risk factors
        """
        detected_issues = []
        severity = SeverityEnum.UNKNOWN
        alert_type = None
        
        input_data = context.input_data or ""
        
        approval_info = self._parse_approval(input_data)
        
        if not approval_info:
            return DetectionResult(
                detector_name=self.name,
                detected=False,
                alert_type=None,
                severity=SeverityEnum.UNKNOWN,
                metadata={"tx_hash": alert.tx_hash}
            )
        
        method = approval_info.get("method")
        
        if method in ("approve", "transferFrom"):
            spender = approval_info.get("spender") or approval_info.get("to")
            amount = approval_info.get("amount", 0)
            
            if self.config.check_infinite_approval and self._is_infinite_approval(amount):
                detected_issues.append("INFINITE_APPROVAL")
            
            is_suspicious, protocol_name = self._is_suspicious_target(spender)
            if is_suspicious:
                detected_issues.append(f"APPROVAL_TO_KNOWN_PROTocol:{protocol_name}")
            
            if self.config.check_approval_to_unknown and not is_suspicious:
                detected_issues.append("APPROVAL_TO_UNKNOWN_CONTRACT")
        
        elif method == "setApprovalForAll":
            operator = approval_info.get("operator")
            approved = approval_info.get("approved", False)
            
            if approved:
                is_suspicious, protocol_name = self._is_suspicious_target(operator)
                if is_suspicious:
                    detected_issues.append(f"APPROVAL_FOR_ALL_KNOWN:{protocol_name}")
                else:
                    detected_issues.append("APPROVAL_FOR_ALL_UNKNOWN")
        
        if detected_issues:
            if "INFINITE_APPROVAL" in detected_issues:
                severity = SeverityEnum.HIGH
                alert_type = "INFINITE_APPROVAL"
            elif "APPROVAL_TO_UNKNOWN_CONTRACT" in detected_issues or "APPROVAL_FOR_ALL_UNKNOWN" in detected_issues:
                severity = SeverityEnum.MEDIUM
                alert_type = "APPROVAL_TO_UNKNOWN"
            else:
                severity = SeverityEnum.LOW
                alert_type = "APPROVAL_DETECTED"
        
        detected = len(detected_issues) > 0
        
        return DetectionResult(
            detector_name=self.name,
            detected=detected,
            alert_type=alert_type,
            severity=severity,
            metadata={
                "method": method,
                "approval_info": approval_info,
                "detected_issues": detected_issues,
                "tx_hash": alert.tx_hash,
                "chain_id": context.chain_id,
                "from_address": context.from_address,
                "to_address": context.to_address,
            }
        )


from detectors.base import DetectorRegistry
DetectorRegistry.register(TokenApprovalDetector)
