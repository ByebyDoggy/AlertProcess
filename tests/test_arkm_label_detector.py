"""
Unit tests for ARKM Label Detector
"""
import pytest
from unittest.mock import MagicMock, patch

import sys
sys.path.insert(0, '/workspace')

from models import AlertInput, TransactionContext, DetectionResult, SeverityEnum
from detectors.implementations.arkm_label_detector import (
    ARKMLabelDetector,
    ARKMLabelDetectorConfig,
)


class TestARKMLabelDetector:
    """Test ARKMLabelDetector"""
    
    def test_detector_creation(self):
        """Test ARKMLabelDetector creation"""
        config = ARKMLabelDetectorConfig(
            arkm_cookie="test_cookie",
            blacklist_entity_types=["hacker", "scammer"]
        )
        detector = ARKMLabelDetector(config)
        
        assert detector.name == "arkm_label_detector"
        assert detector.config.arkm_cookie == "test_cookie"
        assert "hacker" in detector.config.blacklist_entity_types
    
    def test_detector_default_config(self):
        """Test detector with default config"""
        detector = ARKMLabelDetector()
        assert detector.name == "arkm_label_detector"
        assert "hacker" in detector.config.blacklist_entity_types
    
    @pytest.mark.asyncio
    async def test_detect_no_exploiter_address(self):
        """Test detection with no exploiter address"""
        detector = ARKMLabelDetector()
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address=None,
            to_address=None
        )
        
        result = await detector.detect(alert, context)
        
        assert result.detected is False
        assert "error" in result.metadata
    
    @pytest.mark.asyncio
    async def test_detect_blacklisted_entity(self):
        """Test detection with blacklisted entity type (hacker)"""
        config = ARKMLabelDetectorConfig(
            arkm_cookie="test",
            blacklist_entity_types=["hacker"]
        )
        detector = ARKMLabelDetector(config)
        
        # Mock database query to return None (force API call)
        # Mock the API response
        with patch.object(detector, '_fetch_arkm_entity_type', return_value=("hacker", "entity_123", "Hacker Group")):
            alert = AlertInput(chain_id=1, tx_hash="0x123", exploiter_address="0xabc")
            context = TransactionContext(
                chain_id=1,
                tx_hash="0x123",
                from_address="0xabc"
            )
            
            result = await detector.detect(alert, context)
            
            assert result.detected is True
            assert result.severity == SeverityEnum.CRITICAL
            assert result.alert_type == "MALICIOUS_ENTITY"
            assert result.metadata["entity_type"] == "hacker"
    
    @pytest.mark.asyncio
    async def test_detect_known_entity(self):
        """Test detection with known but not blacklisted entity"""
        config = ARKMLabelDetectorConfig(
            arkm_cookie="test",
            blacklist_entity_types=["hacker"],
            ignored_entity_types=["exchange", "institution"]
        )
        detector = ARKMLabelDetector(config)
        
        with patch.object(detector, '_fetch_arkm_entity_type', return_value=("exchange", "entity_456", "Binance")):
            alert = AlertInput(chain_id=1, tx_hash="0x123", exploiter_address="0xabc")
            context = TransactionContext(
                chain_id=1,
                tx_hash="0x123",
                from_address="0xabc"
            )
            
            result = await detector.detect(alert, context)
            
            # Known entity not in blacklist, should still detect but with LOW severity
            assert result.detected is True
            assert result.alert_type == "KNOWN_ENTITY"
            assert result.metadata["is_blacklisted"] is False


class TestARKMLabelDetectorCaching:
    """Test ARKM label caching functionality"""
    
    def test_save_and_get_from_db(self):
        """Test saving and retrieving entity from database"""
        # This test requires actual database setup, so we just test the flow
        config = ARKMLabelDetectorConfig(arkm_cookie="test")
        detector = ARKMLabelDetector(config)
        
        # Test that the methods exist and are callable
        assert callable(detector._save_to_db)
        assert callable(detector._get_entity_type_from_db)


class TestARKMLabelDetectorAPI:
    """Test ARKM API fetching"""
    
    def test_fetch_arkm_entity_type_no_cookie(self):
        """Test fetching without cookie"""
        config = ARKMLabelDetectorConfig(arkm_cookie="")
        detector = ARKMLabelDetector(config)
        
        result = detector._fetch_arkm_entity_type("0xabc", 1)
        
        assert result == (None, None, None)
    
    def test_fetch_arkm_entity_type_unknown_chain(self):
        """Test fetching with unknown chain"""
        config = ARKMLabelDetectorConfig(arkm_cookie="test")
        detector = ARKMLabelDetector(config)
        
        # Chain 999 is not in the mapping
        result = detector._fetch_arkm_entity_type("0xabc", 999)
        
        assert result == (None, None, None)


def run_tests():
    """Run all tests"""
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    run_tests()
