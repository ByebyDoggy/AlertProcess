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


def _python_type_to_json_type(annotation) -> str:
    """Convert Python type annotation to JSON schema type string"""
    origin = getattr(annotation, '__origin__', None)
    if origin is dict:
        return "object"
    if origin is list:
        return "array"
    if annotation is bool:
        return "boolean"
    if annotation is int:
        return "integer"
    if annotation is float:
        return "number"
    if annotation is str:
        return "string"
    return "string"


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

    @classmethod
    def get_detector_info(cls, name: str) -> dict[str, Any] | None:
        """
        Get detailed info for a single detector, including:
        - name: registry name (e.g. "flash_loan_detector")
        - type_key: frontend-friendly key (e.g. "flash_loan")
        - description: human-readable description
        - config_schema: JSON Schema for configuration
        - config_fields: detailed field list for form rendering
        - default_config: default configuration values
        """
        if name not in cls._detectors:
            return None
        detector_class = cls._detectors[name]
        instance = detector_class()
        config_class = type(instance.config)

        config_fields = []
        default_config = instance.config.model_dump()

        for field_name, field_info in config_class.model_fields.items():
            if field_name in ('enabled', 'name'):
                continue
            field_default = default_config.get(field_name)
            config_fields.append({
                "key": field_name,
                "type": _python_type_to_json_type(field_info.annotation),
                "default": field_default,
                "description": field_info.description or "",
                "required": field_info.is_required(),
            })

        return {
            "name": instance.name,
            "type_key": instance.name.replace("_detector", ""),
            "description": instance.description,
            "config_schema": detector_class.get_config_schema(),
            "config_fields": config_fields,
            "default_config": {
                k: v for k, v in default_config.items()
                if k not in ('enabled', 'name')
            },
        }

    @classmethod
    def get_all_detector_info(cls) -> list[dict[str, Any]]:
        """Get detailed info for all registered detectors"""
        return [cls.get_detector_info(name) for name in cls._detectors]

    @classmethod
    def build_detector_type_map(cls) -> dict[str, str]:
        """Build frontend type_key -> registry name mapping (e.g. flash_loan -> flash_loan_detector)"""
        result = {}
        for name in cls._detectors:
            instance = cls._detectors[name]()
            type_key = instance.name.replace("_detector", "")
            result[type_key] = instance.name
        return result
