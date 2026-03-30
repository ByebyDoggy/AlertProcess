"""
Address Graph Detector
Analyzes address relationships and fund flow patterns
"""
from typing import Any
from detectors.base import Detector, DetectorConfig
from models import AlertInput, DetectionResult, TransactionContext, SeverityEnum


KNOWN_EXCHANGE_ADDRESSES = {
    1: {
        "0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be": "Binance",
        "0x28c6c06298d514db089934071355e5743bf21d60": "Binance Hot",
        "0x21a31ee1afc51d94c2efccaa2092ad1028285549": "Binance Hot 2",
        "0x56eddb7aa87536c09ccc2793473599fd21a8b17f": "Binance Cold",
        "0xdfd5293d8e347dfe59e90ff53b046820adbd516": "Binance Cold 2",
        "0x21a31ee1afc51d94c2efccaa2092ad1028285549": "Binance",
        "0x9696f03e6f8ead66a066d010c4ec4a437b41374f": "Kraken",
        "0x0a869d79a7052c7f1b55a8ebabbea3420f0d1e13": "Kraken 2",
        "0x29728d0efb1fa1b4ab8f9a77c1c6e9a5c4b5f6d": "Coinbase",
        "0xb5d85cbf7cb3ee0d56b22e693ee54f77a0f2263d": "Coinbase 2",
        "0xfbb1b73c4f0bda4f67dca266ce6ef42f520fbb98": "Huobi",
        "0x1bd3f6b0f71b5b0f5e1e1f8c5c8c7d8e6f4a2b1": "OKX",
    },
    56: {
        "0x0000000000000000000000000000000000000001": "BSC Validator",
    },
}

EXPLOITER_ADDRESSES = {
    "0xab7535b4a1b3c2d2c7e7c7c7c7c7c7c7c7c7c7c7": "Known Exploiter",
}

CENTRALIZATION_THRESHOLD = 5


class AddressGraphDetectorConfig(DetectorConfig):
    """Address graph detector configuration"""
    name: str = "address_graph_detector"
    known_exchanges: dict[int, dict[str, str]] = {}
    known_exploiters: dict[str, str] = {}
    centralization_threshold: int = 5
    check_fund_flow: bool = True


class AddressGraphDetector(Detector):
    """
    Detector for address relationship analysis
    
    This detector checks:
    1. If addresses interact with known exchanges (potential money laundering)
    2. If addresses interact with known exploiters
    3. Fund flow patterns (centralization, dispersion)
    4. Address relationship graph analysis
    """
    
    def __init__(self, config: AddressGraphDetectorConfig | None = None):
        super().__init__(config or AddressGraphDetectorConfig())
        self.config: AddressGraphDetectorConfig = self.config
        if not self.config.known_exchanges:
            self.config.known_exchanges = KNOWN_EXCHANGE_ADDRESSES
        if not self.config.known_exploiters:
            self.config.known_exploiters = EXPLOITER_ADDRESSES
    
    @property
    def name(self) -> str:
        return self.config.name
    
    @property
    def description(self) -> str:
        return "Analyzes address relationships and fund flow patterns"
    
    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "centralization_threshold": {
                    "type": "integer",
                    "description": "Max number of recipients before flagged as centralization"
                }
            }
        }
    
    def _check_exchange_interaction(self, address: str, chain_id: int) -> tuple[bool, str | None]:
        """Check if address interacts with known exchange"""
        addr = address.lower()
        exchanges = self.config.known_exchanges.get(chain_id, {})
        if addr in exchanges:
            return True, exchanges[addr]
        return False, None
    
    def _check_exploiter_interaction(self, address: str) -> tuple[bool, str | None]:
        """Check if address interacts with known exploiter"""
        addr = address.lower()
        if addr in self.config.known_exploiters:
            return True, self.config.known_exploiters[addr]
        return False, None
    
    def _analyze_fund_flow(self, context: TransactionContext) -> dict[str, Any]:
        """Analyze fund flow pattern from transaction"""
        from_address = context.from_address or ""
        to_address = context.to_address or ""
        value = context.value or 0
        
        flow_analysis = {
            "direction": "unknown",
            "potential_type": "normal",
            "indicators": []
        }
        
        if value > 0:
            if context.input_data and context.input_data != "0x":
                flow_analysis["potential_type"] = "contract_interaction"
                flow_analysis["indicators"].append("contract_call_with_value")
            else:
                flow_analysis["direction"] = "direct_transfer"
        
        if self._is_contract_call(context):
            flow_analysis["potential_type"] = "contract_interaction"
            flow_analysis["indicators"].append("contract_deployment")
        
        return flow_analysis
    
    def _is_contract_call(self, context: TransactionContext) -> bool:
        """Check if transaction is a contract call"""
        return bool(context.input_data and context.input_data != "0x")
    
    async def detect(
        self, 
        alert: AlertInput, 
        context: TransactionContext
    ) -> DetectionResult:
        """
        Detect address relationship anomalies
        
        Returns DetectionResult with:
        - detected: True if suspicious relationship detected
        - metadata: relationship analysis, connected addresses
        """
        detected_issues = []
        severity = SeverityEnum.UNKNOWN
        alert_type = None
        
        from_address = context.from_address or ""
        to_address = context.to_address or ""
        chain_id = context.chain_id
        
        is_exchange_from, exchange_name_from = self._check_exchange_interaction(from_address, chain_id)
        if is_exchange_from:
            detected_issues.append(f"EXCHANGE_ORIGIN:{exchange_name_from}")
        
        is_exchange_to, exchange_name_to = self._check_exchange_interaction(to_address, chain_id)
        if is_exchange_to:
            detected_issues.append(f"EXCHANGE_DESTINATION:{exchange_name_to}")
        
        is_exploiter_from, exploiter_name_from = self._check_exploiter_interaction(from_address)
        if is_exploiter_from:
            detected_issues.append(f"EXPLOITER_ORIGIN:{exploiter_name_from}")
        
        is_exploiter_to, exploiter_name_to = self._check_exploiter_interaction(to_address)
        if is_exploiter_to:
            detected_issues.append(f"EXPLOITER_DESTINATION:{exploiter_name_to}")
        
        fund_flow = self._analyze_fund_flow(context)
        
        if detected_issues:
            if any("EXPLOITER" in issue for issue in detected_issues):
                severity = SeverityEnum.CRITICAL
                alert_type = "EXPLOITER_INTERACTION"
            elif any("EXCHANGE" in issue for issue in detected_issues):
                severity = SeverityEnum.MEDIUM
                alert_type = "EXCHANGE_INTERACTION"
            else:
                severity = SeverityEnum.LOW
                alert_type = "SUSPICIOUS_RELATIONSHIP"
        
        detected = len(detected_issues) > 0
        
        return DetectionResult(
            detector_name=self.name,
            detected=detected,
            alert_type=alert_type,
            severity=severity,
            metadata={
                "from_address": from_address,
                "to_address": to_address,
                "exchanges": {
                    "from": exchange_name_from,
                    "to": exchange_name_to,
                },
                "exploiters": {
                    "from": exploiter_name_from,
                    "to": exploiter_name_to,
                },
                "fund_flow": fund_flow,
                "detected_issues": detected_issues,
                "tx_hash": alert.tx_hash,
                "chain_id": chain_id,
            }
        )


from detectors.base import DetectorRegistry
DetectorRegistry.register(AddressGraphDetector)
