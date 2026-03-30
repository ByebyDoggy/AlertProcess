"""
Gas Price Detector
Detects suspiciously high gas prices in transactions
"""
from typing import Any
from pydantic import BaseModel
from detectors.base import Detector, DetectorConfig
from models import AlertInput, DetectionResult, TransactionContext, SeverityEnum


class GasPriceDetectorConfig(DetectorConfig):
    """Gas price detector configuration"""
    name: str = "gas_price_detector"
    threshold_usd: float = 100.0  # Gas price threshold in USD
    chain_id_to_native_token_price: dict[int, float] = {
        1: 2000.0,    # ETH
        56: 700.0,    # BNB
        137: 1.0,     # MATIC
    }


class GasPriceDetector(Detector):
    """
    Detector for suspicious gas prices
    
    This detector checks if the transaction's gas price is abnormally high,
    which could indicate unusual network activity or urgency.
    """
    
    def __init__(self, config: GasPriceDetectorConfig | None = None):
        super().__init__(config or GasPriceDetectorConfig())
        self.config: GasPriceDetectorConfig = self.config
    
    @property
    def name(self) -> str:
        return self.config.name
    
    @property
    def description(self) -> str:
        return "Detects transactions with suspiciously high gas prices"
    
    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "threshold_usd": {
                    "type": "number",
                    "description": "Gas price threshold in USD",
                    "default": 100.0
                },
                "chain_id_to_native_token_price": {
                    "type": "object",
                    "description": "Native token prices by chain ID for USD conversion"
                }
            }
        }
    
    async def detect(
        self, 
        alert: AlertInput, 
        context: TransactionContext
    ) -> DetectionResult:
        """
        Detect high gas price
        
        Returns DetectionResult with:
        - detected: True if gas price exceeds threshold
        - metadata: gas price details
        """
        if context.gas_price is None:
            return DetectionResult(
                detector_name=self.name,
                detected=False,
                alert_type="gas_price_check",
                severity=SeverityEnum.UNKNOWN,
                metadata={"error": "gas_price not available in context"}
            )
        
        # Calculate gas price in USD
        native_token_price = self.config.chain_id_to_native_token_price.get(
            context.chain_id, 0
        )
        gas_price_in_eth = context.gas_price / 10**18
        gas_price_in_usd = gas_price_in_eth * native_token_price
        
        detected = gas_price_in_usd > self.config.threshold_usd
        
        return DetectionResult(
            detector_name=self.name,
            detected=detected,
            alert_type="HIGH_GAS_PRICE" if detected else None,
            severity=SeverityEnum.HIGH if detected else SeverityEnum.UNKNOWN,
            metadata={
                "gas_price_wei": context.gas_price,
                "gas_price_eth": gas_price_in_eth,
                "gas_price_usd": gas_price_in_usd,
                "threshold_usd": self.config.threshold_usd,
                "chain_id": context.chain_id,
                "native_token_price": native_token_price,
                "tx_hash": context.tx_hash
            }
        )


# Auto-register detector
from detectors.base import DetectorRegistry
DetectorRegistry.register(GasPriceDetector)
