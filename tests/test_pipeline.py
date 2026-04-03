"""
Unit tests for Alert Processing Pipeline
"""
import pytest
from unittest.mock import patch

from models import SeverityEnum
from routers.alert.router import AlertProcessingPipeline, _map_to_db_severity


class TestAlertProcessingPipeline:
    """Test AlertProcessingPipeline"""

    def test_pipeline_creation(self):
        """Test pipeline creation"""
        pipeline = AlertProcessingPipeline()
        assert pipeline is not None

    def test_load_enabled_chains(self):
        """Test _load_enabled_chains returns list"""
        pipeline = AlertProcessingPipeline()
        chains = pipeline._load_enabled_chains()
        assert isinstance(chains, list)


class TestSeverityMapping:
    """Test severity mapping functions"""

    def test_map_severity_critical(self):
        """Test mapping CRITICAL severity"""
        from database.models import SeverityEnum as DBSeverityEnum

        result = _map_to_db_severity(SeverityEnum.CRITICAL)
        assert result == DBSeverityEnum.CRITICAL

    def test_map_severity_high(self):
        """Test mapping HIGH severity"""
        from database.models import SeverityEnum as DBSeverityEnum

        result = _map_to_db_severity(SeverityEnum.HIGH)
        assert result == DBSeverityEnum.CRITICAL

    def test_map_severity_low(self):
        """Test mapping LOW severity"""
        from database.models import SeverityEnum as DBSeverityEnum

        result = _map_to_db_severity(SeverityEnum.LOW)
        assert result == DBSeverityEnum.SUSPICIOUS

    def test_map_severity_unknown(self):
        """Test mapping UNKNOWN severity"""
        from database.models import SeverityEnum as DBSeverityEnum

        result = _map_to_db_severity(SeverityEnum.UNKNOWN)
        assert result == DBSeverityEnum.UNKNOWN


def run_tests():
    """Run all tests"""
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    run_tests()
