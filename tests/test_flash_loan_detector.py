"""
Unit tests for Flash Loan Detector
"""
import pytest

import sys
sys.path.insert(0, '/workspace')

from models import AlertInput, TransactionContext, DetectionResult, SeverityEnum
from detectors.implementations.flash_loan_detector import (
    FlashLoanDetector,
    FlashLoanDetectorConfig,
)


class TestFlashLoanDetector:
    """Test FlashLoanDetector"""
    
    def test_detector_creation(self):
        """Test FlashLoanDetector creation"""
        config = FlashLoanDetectorConfig(
            large_flash_loan_threshold_usd=50000.0
        )
        detector = FlashLoanDetector(config)
        
        assert detector.name == "flash_loan_detector"
        assert detector.config.large_flash_loan_threshold_usd == 50000.0
    
    def test_detector_default_config(self):
        """Test detector with default config"""
        detector = FlashLoanDetector()
        assert detector.name == "flash_loan_detector"
        assert len(detector.config.flash_loan_protocols) > 0
    
    @pytest.mark.asyncio
    async def test_detect_normal_transaction(self):
        """Test detection with normal transaction (no flash loan)"""
        detector = FlashLoanDetector()
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xabc123",
            to_address="0xdef456",
            value=1000000000000000000,  # 1 ETH
            input_data="0x"  # No input data
        )
        
        result = await detector.detect(alert, context)
        
        assert result.detected is False
        assert result.alert_type is None
    
    @pytest.mark.asyncio
    async def test_detect_known_flash_loan_protocol(self):
        """Test detection with known flash loan protocol (Aave V2)"""
        detector = FlashLoanDetector()
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xabc123",
            to_address="0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9",  # Aave V2
            value=0,
            input_data="0x"
        )
        
        result = await detector.detect(alert, context)
        
        assert result.detected is True
        assert "KNOWN_FLASH_LOAN_PROTOCOL:Aave V2" in result.metadata["detected_issues"]
    
    @pytest.mark.asyncio
    async def test_detect_flash_loan_method_signature(self):
        """Test detection with flash loan method signature"""
        detector = FlashLoanDetector()
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xabc123",
            to_address="0xdef456",
            value=0,
            input_data="0x0906f8c8" + "0" * 56  # flash() method
        )
        
        result = await detector.detect(alert, context)
        
        assert result.detected is True
        assert "FLASH_LOAN_METHOD_SIGNATURE" in result.metadata["detected_issues"]
    
    @pytest.mark.asyncio
    async def test_detect_large_flash_loan(self):
        """Test detection with large flash loan amount"""
        config = FlashLoanDetectorConfig(
            large_flash_loan_threshold_usd=100000.0  # $100k threshold
        )
        detector = FlashLoanDetector(config)
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xabc123",
            to_address="0xdef456",
            value=100000000000000000000,  # 100 ETH = $200k (ETH=$2000)
            input_data="0x"
        )
        
        result = await detector.detect(alert, context)
        
        assert result.detected is True
        assert "LARGE_FLASH_LOAN" in result.metadata["detected_issues"][0]
    
    @pytest.mark.asyncio
    async def test_detect_large_flash_loan_with_protocol(self):
        """Test detection with large flash loan on known protocol -> CRITICAL"""
        config = FlashLoanDetectorConfig(
            large_flash_loan_threshold_usd=100000.0
        )
        detector = FlashLoanDetector(config)
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xabc123",
            to_address="0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9",  # Aave V2
            value=100000000000000000000,  # 100 ETH
            input_data="0x"
        )
        
        result = await detector.detect(alert, context)
        
        assert result.detected is True
        assert result.severity == SeverityEnum.CRITICAL
        assert result.alert_type == "LARGE_FLASH_LOAN_ATTACK"
    
    def test_detect_flash_loan_method_true(self):
        """Test _detect_flash_loan_method returns True for valid signatures"""
        detector = FlashLoanDetector()
        
        assert detector._detect_flash_loan_method("0x0906f8c8000...") is True
        assert detector._detect_flash_loan_method("0x5c7d2920000...") is True
        assert detector._detect_flash_loan_method("0x016602d8000...") is True
    
    def test_detect_flash_loan_method_false(self):
        """Test _detect_flash_loan_method returns False for invalid signatures"""
        detector = FlashLoanDetector()
        
        assert detector._detect_flash_loan_method("0x") is False
        assert detector._detect_flash_loan_method("0x12345678") is False
        assert detector._detect_flash_loan_method("") is False
        assert detector._detect_flash_loan_method(None) is False
    
    def test_get_protocol_name(self):
        """Test _get_protocol_name returns correct protocol"""
        detector = FlashLoanDetector()
        
        assert detector._get_protocol_name("0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9") == "Aave V2"
        assert detector._get_protocol_name("0x794a61358d6845594f94dc1db02a252b5b4814aa") == "Aave V3"
        assert detector._get_protocol_name("0x1e0447b19bb6ecfdae1e4ae1694b0c3659614e4e") == "dYdX"
        assert detector._get_protocol_name("0xunknown") is None


class TestFlashLoanDetectorEdgeCases:
    """Test edge cases for FlashLoanDetector"""
    
    @pytest.mark.asyncio
    async def test_no_input_data(self):
        """Test with no input data"""
        detector = FlashLoanDetector()
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xabc",
            to_address="0xdef",
            value=0,
            input_data=None
        )
        
        result = await detector.detect(alert, context)
        
        assert result.detected is False
    
    @pytest.mark.asyncio
    async def test_none_addresses(self):
        """Test with None addresses"""
        detector = FlashLoanDetector()
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address=None,
            to_address=None,
            value=0,
            input_data="0x"
        )
        
        result = await detector.detect(alert, context)
        
        assert result.detected is False


def run_tests():
    """Run all tests"""
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    run_tests()
