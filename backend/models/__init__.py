"""
Core models for the Alert Processing System
Based on Forta-inspired architecture with pluggable detectors and rules
"""
from datetime import datetime
from enum import Enum
from typing import Any, Optional, TYPE_CHECKING
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from web3.types import TxData


class SeverityEnum(str, Enum):
    UNKNOWN = "UNKNOWN"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertInput(BaseModel):
    """Alert input from webhook - minimal required data"""
    chain_id: int
    tx_hash: str
    attacked_address: Optional[str] = None
    exploiter_address: Optional[str] = None


class TransactionContext(BaseModel):
    """
    Full transaction context with web3 transaction data
    Automatically fetches transaction details from chain based on tx_hash
    """
    chain_id: int
    tx_hash: str
    
    # Attack-related inference fields (provided by alert source or derived)
    attacked_address: Optional[str] = None
    exploiter_address: Optional[str] = None
    
    # Web3 transaction data (populated automatically)
    block_number: Optional[int] = None
    from_address: Optional[str] = None
    to_address: Optional[str] = None
    value: Optional[int] = None
    gas_price: Optional[int] = None
    gas_used: Optional[int] = None
    gas_limit: Optional[int] = None
    timestamp: Optional[datetime] = None
    input_data: Optional[str] = None
    nonce: Optional[int] = None
    r: Optional[str] = None
    s: Optional[str] = None
    v: Optional[int] = None
    
    # Raw tx data for advanced access
    raw_tx: Optional[dict] = None
    
    def get(self, key: str, default: Any = None) -> Any:
        """Access transaction fields dynamically"""
        if hasattr(self, key):
            return getattr(self, key)
        if self.raw_tx and key in self.raw_tx:
            return self.raw_tx[key]
        return default
    
    @property
    def from_address_normalized(self) -> Optional[str]:
        """Get normalized from address (checksummed)"""
        return self.from_address
    
    @property
    def to_address_normalized(self) -> Optional[str]:
        """Get normalized to address (checksummed)"""
        return self.to_address
    
    @property
    def value_in_eth(self) -> Optional[float]:
        """Get value in Ether"""
        if self.value is not None:
            return self.value / 10**18
        return None


class DetectionResult(BaseModel):
    """
    Result from a single detector
    """
    detector_name: str
    detected: bool = False
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    alert_type: Optional[str] = None
    severity: SeverityEnum = SeverityEnum.UNKNOWN
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    def __bool__(self) -> bool:
        return self.detected


class FinalAlert(BaseModel):
    """
    Final processed alert after all detections and rule evaluation
    """
    alert_id: str
    chain_id: int
    tx_hash: str
    severity: SeverityEnum = SeverityEnum.UNKNOWN
    score: float = 0.0
    detections: list[DetectionResult] = Field(default_factory=list)
    matched_rules: list[str] = Field(default_factory=list)
    context: Optional[TransactionContext] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    def get_detection(self, detector_name: str) -> Optional[DetectionResult]:
        """Get detection result by detector name"""
        for d in self.detections:
            if d.detector_name == detector_name:
                return d
        return None
    
    def has_detection(self, detector_name: str) -> bool:
        """Check if a specific detector detected something"""
        detection = self.get_detection(detector_name)
        return detection is not None and detection.detected


class DataFetchResult(BaseModel):
    """Result from a DataProvider fetch operation"""
    provider_name: str
    data: Any
    cached: bool = False
    error: Optional[str] = None
    fetch_time_ms: Optional[float] = None
