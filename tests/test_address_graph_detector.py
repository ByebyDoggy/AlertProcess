"""
Unit tests for Address Graph Detector
"""
import pytest

import sys
sys.path.insert(0, '/workspace')

from models import AlertInput, TransactionContext, DetectionResult, SeverityEnum
from detectors.implementations.address_graph_detector import (
    AddressGraphDetector,
    AddressGraphDetectorConfig,
)


class TestAddressGraphDetector:
    """Test AddressGraphDetector"""
    
    def test_detector_creation(self):
        """Test AddressGraphDetector creation"""
        config = AddressGraphDetectorConfig(
            centralization_threshold=10
        )
        detector = AddressGraphDetector(config)
        
        assert detector.name == "address_graph_detector"
        assert detector.config.centralization_threshold == 10
    
    def test_detector_default_config(self):
        """Test detector with default config"""
        detector = AddressGraphDetector()
        assert detector.name == "address_graph_detector"
        assert len(detector.config.known_exchanges) > 0
    
    @pytest.mark.asyncio
    async def test_detect_normal_transaction(self):
        """Test detection with normal transaction"""
        detector = AddressGraphDetector()
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xabc123",
            to_address="0xdef456",
            value=1000000000000000,  # 0.001 ETH
            input_data="0x"
        )
        
        result = await detector.detect(alert, context)
        
        assert result.detected is False
    
    @pytest.mark.asyncio
    async def test_detect_exchange_interaction_from(self):
        """Test detection with exchange as source"""
        detector = AddressGraphDetector()
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be",  # Binance
            to_address="0xdef456",
            value=1000000000000000000,
            input_data="0x"
        )
        
        result = await detector.detect(alert, context)
        
        assert result.detected is True
        assert result.metadata["exchanges"]["from"] == "Binance"
        assert "EXCHANGE_ORIGIN:Binance" in result.metadata["detected_issues"]
    
    @pytest.mark.asyncio
    async def test_detect_exchange_interaction_to(self):
        """Test detection with exchange as destination"""
        detector = AddressGraphDetector()
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xabc123",
            to_address="0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be",  # Binance
            value=1000000000000000000,
            input_data="0x"
        )
        
        result = await detector.detect(alert, context)
        
        assert result.detected is True
        assert result.metadata["exchanges"]["to"] == "Binance"
        assert "EXCHANGE_DESTINATION:Binance" in result.metadata["detected_issues"]
    
    @pytest.mark.asyncio
    async def test_detect_exploiter_interaction_from(self):
        """Test detection with exploiter as source"""
        detector = AddressGraphDetector()
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xab7535b4a1b3c2d2c7e7c7c7c7c7c7c7c7c7c7c7",  # Known Exploiter
            to_address="0xdef456",
            value=1000000000000000000,
            input_data="0x"
        )
        
        result = await detector.detect(alert, context)
        
        assert result.detected is True
        assert result.metadata["exploiters"]["from"] == "Known Exploiter"
        assert "EXPLOITER_ORIGIN:Known Exploiter" in result.metadata["detected_issues"]
    
    @pytest.mark.asyncio
    async def test_detect_exploiter_interaction_to(self):
        """Test detection with exploiter as destination"""
        detector = AddressGraphDetector()
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xabc123",
            to_address="0xab7535b4a1b3c2d2c7e7c7c7c7c7c7c7c7c7c7c7",  # Known Exploiter
            value=1000000000000000000,
            input_data="0x"
        )
        
        result = await detector.detect(alert, context)
        
        assert result.detected is True
        assert result.metadata["exploiters"]["to"] == "Known Exploiter"
        assert "EXPLOITER_DESTINATION:Known Exploiter" in result.metadata["detected_issues"]
    
    @pytest.mark.asyncio
    async def test_detect_exploiter_interaction_critical(self):
        """Test that exploiter interaction is marked CRITICAL"""
        detector = AddressGraphDetector()
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xab7535b4a1b3c2d2c7e7c7c7c7c7c7c7c7c7c7c7",  # Known Exploiter
            to_address="0xdef456",
            value=1000000000000000000,
            input_data="0x"
        )
        
        result = await detector.detect(alert, context)
        
        assert result.severity == SeverityEnum.CRITICAL
        assert result.alert_type == "EXPLOITER_INTERACTION"
    
    @pytest.mark.asyncio
    async def test_detect_exchange_interaction_medium(self):
        """Test that exchange interaction is marked MEDIUM"""
        detector = AddressGraphDetector()
        
        alert = AlertInput(chain_id=1, tx_hash="0x123")
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xabc123",
            to_address="0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be",  # Binance
            value=1000000000000000000,
            input_data="0x"
        )
        
        result = await detector.detect(alert, context)
        
        assert result.severity == SeverityEnum.MEDIUM
        assert result.alert_type == "EXCHANGE_INTERACTION"


class TestAddressGraphDetectorAnalysis:
    """Test analysis methods of AddressGraphDetector"""
    
    def test_check_exchange_interaction(self):
        """Test exchange interaction detection"""
        detector = AddressGraphDetector()
        
        is_exchange, name = detector._check_exchange_interaction(
            "0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be", 1
        )
        assert is_exchange is True
        assert name == "Binance"
        
        is_exchange, name = detector._check_exchange_interaction("0xunknown", 1)
        assert is_exchange is False
        assert name is None
    
    def test_check_exploiter_interaction(self):
        """Test exploiter interaction detection"""
        detector = AddressGraphDetector()
        
        is_exploiter, name = detector._check_exploiter_interaction(
            "0xab7535b4a1b3c2d2c7e7c7c7c7c7c7c7c7c7c7c7"
        )
        assert is_exploiter is True
        assert name == "Known Exploiter"
        
        is_exploiter, name = detector._check_exploiter_interaction("0xunknown")
        assert is_exploiter is False
        assert name is None
    
    def test_analyze_fund_flow_direct_transfer(self):
        """Test fund flow analysis for direct transfer"""
        detector = AddressGraphDetector()
        
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xabc",
            to_address="0xdef",
            value=1000000000000000000,
            input_data="0x"
        )
        
        flow = detector._analyze_fund_flow(context)
        
        assert flow["direction"] == "direct_transfer"
        assert flow["potential_type"] == "direct_transfer"
    
    def test_analyze_fund_flow_contract_interaction(self):
        """Test fund flow analysis for contract interaction"""
        detector = AddressGraphDetector()
        
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xabc",
            to_address="0xdef",
            value=1000000000000000000,
            input_data="0xdeadbeef"
        )
        
        flow = detector._analyze_fund_flow(context)
        
        assert flow["potential_type"] == "contract_interaction"
        assert "contract_call_with_value" in flow["indicators"]
    
    def test_is_contract_call(self):
        """Test contract call detection"""
        detector = AddressGraphDetector()
        
        ctx1 = TransactionContext(chain_id=1, tx_hash="0x123", input_data="0x123")
        assert detector._is_contract_call(ctx1) is True
        
        ctx2 = TransactionContext(chain_id=1, tx_hash="0x123", input_data="0x")
        assert detector._is_contract_call(ctx2) is False
        
        ctx3 = TransactionContext(chain_id=1, tx_hash="0x123", input_data=None)
        assert detector._is_contract_call(ctx3) is False


class TestAddressGraphDetectorEdgeCases:
    """Test edge cases for AddressGraphDetector"""
    
    @pytest.mark.asyncio
    async def test_none_addresses(self):
        """Test with None addresses"""
        detector = AddressGraphDetector()
        
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
    
    @pytest.mark.asyncio
    async def test_no_chain_id_mapping(self):
        """Test with unknown chain"""
        detector = AddressGraphDetector()
        
        alert = AlertInput(chain_id=999, tx_hash="0x123")  # Unknown chain
        context = TransactionContext(
            chain_id=999,
            tx_hash="0x123",
            from_address="0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be",  # Binance
            to_address="0xdef",
            value=1000,
            input_data="0x"
        )
        
        result = await detector.detect(alert, context)
        
        # Should not detect as exchange since chain 999 is not in known_exchanges
        assert result.detected is False


def run_tests():
    """Run all tests"""
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    run_tests()
