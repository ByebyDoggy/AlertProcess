from detectors.base import DetectorRegistry

# Register built-in detectors
from detectors.implementations.gas_price_detector import GasPriceDetector, GasPriceDetectorConfig
from detectors.implementations.address_type_detector import AddressTypeDetector, AddressTypeDetectorConfig

__all__ = [
    'GasPriceDetector',
    'GasPriceDetectorConfig',
    'AddressTypeDetector', 
    'AddressTypeDetectorConfig',
]
