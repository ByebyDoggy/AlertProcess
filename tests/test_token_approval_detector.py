"""
Unit tests for Token Approval Detector
"""
import pytest

import sys
sys.path.insert(0, '/workspace')

from models import AlertInput, TransactionContext, DetectionResult, SeverityEnum
from detectors.implementations.token_approval_detector import (
    TokenApprovalDetector,
    TokenApprovalDetectorConfig,
)


class TestTokenApprovalDetector:
    """Test TokenApprovalDetector"""
    
    def test_detector_creation(self):
        """Test TokenApprovalDetector creation"""
        config = TokenApprovalDetectorConfig(
            check_infinite_approval=True,
            check_approval_to_unknown=True
        )
        detector = TokenApprovalDetector(config)
        
        assert detector.name == "token_approval_detector"
        assert detector.config.check_infinite_approval is True
        assert detector.config.check_approval_to_unknown is True
    
    def test_detector_default_config(self):
        """Test detector with default config"""
        detector = TokenApprovalDetector()
        assert detector.name == "token_approval_detector"
    
    @pytest.mark.asyncio
    async def test_detect_no_approval(self):
        """Test detection with no approval call"""
        detector = TokenApprovalDetector()
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xabc",
            to_address="0xdef",
            input_data="0x12345678"  # Random method, not approval
        )
        
        result = await detector.detect(alert, context)
        
        assert result.detected is False
        assert result.alert_type is None
    
    @pytest.mark.asyncio
    async def test_detect_approve_call(self):
        """Test detection with approve call"""
        detector = TokenApprovalDetector()
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        # approve(spender, amount) - 0x095ea7b3
        # spender: 0xdef456... (20 bytes), amount: 1000...
        input_data = "0x095ea7b3" + "0" * 24 + "def456" + "0" * 24 + "03e8"  # 1000 in hex
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xabc",
            to_address="0xtoken",
            input_data=input_data
        )
        
        result = await detector.detect(alert, context)
        
        # Should detect APPROVAL_TO_UNKNOWN_CONTRACT (since spender is not known)
        assert result.detected is True
        assert "APPROVAL_TO_UNKNOWN_CONTRACT" in result.metadata["detected_issues"]
        assert result.metadata["method"] == "approve"
    
    @pytest.mark.asyncio
    async def test_detect_infinite_approval(self):
        """Test detection with infinite approval"""
        detector = TokenApprovalDetector(
            config=TokenApprovalDetectorConfig(check_infinite_approval=True)
        )
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        # approve with max uint256
        max_uint = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
        input_data = "0x095ea7b3" + "0" * 24 + "def456" + "0" * 24 + max_uint
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xabc",
            to_address="0xtoken",
            input_data=input_data
        )
        
        result = await detector.detect(alert, context)
        
        assert result.detected is True
        assert "INFINITE_APPROVAL" in result.metadata["detected_issues"]
        assert result.alert_type == "INFINITE_APPROVAL"
        assert result.severity == SeverityEnum.HIGH
    
    @pytest.mark.asyncio
    async def test_detect_approval_to_known_protocol(self):
        """Test detection with approval to known protocol (Aave)"""
        detector = TokenApprovalDetector()
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        # approve to Aave V2
        aave_v2 = "0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9"
        input_data = "0x095ea7b3" + "0" * 24 + aave_v2[2:] + "0" * 24 + "03e8"
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xabc",
            to_address="0xtoken",
            input_data=input_data
        )
        
        result = await detector.detect(alert, context)
        
        assert result.detected is True
        assert "APPROVAL_TO_KNOWN_PROTocol:Aave V2" in result.metadata["detected_issues"]
    
    @pytest.mark.asyncio
    async def test_detect_transfer_from(self):
        """Test detection with transferFrom call"""
        detector = TokenApprovalDetector()
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        # transferFrom(from, to, amount) - 0x23b872dd
        # from: 0xabc... (20 bytes), to: 0xdef... (20 bytes), amount: 1000
        input_data = "0x23b872dd" + "0" * 8 + "abc00000000000000000000000000000000000000" + "def00000000000000000000000000000000000000" + "03e8"
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xabc",
            to_address="0xtoken",
            input_data=input_data
        )
        
        result = await detector.detect(alert, context)
        
        assert result.detected is True
        assert result.metadata["method"] == "transferFrom"
    
    @pytest.mark.asyncio
    async def test_detect_set_approval_for_all(self):
        """Test detection with setApprovalForAll"""
        detector = TokenApprovalDetector()
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        # setApprovalForAll(operator, approved) - 0xa22cb465
        operator = "0xdef4560000000000000000000000000000000000"
        input_data = "0xa22cb465" + "0" * 24 + operator[2:] + "0000000000000000000000000000000000000000000000000000000000000001"
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xabc",
            to_address="0xcontract",
            input_data=input_data
        )
        
        result = await detector.detect(alert, context)
        
        assert result.detected is True
        assert "APPROVAL_FOR_ALL_UNKNOWN" in result.metadata["detected_issues"]
    
    @pytest.mark.asyncio
    async def test_detect_set_approval_for_all_to_known(self):
        """Test detection with setApprovalForAll to known protocol"""
        detector = TokenApprovalDetector()
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        # setApprovalForAll to Uniswap V3
        uniswap = "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45"
        input_data = "0xa22cb465" + "0" * 24 + uniswap[2:] + "0000000000000000000000000000000000000000000000000000000000000001"
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xabc",
            to_address="0xcontract",
            input_data=input_data
        )
        
        result = await detector.detect(alert, context)
        
        assert result.detected is True
        assert "APPROVAL_FOR_ALL_KNOWN:Uniswap V3" in result.metadata["detected_issues"]


class TestTokenApprovalDetectorParsing:
    """Test parsing methods of TokenApprovalDetector"""
    
    def test_parse_approve(self):
        """Test parsing approve function call"""
        detector = TokenApprovalDetector()
        
        input_data = "0x095ea7b3" + "0" * 24 + "def45600000000000000000000000000000000000000" + "0" * 24 + "03e8"
        result = detector._parse_approval(input_data)
        
        assert result is not None
        assert result["method"] == "approve"
        assert result["spender"] == "0xdef45600000000000000000000000000000000000000"
        assert result["amount"] == 1000
    
    def test_parse_transfer_from(self):
        """Test parsing transferFrom function call"""
        detector = TokenApprovalDetector()
        
        input_data = "0x23b872dd" + "0" * 8 + "abc00000000000000000000000000000000000000" + "def00000000000000000000000000000000000000" + "03e8"
        result = detector._parse_transfer_data(input_data)
        
        assert result is not None
        assert result["method"] == "transferFrom"
    
    def test_parse_invalid(self):
        """Test parsing with invalid input"""
        detector = TokenApprovalDetector()
        
        assert detector._parse_approval("0x") is None
        assert detector._parse_approval("0x12345678") is None
        assert detector._parse_approval(None) is None
    
    def test_is_infinite_approval(self):
        """Test infinite approval detection"""
        detector = TokenApprovalDetector()
        
        max_uint = 115792089237316195423570985008687907853269984665640564039457584007913129639935
        assert detector._is_infinite_approval(max_uint) is True
        assert detector._is_infinite_approval(max_uint - 1) is True
        assert detector._is_infinite_approval(1000) is False
    
    def test_is_suspicious_target(self):
        """Test suspicious target detection"""
        detector = TokenApprovalDetector()
        
        is_susp, name = detector._is_suspicious_target("0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9")
        assert is_susp is True
        assert name == "Aave V2"
        
        is_susp, name = detector._is_suspicious_target("0xunknown")
        assert is_susp is False
        assert name is None


def run_tests():
    """Run all tests"""
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    run_tests()
