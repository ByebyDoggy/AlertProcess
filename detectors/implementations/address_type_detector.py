"""
Address Type Detector
Detects address types (EOA, Contract) and null address transactions
"""
from typing import Any
from pydantic import BaseModel
from detectors.base import Detector, DetectorConfig
from models import AlertInput, DetectionResult, TransactionContext, SeverityEnum


class AddressTypeDetectorConfig(DetectorConfig):
    """Address type detector configuration"""
    name: str = "address_type_detector"
    null_address: str = "0x0000000000000000000000000000000000000000"
    check_null_to: bool = True
    check_null_from: bool = True
    check_contract_creation: bool = True


class AddressTypeDetector(Detector):
    """
    Detector for address type analysis
    
    This detector checks:
    1. If the 'to' address is null (contract creation or mint)
    2. If the 'from' address is null (unlikely but possible)
    3. Contract creation patterns
    """
    
    NULL_ADDRESS = "0x0000000000000000000000000000000000000000"
    
    def __init__(self, config: AddressTypeDetectorConfig | None = None):
        super().__init__(config or AddressTypeDetectorConfig())
        self.config: AddressTypeDetectorConfig = self.config
    
    @property
    def name(self) -> str:
        return self.config.name
    
    @property
    def description(self) -> str:
        return "Detects null address transactions and contract creation patterns"
    
    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "check_null_to": {
                    "type": "boolean",
                    "description": "Check if 'to' address is null"
                },
                "check_null_from": {
                    "type": "boolean", 
                    "description": "Check if 'from' address is null"
                },
                "check_contract_creation": {
                    "type": "boolean",
                    "description": "Check for contract creation patterns"
                }
            }
        }
    
    async def detect(
        self, 
        alert: AlertInput, 
        context: TransactionContext
    ) -> DetectionResult:
        """
        Detect address type issues
        
        Returns DetectionResult with address type analysis
        """
        detected_issues = []
        severity = SeverityEnum.UNKNOWN
        alert_type = None
        
        # Check for null 'to' address (common in contract creation or suspicious mint)
        if self.config.check_null_to and context.to_address:
            if context.to_address.lower() == self.NULL_ADDRESS.lower():
                detected_issues.append("NULL_TO_ADDRESS")
                severity = SeverityEnum.MEDIUM
                alert_type = "NULL_TO_ADDRESS"
        
        # Check for null 'from' address (unusual)
        if self.config.check_null_from and context.from_address:
            if context.from_address.lower() == self.NULL_ADDRESS.lower():
                detected_issues.append("NULL_FROM_ADDRESS")
                severity = SeverityEnum.HIGH
                alert_type = "NULL_FROM_ADDRESS"
        
        # Check for contract creation (to=null with value > 0 or input data)
        if self.config.check_contract_creation:
            if context.to_address and context.to_address.lower() == self.NULL_ADDRESS.lower():
                if context.value and context.value > 0:
                    detected_issues.append("CONTRACT_CREATION_WITH_VALUE")
                    severity = SeverityEnum.HIGH
                    alert_type = "CONTRACT_CREATION_WITH_VALUE"
                elif context.input_data and context.input_data != "0x":
                    detected_issues.append("CONTRACT_CREATION")
                    if severity == SeverityEnum.UNKNOWN:
                        severity = SeverityEnum.LOW
                    alert_type = "CONTRACT_CREATION"
        
        detected = len(detected_issues) > 0
        
        return DetectionResult(
            detector_name=self.name,
            detected=detected,
            alert_type=alert_type,
            severity=severity,
            metadata={
                "from_address": context.from_address,
                "to_address": context.to_address,
                "value": context.value,
                "input_data": context.input_data,
                "is_null_to": context.to_address and context.to_address.lower() == self.NULL_ADDRESS.lower(),
                "is_null_from": context.from_address and context.from_address.lower() == self.NULL_ADDRESS.lower(),
                "detected_issues": detected_issues,
                "tx_hash": context.tx_hash
            }
        )


from detectors.base import DetectorRegistry
DetectorRegistry.register(AddressTypeDetector)
