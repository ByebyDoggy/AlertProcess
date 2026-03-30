"""
Unit tests for Alert Processing Pipeline
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

import sys
sys.path.insert(0, '/workspace')

from models import AlertInput, TransactionContext, SeverityEnum
from routers.alert.router import AlertProcessingPipeline


class TestAlertProcessingPipeline:
    """Test AlertProcessingPipeline"""
    
    def test_pipeline_creation(self):
        """Test pipeline creation"""
        with patch('routers.alert.router.settings') as mock_settings:
            mock_settings.chainId_to_provider_url = {1: "https://eth.example.com"}
            mock_settings.arkm_cookie = None
            
            pipeline = AlertProcessingPipeline()
            
            assert pipeline.context_builder is not None
            assert len(pipeline.detectors) > 0
            assert pipeline.scoring_engine is not None
            assert pipeline.rule_engine is not None
    
    def test_pipeline_includes_all_detectors(self):
        """Test that pipeline includes all expected detectors"""
        with patch('routers.alert.router.settings') as mock_settings:
            mock_settings.chainId_to_provider_url = {1: "https://eth.example.com"}
            mock_settings.arkm_cookie = None
            
            pipeline = AlertProcessingPipeline()
            
            detector_names = [d.name for d in pipeline.detectors]
            
            assert "gas_price_detector" in detector_names
            assert "address_type_detector" in detector_names
            assert "flash_loan_detector" in detector_names
            assert "token_approval_detector" in detector_names
            assert "token_anomaly_detector" in detector_names
            assert "address_graph_detector" in detector_names
            assert "address_age_detector" in detector_names
    
    @pytest.mark.asyncio
    async def test_pipeline_process_alert(self):
        """Test processing an alert through the pipeline"""
        with patch('routers.alert.router.settings') as mock_settings:
            mock_settings.chainId_to_provider_url = {1: "https://eth.example.com"}
            mock_settings.arkm_cookie = None
            mock_settings.notify_webhook_url = None
            
            pipeline = AlertProcessingPipeline()
            
            alert = AlertInput(
                chain_id=1,
                tx_hash="0x1234567890abcdef",
                attacked_address="0xvictim",
                exploiter_address="0xexploiter"
            )
            
            # Mock context builder
            mock_context = TransactionContext(
                chain_id=1,
                tx_hash="0x1234567890abcdef",
                from_address="0xexploiter",
                to_address="0xvictim",
                value=1000000000000000000,
                gas_price=20000000000,
                block_number=17000000
            )
            
            with patch.object(pipeline.context_builder, 'build', return_value=mock_context):
                result = await pipeline.process(alert)
                
                assert result.alert_id is not None
                assert result.chain_id == 1
                assert result.tx_hash == "0x1234567890abcdef"
                assert result.context is not None
    
    @pytest.mark.asyncio
    async def test_pipeline_with_mock_detectors(self):
        """Test pipeline with mocked detectors"""
        with patch('routers.alert.router.settings') as mock_settings:
            mock_settings.chainId_to_provider_url = {1: "https://eth.example.com"}
            mock_settings.arkm_cookie = None
            mock_settings.notify_webhook_url = None
            
            pipeline = AlertProcessingPipeline()
            
            # Mock all detectors to return empty results
            for detector in pipeline.detectors:
                detector.detect = AsyncMock(return_value=MagicMock(
                    detector_name=detector.name,
                    detected=False,
                    alert_type=None,
                    severity=SeverityEnum.UNKNOWN,
                    metadata={}
                ))
            
            alert = AlertInput(
                chain_id=1,
                tx_hash="0x123",
                attacked_address="0xvictim",
                exploiter_address="0xexploiter"
            )
            
            mock_context = TransactionContext(
                chain_id=1,
                tx_hash="0x123",
                from_address="0xexploiter",
                to_address="0xvictim"
            )
            
            with patch.object(pipeline.context_builder, 'build', return_value=mock_context):
                result = await pipeline.process(alert)
                
                assert result is not None
                assert len(result.detections) == len(pipeline.detectors)


class TestAlertProcessingPipelineMapping:
    """Test severity mapping in pipeline"""
    
    def test_map_severity_critical(self):
        """Test mapping CRITICAL severity"""
        from database.models import SeverityEnum as DBSeverityEnum
        from models import SeverityEnum as ModelSeverityEnum
        
        with patch('routers.alert.router.settings') as mock_settings:
            mock_settings.chainId_to_provider_url = {}
            mock_settings.arkm_cookie = None
            
            pipeline = AlertProcessingPipeline()
            
            result = pipeline._map_severity(ModelSeverityEnum.CRITICAL)
            assert result == DBSeverityEnum.CRITICAL
    
    def test_map_severity_high(self):
        """Test mapping HIGH severity"""
        from database.models import SeverityEnum as DBSeverityEnum
        from models import SeverityEnum as ModelSeverityEnum
        
        with patch('routers.alert.router.settings') as mock_settings:
            mock_settings.chainId_to_provider_url = {}
            mock_settings.arkm_cookie = None
            
            pipeline = AlertProcessingPipeline()
            
            result = pipeline._map_severity(ModelSeverityEnum.HIGH)
            assert result == DBSeverityEnum.CRITICAL  # HIGH maps to CRITICAL
    
    def test_map_severity_low(self):
        """Test mapping LOW severity"""
        from database.models import SeverityEnum as DBSeverityEnum
        from models import SeverityEnum as ModelSeverityEnum
        
        with patch('routers.alert.router.settings') as mock_settings:
            mock_settings.chainId_to_provider_url = {}
            mock_settings.arkm_cookie = None
            
            pipeline = AlertProcessingPipeline()
            
            result = pipeline._map_severity(ModelSeverityEnum.LOW)
            assert result == DBSeverityEnum.SUSPICIOUS  # LOW maps to SUSPICIOUS
    
    def test_map_severity_unknown(self):
        """Test mapping UNKNOWN severity"""
        from database.models import SeverityEnum as DBSeverityEnum
        from models import SeverityEnum as ModelSeverityEnum
        
        with patch('routers.alert.router.settings') as mock_settings:
            mock_settings.chainId_to_provider_url = {}
            mock_settings.arkm_cookie = None
            
            pipeline = AlertProcessingPipeline()
            
            result = pipeline._map_severity(ModelSeverityEnum.UNKNOWN)
            assert result == DBSeverityEnum.UNKNOWN


def run_tests():
    """Run all tests"""
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    run_tests()
