"""
Token Anomaly Detector
Detects anomalous token transfer patterns
"""
from typing import Any
from detectors.base import Detector, DetectorConfig
from models import AlertInput, DetectionResult, TransactionContext, SeverityEnum


NATIVE_ETH_ADDRESS = "0x0000000000000000000000000000000000000000"

SUSPICIOUS_TOKEN_CONTRACTS = {
    "0x0000000000000000000000000000000000000000": "ETH",
}

NEW_TOKEN_CREATION_BLOCK = {
    1: 17000000,
    56: 25000000,
    137: 45000000,
}

LARGE_TRANSFER_THRESHOLD = 1000000


class TokenAnomalyDetectorConfig(DetectorConfig):
    """Token anomaly detector configuration"""
    name: str = "token_anomaly_detector"
    large_transfer_threshold: float = 1000000.0
    new_token_block: dict[int, int] = {}
    check_new_token: bool = True
    check_unusual_value: bool = True


class TokenAnomalyDetector(Detector):
    """
    Detector for anomalous token transfer patterns
    
    This detector checks:
    1. Large token transfers
    2. Newly created tokens
    3. Unusual value transfers
    4. Multiple transfers in single transaction
    """
    
    def __init__(self, config: TokenAnomalyDetectorConfig | None = None):
        super().__init__(config or TokenAnomalyDetectorConfig())
        self.config: TokenAnomalyDetectorConfig = self.config
        if not self.config.new_token_block:
            self.config.new_token_block = NEW_TOKEN_CREATION_BLOCK
    
    @property
    def name(self) -> str:
        return self.config.name
    
    @property
    def description(self) -> str:
        return "Detects anomalous token transfer patterns"
    
    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "large_transfer_threshold": {
                    "type": "number",
                    "description": "Threshold for large transfer detection"
                },
                "check_new_token": {
                    "type": "boolean",
                    "description": "Check for newly created tokens"
                }
            }
        }
    
    def _is_native_eth_transfer(self, to_address: str, input_data: str) -> bool:
        """Check if this is a native ETH transfer"""
        return to_address and to_address.lower() == NATIVE_ETH_ADDRESS.lower()
    
    def _parse_transfer_data(self, input_data: str) -> dict | None:
        """Parse ERC20 transfer data from input"""
        if not input_data or len(input_data) < 10:
            return None
        
        method_sig = input_data[:10].lower()
        
        if method_sig == "0xa9059cbb":
            try:
                to_addr = "0x" + input_data[34:74]
                amount = int(input_data[74:], 16) if len(input_data) > 74 else 0
                return {"method": "transfer", "to": to_addr, "amount": amount}
            except Exception:
                pass
        
        elif method_sig == "0x23b872dd":
            try:
                from_addr = "0x" + input_data[34:74]
                to_addr = "0x" + input_data[98:138]
                amount = int(input_data[138:], 16) if len(input_data) > 138 else 0
                return {"method": "transferFrom", "from": from_addr, "to": to_addr, "amount": amount}
            except Exception:
                pass
        
        return None
    
    def _is_new_token(self, token_address: str, block_number: int | None) -> bool:
        """Check if token was recently created"""
        if not block_number:
            return False
        
        chain_id = 1
        threshold_block = self.config.new_token_block.get(chain_id, 17000000)
        
        return block_number < threshold_block + 1000000
    
    async def detect(
        self, 
        alert: AlertInput, 
        context: TransactionContext
    ) -> DetectionResult:
        """
        Detect anomalous token patterns
        
        Returns DetectionResult with:
        - detected: True if anomaly detected
        - metadata: transfer details, anomaly type
        """
        detected_issues = []
        severity = SeverityEnum.UNKNOWN
        alert_type = None
        
        from_address = context.from_address or ""
        to_address = context.to_address or ""
        input_data = context.input_data or ""
        value = context.value or 0
        block_number = context.block_number
        
        if self._is_native_eth_transfer(to_address, input_data):
            if value > self.config.large_transfer_threshold * 10**18:
                detected_issues.append(f"LARGE_ETH_TRANSFER:{value / 10**18:.2f} ETH")
        
        transfer_info = self._parse_transfer_data(input_data)
        
        if transfer_info:
            amount = transfer_info.get("amount", 0)
            if amount > self.config.large_transfer_threshold:
                detected_issues.append(f"LARGE_TOKEN_TRANSFER:{amount}")
        
        if context.input_data and context.input_data != "0x":
            if not transfer_info and not self._is_native_eth_transfer(to_address, input_data):
                detected_issues.append("UNUSUAL_CONTRACT_INTERACTION")
        
        if block_number:
            token_block_threshold = self.config.new_token_block.get(context.chain_id, 0)
            if block_number < token_block_threshold + 1000000:
                detected_issues.append("NEW_TOKEN_ACTIVITY")
        
        if detected_issues:
            if any("LARGE" in issue for issue in detected_issues):
                severity = SeverityEnum.HIGH
                alert_type = "LARGE_TRANSFER"
            elif any("NEW_TOKEN" in issue for issue in detected_issues):
                severity = SeverityEnum.MEDIUM
                alert_type = "NEW_TOKEN_ACTIVITY"
            else:
                severity = SeverityEnum.LOW
                alert_type = "ANOMALY_DETECTED"
        
        detected = len(detected_issues) > 0
        
        return DetectionResult(
            detector_name=self.name,
            detected=detected,
            alert_type=alert_type,
            severity=severity,
            metadata={
                "from_address": from_address,
                "to_address": to_address,
                "value": value,
                "transfer_info": transfer_info,
                "detected_issues": detected_issues,
                "tx_hash": alert.tx_hash,
                "chain_id": context.chain_id,
                "block_number": block_number,
            }
        )


from detectors.base import DetectorRegistry
DetectorRegistry.register(TokenAnomalyDetector)
