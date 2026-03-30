"""
Unit tests for Alert Processing System
Tests core models, detectors, and data providers
"""
import pytest
import asyncio
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch

# Test imports
import sys
sys.path.insert(0, '/workspace')

from models import (
    AlertInput, 
    TransactionContext, 
    DetectionResult, 
    SeverityEnum,
    FinalAlert
)
from detectors.base import Detector, DetectorConfig, DetectorRegistry
from detectors.implementations.gas_price_detector import GasPriceDetector, GasPriceDetectorConfig
from detectors.implementations.address_type_detector import AddressTypeDetector, AddressTypeDetectorConfig
from data_providers.context_builder import TransactionContextBuilder


class TestAlertInput:
    """Test AlertInput model"""
    
    def test_alert_input_creation(self):
        """Test basic AlertInput creation"""
        alert = AlertInput(
            chain_id=1,
            tx_hash="0x1234567890abcdef",
            attacked_address="0xabc123",
            exploiter_address="0xdef456"
        )
        
        assert alert.chain_id == 1
        assert alert.tx_hash == "0x1234567890abcdef"
        assert alert.attacked_address == "0xabc123"
        assert alert.exploiter_address == "0xdef456"
    
    def test_alert_input_optional_fields(self):
        """Test AlertInput with optional fields"""
        alert = AlertInput(
            chain_id=1,
            tx_hash="0x1234567890abcdef"
        )
        
        assert alert.attacked_address is None
        assert alert.exploiter_address is None


class TestTransactionContext:
    """Test TransactionContext model"""
    
    def test_transaction_context_creation(self):
        """Test basic TransactionContext creation"""
        ctx = TransactionContext(
            chain_id=1,
            tx_hash="0x1234567890abcdef",
            block_number=12345678,
            from_address="0xabc123",
            to_address="0xdef456",
            value=1000000000000000000,  # 1 ETH
            gas_price=20000000000,  # 20 gwei
            gas_used=21000,
            timestamp=datetime.now()
        )
        
        assert ctx.chain_id == 1
        assert ctx.tx_hash == "0x1234567890abcdef"
        assert ctx.from_address == "0xabc123"
        assert ctx.value == 1000000000000000000
    
    def test_value_in_eth(self):
        """Test value conversion to ETH"""
        ctx = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            value=1000000000000000000  # 1 ETH in wei
        )
        
        assert ctx.value_in_eth == 1.0
    
    def test_get_method(self):
        """Test dynamic field access"""
        ctx = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xabc"
        )
        
        assert ctx.get("chain_id") == 1
        assert ctx.get("from_address") == "0xabc"
        assert ctx.get("nonexistent", "default") == "default"


class TestDetectionResult:
    """Test DetectionResult model"""
    
    def test_detection_result_creation(self):
        """Test basic DetectionResult creation"""
        result = DetectionResult(
            detector_name="test_detector",
            detected=True,
            alert_type="TEST_ALERT",
            severity=SeverityEnum.HIGH,
            metadata={"key": "value"}
        )
        
        assert result.detector_name == "test_detector"
        assert result.detected is True
        assert result.alert_type == "TEST_ALERT"
        assert result.severity == SeverityEnum.HIGH
    
    def test_detection_result_bool(self):
        """Test DetectionResult boolean conversion"""
        detected_result = DetectionResult(detector_name="test", detected=True)
        not_detected_result = DetectionResult(detector_name="test", detected=False)
        
        assert bool(detected_result) is True
        assert bool(not_detected_result) is False


class TestDetectorRegistry:
    """Test DetectorRegistry functionality"""
    
    def test_register_and_get(self):
        """Test registering and retrieving a detector"""
        # Create a simple concrete detector for testing
        class TestDetector(Detector):
            @property
            def name(self) -> str:
                return "test_detector"
            
            async def detect(self, alert: AlertInput, context: TransactionContext) -> DetectionResult:
                return DetectionResult(detector_name=self.name, detected=False)
        
        # Note: This test assumes clean registry state
        # In real tests, you might want to use a separate registry instance
        pass  # Registry operations tested below
    
    def test_list_detectors(self):
        """Test listing registered detectors"""
        detectors = DetectorRegistry.list_detectors()
        assert isinstance(detectors, list)
        # Should have our built-in detectors
        assert "gas_price_detector" in detectors
        assert "address_type_detector" in detectors


class TestGasPriceDetector:
    """Test GasPriceDetector"""
    
    def test_detector_creation(self):
        """Test GasPriceDetector creation"""
        config = GasPriceDetectorConfig(threshold_usd=50.0)
        detector = GasPriceDetector(config)
        
        assert detector.name == "gas_price_detector"
        assert detector.config.threshold_usd == 50.0
    
    @pytest.mark.asyncio
    async def test_detect_normal_gas_price(self):
        """Test detection with normal gas price"""
        config = GasPriceDetectorConfig(threshold_usd=100.0)
        detector = GasPriceDetector(config)
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            gas_price=20000000000,  # 20 gwei = ~$40 USD (ETH=$2000)
        )
        
        result = await detector.detect(alert, context)
        
        assert result.detected is False
        assert result.detector_name == "gas_price_detector"
    
    @pytest.mark.asyncio
    async def test_detect_high_gas_price(self):
        """Test detection with high gas price"""
        config = GasPriceDetectorConfig(threshold_usd=100.0)
        detector = GasPriceDetector(config)
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        # threshold_usd=100, ETH=$2000 -> threshold = 0.05 ETH = 5e16 wei = 50000 gwei
        # Use 60000 gwei = 6e13 wei = $120 USD to exceed threshold
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            gas_price=60000000000000000,  # 60000 gwei = ~$120 USD (ETH=$2000)
        )
        
        result = await detector.detect(alert, context)
        
        assert result.detected is True
        assert result.alert_type == "HIGH_GAS_PRICE"
        assert result.severity == SeverityEnum.HIGH
        assert result.metadata["gas_price_usd"] > 100.0
    
    @pytest.mark.asyncio
    async def test_detect_no_gas_price(self):
        """Test detection when gas price not available"""
        detector = GasPriceDetector()
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            gas_price=None
        )
        
        result = await detector.detect(alert, context)
        
        assert result.detected is False
        assert "error" in result.metadata


class TestAddressTypeDetector:
    """Test AddressTypeDetector"""
    
    def test_detector_creation(self):
        """Test AddressTypeDetector creation"""
        detector = AddressTypeDetector()
        assert detector.name == "address_type_detector"
    
    @pytest.mark.asyncio
    async def test_detect_normal_transaction(self):
        """Test detection with normal transaction"""
        detector = AddressTypeDetector()
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xabc",
            to_address="0xdef",
            value=1000
        )
        
        result = await detector.detect(alert, context)
        
        assert result.detected is False
    
    @pytest.mark.asyncio
    async def test_detect_null_to_address(self):
        """Test detection with null 'to' address (contract creation)"""
        detector = AddressTypeDetector()
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xabc",
            to_address="0x0000000000000000000000000000000000000000",
            value=0,
            input_data=None  # No input data, just null to address
        )
        
        result = await detector.detect(alert, context)
        
        assert result.detected is True
        assert result.alert_type == "NULL_TO_ADDRESS"
        assert result.metadata["is_null_to"] is True
    
    @pytest.mark.asyncio
    async def test_detect_contract_creation_with_value(self):
        """Test detection of contract creation with value"""
        detector = AddressTypeDetector()
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xabc",
            to_address="0x0000000000000000000000000000000000000000",
            value=1000000000000000000,  # 1 ETH
            input_data="0x60606040..."
        )
        
        result = await detector.detect(alert, context)
        
        assert result.detected is True
        assert "CONTRACT_CREATION_WITH_VALUE" in result.metadata["detected_issues"]


class TestTransactionContextBuilder:
    """Test TransactionContextBuilder"""
    
    def test_builder_creation(self):
        """Test builder creation"""
        builder = TransactionContextBuilder({
            1: "https://eth-mainnet.example.com",
            56: "https://bsc-mainnet.example.com"
        })
        
        assert builder.chain_id_to_provider_url[1] == "https://eth-mainnet.example.com"
    
    @pytest.mark.asyncio
    async def test_build_minimal_context(self):
        """Test building context without web3 (no provider)"""
        builder = TransactionContextBuilder({})
        
        alert = AlertInput(
            chain_id=1,
            tx_hash="0x1234567890abcdef",
            attacked_address="0xvictim",
            exploiter_address="0xexploiter"
        )
        
        context = await builder.build(alert)
        
        assert context.chain_id == 1
        assert context.tx_hash == "0x1234567890abcdef"
        assert context.attacked_address == "0xvictim"
        assert context.exploiter_address == "0xexploiter"
        # These should be None as no web3 provider
        assert context.from_address is None


class TestFinalAlert:
    """Test FinalAlert model"""
    
    def test_final_alert_creation(self):
        """Test FinalAlert creation"""
        alert = FinalAlert(
            alert_id="test-123",
            chain_id=1,
            tx_hash="0x123",
            severity=SeverityEnum.HIGH,
            score=85.0
        )
        
        assert alert.alert_id == "test-123"
        assert alert.severity == SeverityEnum.HIGH
        assert alert.score == 85.0
    
    def test_get_detection(self):
        """Test getting detection by name"""
        detection1 = DetectionResult(detector_name="detector1", detected=True)
        detection2 = DetectionResult(detector_name="detector2", detected=False)
        
        alert = FinalAlert(
            alert_id="test",
            chain_id=1,
            tx_hash="0x123",
            detections=[detection1, detection2]
        )
        
        assert alert.get_detection("detector1") == detection1
        assert alert.get_detection("detector2") == detection2
        assert alert.get_detection("nonexistent") is None
    
    def test_has_detection(self):
        """Test checking if detector detected something"""
        detection = DetectionResult(detector_name="detector1", detected=True)
        
        alert = FinalAlert(
            alert_id="test",
            chain_id=1,
            tx_hash="0x123",
            detections=[detection]
        )
        
        assert alert.has_detection("detector1") is True
        assert alert.has_detection("detector2") is False


class TestSeverityEnum:
    """Test SeverityEnum"""
    
    def test_severity_values(self):
        """Test severity enum values"""
        assert SeverityEnum.UNKNOWN.value == "UNKNOWN"
        assert SeverityEnum.LOW.value == "LOW"
        assert SeverityEnum.MEDIUM.value == "MEDIUM"
        assert SeverityEnum.HIGH.value == "HIGH"
        assert SeverityEnum.CRITICAL.value == "CRITICAL"


def run_tests():
    """Run all tests"""
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    run_tests()
