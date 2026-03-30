"""
Detector base class and registry for pluggable security detection
"""
from abc import ABC, abstractmethod
from typing import Any
from pydantic import BaseModel
from models import AlertInput, DetectionResult, TransactionContext


class DetectorConfig(BaseModel):
    """Base detector configuration"""
    enabled: bool = True


class Detector(ABC):
    """
    Base class for all detectors
    
    Detectors are the core security analysis units that analyze
    transaction context and return detection results.
    
    Each detector should:
    1. Have a unique name
    2. Implement the detect method
    3. Provide a config schema for user configuration
    4. Optionally cache results to avoid redundant API calls
    """
    
    def __init__(self, config: DetectorConfig | None = None):
        self.config = config or self.get_default_config()
        self._cache: dict[str, DetectionResult] = {}
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique detector name"""
        pass
    
    @property
    def description(self) -> str:
        """Human-readable description of what this detector does"""
        return ""
    
    @classmethod
    def get_default_config(cls) -> DetectorConfig:
        """Get default configuration for this detector"""
        return DetectorConfig()
    
    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        """
        Get JSON schema for detector configuration
        Override this to allow users to configure detector parameters
        """
        return {}
    
    @abstractmethod
    async def detect(
        self, 
        alert: AlertInput, 
        context: TransactionContext
    ) -> DetectionResult:
        """
        Perform detection analysis on the given alert and context
        
        Args:
            alert: The alert input containing basic alert info
            context: The full transaction context
            
        Returns:
            DetectionResult with detection status and metadata
        """
        pass
    
    def get_cache_key(self, alert: AlertInput, context: TransactionContext) -> str:
        """Generate cache key for this detection"""
        return f"{self.name}:{alert.chain_id}:{alert.tx_hash}"
    
    def get_cached(self, alert: AlertInput, context: TransactionContext) -> DetectionResult | None:
        """Get cached detection result if available"""
        key = self.get_cache_key(alert, context)
        return self._cache.get(key)
    
    def set_cached(self, alert: AlertInput, context: TransactionContext, result: DetectionResult):
        """Cache detection result"""
        key = self.get_cache_key(alert, context)
        self._cache[key] = result
    
    def clear_cache(self):
        """Clear all cached results"""
        self._cache.clear()
    
    async def detect_with_cache(
        self, 
        alert: AlertInput, 
        context: TransactionContext
    ) -> DetectionResult:
        """Detect with automatic caching"""
        cached = self.get_cached(alert, context)
        if cached:
            return cached
        
        result = await self.detect(alert, context)
        self.set_cached(alert, context, result)
        return result


class DetectorRegistry:
    """
    Registry for managing and accessing detectors
    """
    
    _detectors: dict[str, type[Detector]] = {}
    _instances: dict[str, Detector] = {}
    
    @classmethod
    def register(cls, detector_class: type[Detector]):
        """Register a detector class"""
        instance = detector_class()
        cls._detectors[instance.name] = detector_class
        return detector_class
    
    @classmethod
    def get(cls, name: str) -> Detector | None:
        """Get detector instance by name"""
        if name in cls._instances:
            return cls._instances[name]
        
        if name in cls._detectors:
            cls._instances[name] = cls._detectors[name]()
            return cls._instances[name]
        
        return None
    
    @classmethod
    def get_or_create(cls, name: str, config: dict[str, Any] | None = None) -> Detector | None:
        """Get or create detector instance with configuration"""
        if name in cls._instances:
            instance = cls._instances[name]
            if config and hasattr(instance, 'config') and isinstance(config, dict):
                for key, value in config.items():
                    if hasattr(instance.config, key):
                        setattr(instance.config, key, value)
            return instance
        
        if name in cls._detectors:
            detector_class = cls._detectors[name]
            if config:
                instance = detector_class(config)
            else:
                instance = detector_class()
            cls._instances[name] = instance
            return instance
        
        return None
    
    @classmethod
    def list_detectors(cls) -> list[str]:
        """List all registered detector names"""
        return list(cls._detectors.keys())
    
    @classmethod
    def create_all(cls) -> list[Detector]:
        """Create instances of all registered detectors"""
        return [cls._detectors[name]() for name in cls._detectors]
