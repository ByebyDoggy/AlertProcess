"""
Address Age Detector
Detects suspiciously new addresses involved in transactions
"""
from typing import Any
from detectors.base import Detector, DetectorConfig
from models import AlertInput, DetectionResult, TransactionContext, SeverityEnum
from moralis import evm_api
from database.models import ContractAddressDB, SessionLocal
from datetime import datetime
from config import settings


ChainIDToMoralisChain = {
    1: 'eth',
    56: 'bsc',
    137: 'matic',
}


class AddressAgeDetectorConfig(DetectorConfig):
    """Address age detector configuration"""
    name: str = "address_age_detector"
    new_address_threshold_days: int = 7


class AddressAgeDetector(Detector):
    """
    Detector for address age analysis
    
    This detector checks:
    1. When was the address first active on the chain
    2. Newly created addresses get higher risk scores
    """
    
    def __init__(self, config: AddressAgeDetectorConfig | None = None):
        super().__init__(config or AddressAgeDetectorConfig())
        self.config: AddressAgeDetectorConfig = self.config
    
    @property
    def name(self) -> str:
        return self.config.name
    
    @property
    def description(self) -> str:
        return "Detects suspiciously new addresses involved in transactions"
    
    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "new_address_threshold_days": {
                    "type": "integer",
                    "description": "Days threshold for considering an address 'new'"
                }
            }
        }
    
    def _get_cached_create_time(self, address: str, chain_id: int) -> datetime | None:
        """Get cached create time from local database"""
        db = SessionLocal()
        try:
            entity = db.query(ContractAddressDB).filter(
                ContractAddressDB.contract_address == address,
                ContractAddressDB.chain_id == chain_id,
            ).first()
            if entity and entity.address_create_time:
                return entity.address_create_time
            return None
        finally:
            db.close()
    
    def _save_create_time(self, address: str, chain_id: int, create_time: datetime):
        """Save address create time to local database"""
        db = SessionLocal()
        try:
            existing = db.query(ContractAddressDB).filter(
                ContractAddressDB.contract_address == address,
                ContractAddressDB.chain_id == chain_id,
            ).first()
            if existing:
                existing.address_create_time = create_time
            else:
                db.add(ContractAddressDB(
                    contract_address=address,
                    chain_id=chain_id,
                    address_create_time=create_time,
                ))
            db.commit()
        finally:
            db.close()
    
    async def detect(
        self, 
        alert: AlertInput, 
        context: TransactionContext
    ) -> DetectionResult:
        """
        Detect address age
        
        Returns DetectionResult with:
        - detected: True if address is suspiciously new
        - metadata: age in days, create time, etc.
        """
        address = alert.exploiter_address or context.from_address
        if not address:
            return DetectionResult(
                detector_name=self.name,
                detected=False,
                alert_type="no_address",
                severity=SeverityEnum.UNKNOWN,
                metadata={"error": "No address available"}
            )
        
        create_time = self._get_cached_create_time(address, alert.chain_id)
        fetched_from_api = False
        
        if not create_time:
            # Fetch from Moralis
            moralis_chain = ChainIDToMoralisChain.get(alert.chain_id)
            if not moralis_chain or not settings.moralis_api_key:
                return DetectionResult(
                    detector_name=self.name,
                    detected=False,
                    alert_type="no_api_key",
                    severity=SeverityEnum.UNKNOWN,
                    metadata={"error": "No Moralis API key configured"}
                )
            
            try:
                result = evm_api.wallets.get_wallet_active_chains(
                    api_key=settings.moralis_api_key,
                    params={'address': address}
                )
                
                active_chains = result.get('active_chains', [])
                for chain in active_chains:
                    if chain.get('chain') == moralis_chain:
                        first_tx = chain.get('first_transaction')
                        if first_tx:
                            create_time = datetime.fromisoformat(first_tx['block_timestamp'])
                            self._save_create_time(address, alert.chain_id, create_time)
                            fetched_from_api = True
                            break
            except Exception:
                pass
        
        if not create_time:
            return DetectionResult(
                detector_name=self.name,
                detected=False,
                alert_type="no_activity",
                severity=SeverityEnum.UNKNOWN,
                metadata={"address": address, "reason": "No active chain activity found"}
            )
        
        now = datetime.now()
        age_days = (now - create_time).days
        is_new = age_days < self.config.new_address_threshold_days
        
        return DetectionResult(
            detector_name=self.name,
            detected=is_new,
            alert_type="NEW_ADDRESS" if is_new else None,
            severity=SeverityEnum.HIGH if is_new else SeverityEnum.UNKNOWN,
            metadata={
                "address": address,
                "create_time": create_time.isoformat() if create_time else None,
                "age_days": age_days,
                "threshold_days": self.config.new_address_threshold_days,
                "is_new": is_new,
                "fetched_from_api": fetched_from_api,
                "tx_hash": alert.tx_hash
            }
        )


from detectors.base import DetectorRegistry
DetectorRegistry.register(AddressAgeDetector)
