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
            assert result == DBSeverityEnum.CRITICAL
    
    def test_map_severity_low(self):
        """Test mapping LOW severity"""
        from database.models import SeverityEnum as DBSeverityEnum
        from models import SeverityEnum as ModelSeverityEnum
        
        with patch('routers.alert.router.settings') as mock_settings:
            mock_settings.chainId_to_provider_url = {}
            mock_settings.arkm_cookie = None
            
            pipeline = AlertProcessingPipeline()
            
            result = pipeline._map_severity(ModelSeverityEnum.LOW)
            assert result == DBSeverityEnum.SUSPICIOUS
    
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
