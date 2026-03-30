"""
Unit tests for Token Anomaly Detector
"""
import pytest

import sys
sys.path.insert(0, '/workspace')

from models import AlertInput, TransactionContext, DetectionResult, SeverityEnum
from detectors.implementations.token_anomaly_detector import (
    TokenAnomalyDetector,
    TokenAnomalyDetectorConfig,
)


class TestTokenAnomalyDetector:
    """Test TokenAnomalyDetector"""
    
    def test_detector_creation(self):
        """Test TokenAnomalyDetector creation"""
        config = TokenAnomalyDetectorConfig(
            large_transfer_threshold=500000.0
        )
        detector = TokenAnomalyDetector(config)
        
        assert detector.name == "token_anomaly_detector"
        assert detector.config.large_transfer_threshold == 500000.0
    
    def test_detector_default_config(self):
        """Test detector with default config"""
        detector = TokenAnomalyDetector()
        assert detector.name == "token_anomaly_detector"
    
    @pytest.mark.asyncio
    async def test_detect_normal_transaction(self):
        """Test detection with normal transaction"""
        detector = TokenAnomalyDetector()
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xabc",
            to_address="0xdef",
            value=1000000000000000,  # 0.001 ETH
            input_data="0x"
        )
        
        result = await detector.detect(alert, context)
        
        assert result.detected is False
    
    @pytest.mark.asyncio
    async def test_detect_large_eth_transfer(self):
        """Test detection with large ETH transfer"""
        detector = TokenAnomalyDetector()
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xabc",
            to_address="0x0000000000000000000000000000000000000000",  # null address
            value=10000000000000000000,  # 10 ETH
            input_data="0x"
        )
        
        result = await detector.detect(alert, context)
        
        assert result.detected is True
        assert any("LARGE_ETH_TRANSFER" in issue for issue in result.metadata["detected_issues"])
    
    @pytest.mark.asyncio
    async def test_detect_large_token_transfer(self):
        """Test detection with large token transfer"""
        detector = TokenAnomalyDetector()
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        # ERC20 transfer to some address
        # transfer(to, amount) - 0xa9059cbb
        to_address = "0xdef456000000000000000000000000000000000000"
        amount = "00000000000000000000000000000000000000000000000000000000000ffffff"  # large amount
        input_data = "0xa9059cbb" + "0" * 24 + to_address[2:] + amount
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xabc",
            to_address="0xtoken",
            value=0,
            input_data=input_data
        )
        
        result = await detector.detect(alert, context)
        
        assert result.detected is True
        assert any("LARGE_TOKEN_TRANSFER" in issue for issue in result.metadata["detected_issues"])
    
    @pytest.mark.asyncio
    async def test_detect_unusual_contract_interaction(self):
        """Test detection with unusual contract interaction"""
        detector = TokenAnomalyDetector()
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xabc",
            to_address="0xcontract",
            value=0,
            input_data="0xdeadbeef"  # Random data, not standard transfer
        )
        
        result = await detector.detect(alert, context)
        
        assert result.detected is True
        assert "UNUSUAL_CONTRACT_INTERACTION" in result.metadata["detected_issues"]
    
    @pytest.mark.asyncio
    async def test_detect_new_token_activity(self):
        """Test detection with new token activity"""
        detector = TokenAnomalyDetector()
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xabc",
            to_address="0xdef",
            value=0,
            input_data="0x",
            block_number=17000000  # Recent block on mainnet
        )
        
        result = await detector.detect(alert, context)
        
        # Should flag as new token activity
        assert result.detected is False  # No other issues
        assert "NEW_TOKEN_ACTIVITY" in result.metadata["detected_issues"]


class TestTokenAnomalyDetectorParsing:
    """Test parsing methods of TokenAnomalyDetector"""
    
    def test_is_native_eth_transfer(self):
        """Test native ETH transfer detection"""
        detector = TokenAnomalyDetector()
        
        assert detector._is_native_eth_transfer("0x0000000000000000000000000000000000000000", "0x") is True
        assert detector._is_native_eth_transfer("0x0000000000000000000000000000000000000000", "0x123") is True
        assert detector._is_native_eth_transfer("0xdef456", "0x") is False
    
    def test_parse_transfer_data(self):
        """Test parsing ERC20 transfer data"""
        detector = TokenAnomalyDetector()
        
        # transfer(to, amount) - 0xa9059cbb
        to_addr = "0x" + "def456" + "0" * 36
        amount_hex = "0" * 56 + "03e8"  # 1000
        input_data = "0xa9059cbb" + to_addr + amount_hex
        
        result = detector._parse_transfer_data(input_data)
        
        assert result is not None
        assert result["method"] == "transfer"
        assert result["to"] == to_addr
        assert result["amount"] == 1000
    
    def test_parse_transfer_from_data(self):
        """Test parsing ERC20 transferFrom data"""
        detector = TokenAnomalyDetector()
        
        # transferFrom(from, to, amount) - 0x23b872dd
        from_addr = "0x" + "abc123" + "0" * 36
        to_addr = "0x" + "def456" + "0" * 36
        amount_hex = "0" * 56 + "03e8"
        input_data = "0x23b872dd" + from_addr + to_addr + amount_hex
        
        result = detector._parse_transfer_data(input_data)
        
        assert result is not None
        assert result["method"] == "transferFrom"
    
    def test_parse_invalid_transfer_data(self):
        """Test parsing with invalid transfer data"""
        detector = TokenAnomalyDetector()
        
        assert detector._parse_transfer_data("0x") is None
        assert detector._parse_transfer_data("0x12345678") is None
        assert detector._parse_transfer_data(None) is None
    
    def test_is_new_token(self):
        """Test new token detection"""
        detector = TokenAnomalyDetector()
        
        # Block 17000000 on mainnet is recent
        assert detector._is_new_token("0xtoken", 17000000) is True
        
        # Block far below threshold
        assert detector._is_new_token("0xtoken", 1000000) is False


class TestTokenAnomalyDetectorEdgeCases:
    """Test edge cases for TokenAnomalyDetector"""
    
    @pytest.mark.asyncio
    async def test_no_input_data(self):
        """Test with no input data"""
        detector = TokenAnomalyDetector()
        
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
        detector = TokenAnomalyDetector()
        
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
