"""
Flash Loan Detector
Detects flash loan attacks and suspicious flash loan patterns
"""
from typing import Any
from detectors.base import Detector, DetectorConfig
from models import AlertInput, DetectionResult, TransactionContext, SeverityEnum
from web3 import Web3


KNOWN_FLASH_LOAN_PROTOCOLS = {
    # Aave
    "0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9": "Aave V2",
    "0x879a82308338eca4296a55a4e63684f070d6832": "Aave V2",
    "0x794a61358d6845594f94dc1db02a252b5b4814aa": "Aave V3",
    # dYdX
    "0x1e0447b19bb6ecfdae1e4ae1694b0c3659614e4e": "dYdX",
    # Uniswap V2 (callback)
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": "Uniswap V3",
    # Compound
    "0x3d9819210a31b4961b30ef54be2aed79b9c9cd3b": "Compound",
    # Cream
    "0x780f305874fc8f5d3fc5c4d7c0a89bf8092f2b8f": "Cream",
    # Balancer
    "0xba12222222228d8ba445958a75a0704d566bf2c8": "Balancer",
    # Yearn
    "0x1fa71f4db46a5d4f6c5f5a5f5f5f5f5f5f5f5f5f": "Yearn",
}

FLASH_LOAN_METHOD_SIGS = {
    "0x0906f8c8": "flash",           # Aave flash loan
    "0x5c7d2920": "flashLoan",       # dYdX flash loan
    "0x016602d8": "flashswap",        # Uniswap flash swap
    "0xab9c4b5d": "initiateFlashLoan", # Generic flash loan
}


class FlashLoanDetectorConfig(DetectorConfig):
    """Flash loan detector configuration"""
    name: str = "flash_loan_detector"
    large_flash_loan_threshold_usd: float = 100000.0
    flash_loan_protocols: dict[str, str] = {}
    chain_id_to_native_token_price: dict[int, float] = {
        1: 2000.0,
        56: 300.0,
        137: 1.0,
    }


class FlashLoanDetector(Detector):
    """
    Detector for flash loan attacks
    
    This detector checks:
    1. If the transaction interacts with known flash loan protocols
    2. If the transaction has unusually large value for flash loan
    3. If the transaction has flash loan method signatures
    """
    
    def __init__(self, config: FlashLoanDetectorConfig | None = None):
        super().__init__(config or FlashLoanDetectorConfig())
        self.config: FlashLoanDetectorConfig = self.config
        if not self.config.flash_loan_protocols:
            self.config.flash_loan_protocols = KNOWN_FLASH_LOAN_PROTOCOLS
    
    @property
    def name(self) -> str:
        return self.config.name
    
    @property
    def description(self) -> str:
        return "Detects flash loan attacks and suspicious flash loan patterns"
    
    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "large_flash_loan_threshold_usd": {
                    "type": "number",
                    "description": "Threshold in USD for large flash loan detection"
                },
                "flash_loan_protocols": {
                    "type": "object",
                    "description": "Known flash loan protocol addresses"
                }
            }
        }
    
    def _detect_flash_loan_method(self, input_data: str) -> bool:
        """Check if input data contains flash loan method signature"""
        if not input_data or input_data == "0x":
            return False
        method_sig = input_data[:10].lower()
        return method_sig in FLASH_LOAN_METHOD_SIGS
    
    def _get_protocol_name(self, address: str) -> str | None:
        """Get protocol name from address"""
        addr = address.lower()
        if addr in self.config.flash_loan_protocols:
            return self.config.flash_loan_protocols[addr]
        return None
    
    async def detect(
        self, 
        alert: AlertInput, 
        context: TransactionContext
    ) -> DetectionResult:
        """
        Detect flash loan patterns
        
        Returns DetectionResult with:
        - detected: True if flash loan pattern detected
        - metadata: protocol, value, method, etc.
        """
        detected_issues = []
        severity = SeverityEnum.UNKNOWN
        alert_type = None
        
        to_address = context.to_address or ""
        from_address = context.from_address or ""
        input_data = context.input_data or ""
        value = context.value or 0
        
        protocol = self._get_protocol_name(to_address)
        if protocol:
            detected_issues.append(f"KNOWN_FLASH_LOAN_PROTOCOL:{protocol}")
        
        if self._detect_flash_loan_method(input_data):
            detected_issues.append("FLASH_LOAN_METHOD_SIGNATURE")
        
        native_price = self.config.chain_id_to_native_token_price.get(
            context.chain_id, 0
        )
        value_usd = (value / 10**18) * native_price
        
        if value_usd > self.config.large_flash_loan_threshold_usd:
            detected_issues.append(f"LARGE_FLASH_LOAN:${value_usd:,.0f}")
            if protocol:
                severity = SeverityEnum.CRITICAL
                alert_type = "LARGE_FLASH_LOAN_ATTACK"
            else:
                severity = SeverityEnum.HIGH
                alert_type = "LARGE_FLASH_LOAN"
        
        if len(detected_issues) > 0 and severity == SeverityEnum.UNKNOWN:
            severity = SeverityEnum.MEDIUM
            alert_type = "FLASH_LOAN_DETECTED"
        
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
                "value_usd": value_usd,
                "protocol": protocol,
                "has_flash_loan_method": self._detect_flash_loan_method(input_data),
                "detected_issues": detected_issues,
                "tx_hash": alert.tx_hash,
                "chain_id": context.chain_id
            }
        )


from detectors.base import DetectorRegistry
DetectorRegistry.register(FlashLoanDetector)
