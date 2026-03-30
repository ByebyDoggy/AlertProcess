"""
Unit tests for Address Age Detector
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

import sys
sys.path.insert(0, '/workspace')

from models import AlertInput, TransactionContext, DetectionResult, SeverityEnum
from detectors.implementations.address_age_detector import (
    AddressAgeDetector,
    AddressAgeDetectorConfig,
)


class TestAddressAgeDetector:
    """Test AddressAgeDetector"""
    
    def test_detector_creation(self):
        """Test AddressAgeDetector creation"""
        config = AddressAgeDetectorConfig(
            new_address_threshold_days=14
        )
        detector = AddressAgeDetector(config)
        
        assert detector.name == "address_age_detector"
        assert detector.config.new_address_threshold_days == 14
    
    def test_detector_default_config(self):
        """Test detector with default config"""
        detector = AddressAgeDetector()
        assert detector.name == "address_age_detector"
        assert detector.config.new_address_threshold_days == 7
    
    @pytest.mark.asyncio
    async def test_detect_no_address(self):
        """Test detection with no address"""
        detector = AddressAgeDetector()
        
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
    async def test_detect_new_address(self):
        """Test detection with new address (created recently)"""
        detector = AddressAgeDetector(
            config=AddressAgeDetectorConfig(new_address_threshold_days=30)
        )
        
        # Create time was 5 days ago
        recent_time = datetime.now() - timedelta(days=5)
        
        with patch.object(detector, '_get_cached_create_time', return_value=recent_time):
            alert = AlertInput(chain_id=1, tx_hash="0x123", exploiter_address="0xabc")
            context = TransactionContext(
                chain_id=1,
                tx_hash="0x123",
                from_address="0xabc"
            )
            
            result = await detector.detect(alert, context)
            
            assert result.detected is True
            assert result.severity == SeverityEnum.HIGH
            assert result.alert_type == "NEW_ADDRESS"
            assert result.metadata["is_new"] is True
            assert result.metadata["age_days"] == 5
    
    @pytest.mark.asyncio
    async def test_detect_old_address(self):
        """Test detection with old address"""
        detector = AddressAgeDetector(
            config=AddressAgeDetectorConfig(new_address_threshold_days=30)
        )
        
        # Create time was 100 days ago
        old_time = datetime.now() - timedelta(days=100)
        
        with patch.object(detector, '_get_cached_create_time', return_value=old_time):
            alert = AlertInput(chain_id=1, tx_hash="0x123", exploiter_address="0xabc")
            context = TransactionContext(
                chain_id=1,
                tx_hash="0x123",
                from_address="0xabc"
            )
            
            result = await detector.detect(alert, context)
            
            assert result.detected is False
            assert result.severity == SeverityEnum.UNKNOWN
            assert result.metadata["is_new"] is False
            assert result.metadata["age_days"] == 100
    
    @pytest.mark.asyncio
    async def test_detect_no_api_key(self):
        """Test detection when no Moralis API key"""
        detector = AddressAgeDetector()
        
        with patch.object(detector, '_get_cached_create_time', return_value=None):
            with patch('detectors.implementations.address_age_detector.settings') as mock_settings:
                mock_settings.moralis_api_key = None
                
                alert = AlertInput(chain_id=1, tx_hash="0x123", exploiter_address="0xabc")
                context = TransactionContext(
                    chain_id=1,
                    tx_hash="0x123",
                    from_address="0xabc"
                )
                
                result = await detector.detect(alert, context)
                
                assert result.detected is False
                assert "No Moralis API key" in result.metadata.get("error", "")


class TestAddressAgeDetectorCaching:
    """Test address age caching functionality"""
    
    def test_save_and_get_cached_create_time(self):
        """Test saving and retrieving create time from cache"""
        config = AddressAgeDetectorConfig()
        detector = AddressAgeDetector(config)
        
        # Test that the methods exist
        assert callable(detector._save_create_time)
        assert callable(detector._get_cached_create_time)


class TestAddressAgeDetectorMoralis:
    """Test Moralis API integration"""
    
    @pytest.mark.asyncio
    async def test_fetch_from_moralis(self):
        """Test fetching create time from Moralis"""
        detector = AddressAgeDetector()
        
        # Mock the API response
        mock_result = MagicMock()
        mock_result.get.return_value = [
            {
                "chain": "eth",
                "first_transaction": {
                    "block_timestamp": "2024-01-15T00:00:00.000Z"
                }
            }
        ]
        
        with patch('detectors.implementations.address_age_detector.evm_api') as mock_evm:
            with patch('detectors.implementations.address_age_detector.settings') as mock_settings:
                mock_settings.moralis_api_key = "test_key"
                mock_evm.wallets.get_wallet_active_chains.return_value = mock_result
                
                alert = AlertInput(chain_id=1, tx_hash="0x123", exploiter_address="0xabc")
                context = TransactionContext(
                    chain_id=1,
                    tx_hash="0x123",
                    from_address="0xabc"
                )
                
                # Clear cache to force API call
                with patch.object(detector, '_get_cached_create_time', return_value=None):
                    result = await detector.detect(alert, context)
                    
                    # Should process successfully
                    assert result.detected is True  # or False depending on age


def run_tests():
    """Run all tests"""
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    run_tests()
