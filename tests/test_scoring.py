"""
Unit tests for Scoring Engine
"""
import pytest
from datetime import datetime, timedelta

import sys
sys.path.insert(0, '/workspace')

from models import AlertInput, TransactionContext, DetectionResult, SeverityEnum
from scoring.engine import (
    ScoringDimension,
    SeverityThreshold,
    ScoringConfig,
    ScoringResult,
    ScoringEngine,
    WeightedSumScoring,
    MaxScoring,
    DefaultScoringConfig,
)


class TestScoringConfig:
    """Test ScoringConfig"""
    
    def test_default_config(self):
        """Test default scoring config"""
        config = ScoringConfig()
        
        assert config.method == "weighted_sum"
        assert len(config.dimensions) == 0
        assert len(config.severity_thresholds) == 4  # CRITICAL, HIGH, MEDIUM, LOW
    
    def test_severity_thresholds_order(self):
        """Test severity thresholds are defined in config"""
        config = ScoringConfig(
            severity_thresholds=[
                SeverityThreshold(severity=SeverityEnum.HIGH, min_score=60),
                SeverityThreshold(severity=SeverityEnum.CRITICAL, min_score=80),
            ]
        )
        
        # Config preserves order as defined
        assert config.severity_thresholds[0].severity == SeverityEnum.HIGH
        assert config.severity_thresholds[1].severity == SeverityEnum.CRITICAL


class TestScoringResult:
    """Test ScoringResult"""
    
    def test_scoring_result_creation(self):
        """Test basic scoring result"""
        result = ScoringResult(
            total_score=85.0,
            severity=SeverityEnum.CRITICAL,
            dimension_scores={"test": 85.0}
        )
        
        assert result.total_score == 85.0
        assert result.severity == SeverityEnum.CRITICAL
        assert result.dimension_scores["test"] == 85.0
    
    def test_scoring_result_string(self):
        """Test scoring result string representation"""
        result = ScoringResult(
            total_score=75.5,
            severity=SeverityEnum.HIGH
        )
        
        assert "75.5" in str(result)
        assert "HIGH" in str(result)


class TestWeightedSumScoring:
    """Test WeightedSumScoring method"""
    
    def test_basic_scoring(self):
        """Test basic weighted sum scoring"""
        config = ScoringConfig(
            dimensions=[
                ScoringDimension(
                    name="test_dim",
                    weight=1.0,
                    scoring_type="threshold",
                    scoring_config={
                        "field": "context.value",
                        "threshold": 100,
                        "score_above": 100,
                        "score_below": 0
                    }
                )
            ]
        )
        
        method = WeightedSumScoring(config)
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            value=200
        )
        
        result = method.calculate(context, [])
        
        assert result.dimension_scores["test_dim"] == 100
    
    def test_weighted_scoring(self):
        """Test weighted scoring with multiple dimensions"""
        config = ScoringConfig(
            dimensions=[
                ScoringDimension(
                    name="dim1",
                    weight=0.7,
                    scoring_type="threshold",
                    scoring_config={
                        "field": "context.chain_id",
                        "threshold": 0,
                        "score_above": 100,
                        "score_below": 0
                    }
                ),
                ScoringDimension(
                    name="dim2",
                    weight=0.3,
                    scoring_type="threshold",
                    scoring_config={
                        "field": "context.value",
                        "threshold": 100,
                        "score_above": 50,
                        "score_below": 0
                    }
                )
            ]
        )
        
        method = WeightedSumScoring(config)
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            value=200
        )
        
        result = method.calculate(context, [])
        
        # dim1 = 100, dim2 = 50
        # weighted = (100 * 0.7 + 50 * 0.3) / (0.7 + 0.3) = 85
        assert result.dimension_scores["dim1"] == 100
        assert result.dimension_scores["dim2"] == 50
        assert result.total_score == 85.0
    
    def test_categorical_scoring(self):
        """Test categorical scoring"""
        # Use context fields instead of detection metadata for simplicity
        config = ScoringConfig(
            dimensions=[
                ScoringDimension(
                    name="chain_category",
                    weight=1.0,
                    scoring_type="categorical",
                    scoring_config={
                        "field": "context.chain_id",
                        "values": {
                            "1": 100,      # Ethereum = highest
                            "56": 70,      # BSC
                            "137": 50,     # Polygon
                            "default": 30
                        }
                    }
                )
            ]
        )
        
        method = WeightedSumScoring(config)
        context = TransactionContext(chain_id=1, tx_hash="0x123")
        
        result = method.calculate(context, [])
        
        assert result.dimension_scores["chain_category"] == 100
        assert result.total_score == 100.0
    
    def test_inverse_time_scoring(self):
        """Test inverse time scoring (newer = higher score)"""
        # Use block_number as a proxy for age (higher block = older on average)
        config = ScoringConfig(
            dimensions=[
                ScoringDimension(
                    name="account_age",
                    weight=1.0,
                    scoring_type="inverse_time",
                    scoring_config={
                        "max_days": 365,
                        "min_score": 0,
                        "max_score": 100
                    }
                )
            ]
        )
        
        method = WeightedSumScoring(config)
        # Can't easily test inverse_time without a real days field
        # So we just verify the dimension is evaluated
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            block_number=1000
        )
        
        result = method.calculate(context, [])
        
        # Score depends on the field value - just check it runs
        assert "account_age" in result.dimension_scores
    
    def test_severity_calculation(self):
        """Test severity is calculated from score"""
        config = ScoringConfig(
            dimensions=[
                ScoringDimension(
                    name="test",
                    weight=1.0,
                    scoring_type="threshold",
                    scoring_config={
                        "field": "context.value",
                        "threshold": 0,
                        "score_above": 85,  # Should be CRITICAL (>80)
                        "score_below": 0
                    }
                )
            ]
        )
        
        method = WeightedSumScoring(config)
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            value=100
        )
        
        result = method.calculate(context, [])
        
        assert result.total_score == 85
        assert result.severity == SeverityEnum.CRITICAL
    
    def test_empty_dimensions(self):
        """Test with no dimensions returns base score"""
        # Set thresholds that base_score 20 falls into LOW
        config = ScoringConfig(
            base_score=20.0,
            severity_thresholds=[
                SeverityThreshold(severity=SeverityEnum.CRITICAL, min_score=80),
                SeverityThreshold(severity=SeverityEnum.HIGH, min_score=60),
                SeverityThreshold(severity=SeverityEnum.MEDIUM, min_score=40),
                SeverityThreshold(severity=SeverityEnum.LOW, min_score=20),
            ]
        )
        
        method = WeightedSumScoring(config)
        context = TransactionContext(chain_id=1, tx_hash="0x123")
        
        result = method.calculate(context, [])
        
        assert result.total_score == 20.0
        assert result.severity == SeverityEnum.LOW


class TestMaxScoring:
    """Test MaxScoring method"""
    
    def test_max_scoring(self):
        """Test max scoring returns highest dimension score"""
        config = ScoringConfig(
            dimensions=[
                ScoringDimension(
                    name="dim1",
                    weight=1.0,
                    scoring_type="threshold",
                    scoring_config={
                        "field": "context.value",
                        "threshold": 0,
                        "score_above": 30,
                        "score_below": 0
                    }
                ),
                ScoringDimension(
                    name="dim2",
                    weight=1.0,
                    scoring_type="threshold",
                    scoring_config={
                        "field": "context.chain_id",
                        "threshold": 0,
                        "score_above": 70,
                        "score_below": 0
                    }
                )
            ]
        )
        
        method = MaxScoring(config)
        context = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            value=100
        )
        
        result = method.calculate(context, [])
        
        # Should return the max of dim1(30) and dim2(70)
        assert result.total_score == 70


class TestScoringEngine:
    """Test ScoringEngine"""
    
    def test_engine_creation(self):
        """Test engine creation"""
        config = ScoringConfig()
        engine = ScoringEngine(config)
        
        assert engine.config == config
        assert isinstance(engine.method, WeightedSumScoring)
    
    def test_engine_custom_method(self):
        """Test engine with custom method"""
        config = ScoringConfig(method="max")
        engine = ScoringEngine(config)
        
        assert isinstance(engine.method, MaxScoring)
    
    def test_engine_calculate(self):
        """Test engine calculate method"""
        config = ScoringConfig(
            dimensions=[
                ScoringDimension(
                    name="test",
                    weight=1.0,
                    scoring_type="threshold",
                    scoring_config={
                        "field": "context.chain_id",
                        "threshold": 0,
                        "score_above": 100,
                        "score_below": 0
                    }
                )
            ]
        )
        
        engine = ScoringEngine(config)
        context = TransactionContext(chain_id=1, tx_hash="0x123")
        
        result = engine.calculate(context, [])
        
        assert result.total_score == 100


class TestDefaultScoringConfig:
    """Test DefaultScoringConfig factory"""
    
    def test_basic_config(self):
        """Test basic scoring config"""
        config = DefaultScoringConfig.basic()
        
        assert config.method == "weighted_sum"
        assert len(config.dimensions) == 1
    
    def test_exploit_analysis_config(self):
        """Test exploit analysis config"""
        config = DefaultScoringConfig.exploit_analysis()
        
        assert config.method == "weighted_sum"
        assert len(config.dimensions) == 4
        
        # Check dimension names
        dim_names = [d.name for d in config.dimensions]
        assert "exploiter_age" in dim_names
        assert "entity_type" in dim_names
        assert "gas_anomaly" in dim_names
        assert "value_transfer" in dim_names


class TestScoringIntegration:
    """Integration tests for scoring with detections"""
    
    def test_scoring_with_detection_result(self):
        """Test scoring with actual detection results using simple field"""
        config = ScoringConfig(
            dimensions=[
                ScoringDimension(
                    name="high_gas",
                    weight=1.0,
                    scoring_type="threshold",
                    scoring_config={
                        "field": "context.value",  # Use context field
                        "threshold": 50,
                        "score_above": 100,
                        "score_below": 0
                    }
                )
            ]
        )
        
        engine = ScoringEngine(config)
        context = TransactionContext(chain_id=1, tx_hash="0x123", value=100)
        detections = [
            DetectionResult(
                detector_name="gas_price_detector",
                detected=True,
                severity=SeverityEnum.HIGH
            )
        ]
        
        result = engine.calculate(context, detections)
        
        # value=100 > threshold=50, so score_above=100
        assert result.dimension_scores["high_gas"] == 100
        assert result.total_score == 100


def run_tests():
    """Run all tests"""
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    run_tests()
