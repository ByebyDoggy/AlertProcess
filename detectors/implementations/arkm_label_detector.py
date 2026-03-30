"""
ARKM Label Detector
Detects malicious entity labels for addresses using ARKM Intelligence API
"""
from typing import Any
from detectors.base import Detector, DetectorConfig
from models import AlertInput, DetectionResult, TransactionContext, SeverityEnum
from arkm import AsyncArkmClient, SyncArkmClient
from database.models import ContractAddressDB, SessionLocal
from datetime import datetime


ChainIDToARKMNetwork = {
    1: "ethereum",
    56: "bsc",
    137: "polygon",
}


class ARKMLabelDetectorConfig(DetectorConfig):
    """ARKM Label detector configuration"""
    name: str = "arkm_label_detector"
    arkm_cookie: str = ""
    blacklist_entity_types: list[str] = ['hacker']
    ignored_entity_types: list[str] = []


class ARKMLabelDetector(Detector):
    """
    Detector for ARKM entity label analysis
    
    This detector checks:
    1. If the address is labeled as a hacker/malicious entity in ARKM
    2. If the address belongs to a trusted entity
    """
    
    def __init__(self, config: ARKMLabelDetectorConfig | None = None):
        super().__init__(config or ARKMLabelDetectorConfig())
        self.config: ARKMLabelDetectorConfig = self.config
        self.arkm_client = AsyncArkmClient(cookie=self.config.arkm_cookie) if self.config.arkm_cookie else None
        self.arkm_sync_client = SyncArkmClient(cookie=self.config.arkm_cookie) if self.config.arkm_cookie else None
    
    @property
    def name(self) -> str:
        return self.config.name
    
    @property
    def description(self) -> str:
        return "Detects malicious entity labels using ARKM Intelligence"
    
    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "blacklist_entity_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Entity types considered malicious"
                },
                "ignored_entity_types": {
                    "type": "array", 
                    "items": {"type": "string"},
                    "description": "Entity types to ignore (trusted)"
                }
            }
        }
    
    def _get_entity_type_from_db(self, address: str) -> tuple[str | None, int | None]:
        """Get cached entity type from local database"""
        db = SessionLocal()
        try:
            entity = db.query(ContractAddressDB).filter(
                ContractAddressDB.contract_address == address
            ).first()
            if entity:
                return entity.entity_type, entity.chain_id
            return None, None
        finally:
            db.close()
    
    def _save_to_db(self, address: str, chain_id: int, entity_type: str | None, 
                    entity_id: str | None = None, entity_name: str | None = None):
        """Save entity info to local database"""
        db = SessionLocal()
        try:
            existing = db.query(ContractAddressDB).filter(
                ContractAddressDB.contract_address == address
            ).first()
            if existing:
                if entity_type:
                    existing.entity_type = entity_type
                if entity_id:
                    existing.entity_id = entity_id
                if entity_name:
                    existing.entity_name = entity_name
            else:
                db.add(ContractAddressDB(
                    contract_address=address,
                    chain_id=chain_id,
                    entity_id=entity_id,
                    entity_type=entity_type,
                    entity_name=entity_name,
                ))
            db.commit()
        finally:
            db.close()
    
    def _fetch_arkm_entity_type(self, address: str, chain_id: int) -> tuple[str | None, str | None, str | None]:
        """Fetch entity type from ARKM API"""
        if not self.arkm_sync_client:
            return None, None, None
        
        arkm_network = ChainIDToARKMNetwork.get(chain_id)
        if not arkm_network:
            return None, None, None
        
        try:
            response = self.arkm_sync_client.get(
                path=f"/intelligence/address_enriched/{address}/all?includeTags=true&includeEntityPredictions=true&includeClusters=true"
            )
            
            chain_data = response.get(arkm_network, {})
            arkm_entity = chain_data.get("arkhamEntity", {})
            
            entity_type = arkm_entity.get("type")
            entity_id = arkm_entity.get("id")
            entity_name = arkm_entity.get("name")
            
            return entity_type, entity_id, entity_name
        except Exception:
            return None, None, None
    
    async def detect(
        self, 
        alert: AlertInput, 
        context: TransactionContext
    ) -> DetectionResult:
        """
        Detect entity labels
        
        Returns DetectionResult with:
        - detected: True if address is tagged as malicious
        - metadata: entity type, tags, etc.
        """
        # Check for exploiter (attacker) address
        exploiter_address = alert.exploiter_address or context.from_address
        if not exploiter_address:
            return DetectionResult(
                detector_name=self.name,
                detected=False,
                alert_type="no_exploiter_address",
                severity=SeverityEnum.UNKNOWN,
                metadata={"error": "No exploiter address available"}
            )
        
        entity_type = None
        entity_id = None
        entity_name = None
        
        # Try cache first
        cached_type, cached_chain = self._get_entity_type_from_db(exploiter_address)
        if cached_type:
            entity_type = cached_type
        else:
            # Fetch from ARKM
            entity_type, entity_id, entity_name = self._fetch_arkm_entity_type(
                exploiter_address, alert.chain_id
            )
            # Save to DB
            if entity_type:
                self._save_to_db(exploiter_address, alert.chain_id, entity_type, entity_id, entity_name)
        
        # Determine detection result
        detected = False
        severity = SeverityEnum.UNKNOWN
        alert_type = None
        
        if entity_type:
            if entity_type in self.config.blacklist_entity_types:
                detected = True
                severity = SeverityEnum.CRITICAL
                alert_type = "MALICIOUS_ENTITY"
            elif entity_type not in self.config.ignored_entity_types:
                detected = True
                severity = SeverityEnum.LOW
                alert_type = "KNOWN_ENTITY"
        
        return DetectionResult(
            detector_name=self.name,
            detected=detected,
            alert_type=alert_type,
            severity=severity,
            metadata={
                "address": exploiter_address,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "entity_name": entity_name,
                "chain_id": alert.chain_id,
                "is_blacklisted": entity_type in self.config.blacklist_entity_types if entity_type else False,
                "tx_hash": alert.tx_hash
            }
        )


from detectors.base import DetectorRegistry
DetectorRegistry.register(ARKMLabelDetector)
