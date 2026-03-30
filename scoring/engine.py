"""
Scoring Engine for configurable threat scoring
Replaces hardcoded scoring with user-configurable scoring methods
"""
from abc import ABC, abstractmethod
from typing import Any
from pydantic import BaseModel

from models import AlertInput, TransactionContext, DetectionResult, SeverityEnum


class ScoringDimension(BaseModel):
    """A single dimension for scoring"""
    name: str
    weight: float = 1.0
    scoring_type: str = "threshold"  # "threshold", "categorical", "inverse_time", "linear"
    scoring_config: dict[str, Any] = {}


class SeverityThreshold(BaseModel):
    """Severity threshold configuration"""
    severity: SeverityEnum
    min_score: float


class ScoringConfig(BaseModel):
    """Scoring engine configuration"""
    method: str = "weighted_sum"  # "weighted_sum", "rule_based", "max", "sum"
    dimensions: list[ScoringDimension] = []
    severity_thresholds: list[SeverityThreshold] = [
        SeverityThreshold(severity=SeverityEnum.CRITICAL, min_score=80),
        SeverityThreshold(severity=SeverityEnum.HIGH, min_score=60),
        SeverityThreshold(severity=SeverityEnum.MEDIUM, min_score=40),
        SeverityThreshold(severity=SeverityEnum.LOW, min_score=20),
    ]
    base_score: float = 0.0


class ScoringResult(BaseModel):
    """Result of scoring calculation"""
    total_score: float
    severity: SeverityEnum
    dimension_scores: dict[str, float] = {}
    dimension_weights: dict[str, float] = {}
    scoring_details: dict[str, Any] = {}
    
    def __str__(self) -> str:
        return f"ScoringResult(score={self.total_score:.1f}, severity={self.severity.value})"


class ScoringMethod(ABC):
    """Base class for scoring methods"""
    
    def __init__(self, config: ScoringConfig):
        self.config = config
    
    @abstractmethod
    def calculate(
        self,
        context: TransactionContext,
        detections: list[DetectionResult]
    ) -> ScoringResult:
        """Calculate final score"""
        pass


class WeightedSumScoring(ScoringMethod):
    """
    Weighted sum scoring method
    
    Calculates score as weighted sum of dimension scores:
    score = sum(dimension_score[i] * weight[i]) / sum(weights)
    """
    
    def calculate(
        self,
        context: TransactionContext,
        detections: list[DetectionResult]
    ) -> ScoringResult:
        dimension_scores = {}
        dimension_weights = {}
        total_weighted_score = 0.0
        total_weight = 0.0
        
        for dim in self.config.dimensions:
            score = self._calculate_dimension_score(dim, context, detections)
            dimension_scores[dim.name] = score
            dimension_weights[dim.name] = dim.weight
            total_weighted_score += score * dim.weight
            total_weight += dim.weight
        
        if total_weight > 0:
            final_score = total_weighted_score / total_weight
        else:
            final_score = self.config.base_score
        
        final_score = min(100.0, max(0.0, final_score))  # Clamp to 0-100
        
        severity = self._calculate_severity(final_score)
        
        return ScoringResult(
            total_score=final_score,
            severity=severity,
            dimension_scores=dimension_scores,
            dimension_weights=dimension_weights,
            scoring_details={"method": "weighted_sum", "total_weight": total_weight}
        )
    
    def _calculate_dimension_score(
        self,
        dim: ScoringDimension,
        context: TransactionContext,
        detections: list[DetectionResult]
    ) -> float:
        """Calculate score for a single dimension"""
        if dim.scoring_type == "threshold":
            return self._score_threshold(dim, context, detections)
        elif dim.scoring_type == "categorical":
            return self._score_categorical(dim, context, detections)
        elif dim.scoring_type == "inverse_time":
            return self._score_inverse_time(dim, context, detections)
        elif dim.scoring_type == "linear":
            return self._score_linear(dim, context, detections)
        else:
            return 0.0
    
    def _score_threshold(
        self,
        dim: ScoringDimension,
        context: TransactionContext,
        detections: list[DetectionResult]
    ) -> float:
        """Score based on threshold comparison"""
        config = dim.scoring_config
        field = config.get("field", "")
        threshold = config.get("threshold", 0)
        score_above = config.get("score_above", 100)
        score_below = config.get("score_below", 0)
        
        value = self._resolve_field(field, context, detections)
        if value is None:
            return score_below
        
        try:
            if float(value) > threshold:
                return score_above
            else:
                return score_below
        except (ValueError, TypeError):
            return score_below
    
    def _score_categorical(
        self,
        dim: ScoringDimension,
        context: TransactionContext,
        detections: list[DetectionResult]
    ) -> float:
        """Score based on categorical values"""
        config = dim.scoring_config
        field = config.get("field", "")
        values_map = config.get("values", {})
        
        value = self._resolve_field(field, context, detections)
        if value is None:
            return values_map.get("unknown", 50)
        
        return values_map.get(str(value), values_map.get("default", 50))
    
    def _score_inverse_time(
        self,
        dim: ScoringDimension,
        context: TransactionContext,
        detections: list[DetectionResult]
    ) -> float:
        """Score based on inverse time (newer = higher score)"""
        config = dim.scoring_config
        field = config.get("field", "")  # Field containing timestamp or days
        max_days = config.get("max_days", 365)
        min_score = config.get("min_score", 0)
        max_score = config.get("max_score", 100)
        
        value = self._resolve_field(field, context, detections)
        if value is None:
            return min_score
        
        try:
            days = float(value)
            if days <= 0:
                return max_score
            score = max_score * (1 - min(days, max_days) / max_days)
            return max(min_score, min(max_score, score))
        except (ValueError, TypeError):
            return min_score
    
    def _score_linear(
        self,
        dim: ScoringDimension,
        context: TransactionContext,
        detections: list[DetectionResult]
    ) -> float:
        """Score based on linear interpolation"""
        config = dim.scoring_config
        field = config.get("field", "")
        min_value = config.get("min_value", 0)
        max_value = config.get("max_value", 100)
        min_score = config.get("min_score", 0)
        max_score = config.get("max_score", 100)
        
        value = self._resolve_field(field, context, detections)
        if value is None:
            return min_score
        
        try:
            value = float(value)
            if value <= min_value:
                return min_score
            if value >= max_value:
                return max_score
            
            ratio = (value - min_value) / (max_value - min_value)
            return min_score + ratio * (max_score - min_score)
        except (ValueError, TypeError):
            return min_score
    
    def _resolve_field(
        self,
        field: str,
        context: TransactionContext,
        detections: list[DetectionResult]
    ) -> Any:
        """Resolve field path to value"""
        if not field:
            return None
        
        parts = field.split(".", 1)
        
        if parts[0] == "context":
            return getattr(context, parts[1], None) if len(parts) > 1 else None
        elif parts[0] == "detector" or parts[0] == "detection":
            if len(parts) < 2:
                return None
            detector_name = parts[1].split(".")[0]
            for d in detections:
                if d.detector_name == detector_name:
                    if "." in parts[1]:
                        return d.metadata.get(parts[1].split(".", 1)[1])
                    return d.detected
            return None
        else:
            return getattr(context, field, None)
    
    def _calculate_severity(self, score: float) -> SeverityEnum:
        """Calculate severity based on score"""
        thresholds = sorted(
            self.config.severity_thresholds,
            key=lambda t: -t.min_score  # Sort descending
        )
        
        for threshold in thresholds:
            if score >= threshold.min_score:
                return threshold.severity
        
        return SeverityEnum.UNKNOWN


class RuleBasedScoring(ScoringMethod):
    """
    Rule-based scoring method
    
    Score is determined by matched rules. Each rule can add or set a score.
    """
    
    def calculate(
        self,
        context: TransactionContext,
        detections: list[DetectionResult]
    ) -> ScoringResult:
        """Calculate score based on matched rules"""
        # This will be integrated with the Rule Engine later
        # For now, return base score
        return ScoringResult(
            total_score=self.config.base_score,
            severity=SeverityEnum.UNKNOWN,
            dimension_scores={},
            dimension_weights={},
            scoring_details={"method": "rule_based", "note": "Requires rule evaluation"}
        )


class MaxScoring(ScoringMethod):
    """
    Maximum scoring method
    
    Final score is the maximum of all dimension scores.
    """
    
    def calculate(
        self,
        context: TransactionContext,
        detections: list[DetectionResult]
    ) -> ScoringResult:
        dimension_scores = {}
        
        for dim in self.config.dimensions:
            score = self._calculate_dimension_score(dim, context, detections)
            dimension_scores[dim.name] = score
        
        if dimension_scores:
            final_score = max(dimension_scores.values())
        else:
            final_score = self.config.base_score
        
        final_score = min(100.0, max(0.0, final_score))
        severity = self._calculate_severity(final_score)
        
        return ScoringResult(
            total_score=final_score,
            severity=severity,
            dimension_scores=dimension_scores,
            dimension_weights={},
            scoring_details={"method": "max"}
        )
    
    def _calculate_dimension_score(
        self,
        dim: ScoringDimension,
        context: TransactionContext,
        detections: list[DetectionResult]
    ) -> float:
        """Calculate dimension score"""
        config = dim.scoring_config
        field = config.get("field", "")
        threshold = config.get("threshold", 0)
        score_above = config.get("score_above", 100)
        score_below = config.get("score_below", 0)
        
        value = self._resolve_field(field, context, detections)
        if value is None:
            return score_below
        
        try:
            if float(value) > threshold:
                return score_above
            return score_below
        except (ValueError, TypeError):
            return score_below
    
    def _resolve_field(self, field: str, context: TransactionContext, detections: list[DetectionResult]) -> Any:
        if not field:
            return None
        parts = field.split(".", 1)
        if parts[0] == "context":
            return getattr(context, parts[1], None) if len(parts) > 1 else None
        return getattr(context, field, None)
    
    def _calculate_severity(self, score: float) -> SeverityEnum:
        thresholds = sorted(self.config.severity_thresholds, key=lambda t: -t.min_score)
        for threshold in thresholds:
            if score >= threshold.min_score:
                return threshold.severity
        return SeverityEnum.UNKNOWN


class ScoringEngine:
    """
    Main scoring engine that coordinates scoring methods
    
    Usage:
        config = ScoringConfig(method="weighted_sum", dimensions=[...])
        engine = ScoringEngine(config)
        result = engine.calculate(context, detections)
    """
    
    _methods: dict[str, type[ScoringMethod]] = {
        "weighted_sum": WeightedSumScoring,
        "rule_based": RuleBasedScoring,
        "max": MaxScoring,
    }
    
    def __init__(self, config: ScoringConfig | None = None):
        self.config = config or ScoringConfig()
        self.method = self._create_method()
    
    def _create_method(self) -> ScoringMethod:
        """Create scoring method based on config"""
        method_class = self._methods.get(self.config.method, WeightedSumScoring)
        return method_class(self.config)
    
    def calculate(
        self,
        context: TransactionContext,
        detections: list[DetectionResult]
    ) -> ScoringResult:
        """Calculate final score"""
        return self.method.calculate(context, detections)
    
    @classmethod
    def register_method(cls, name: str, method_class: type[ScoringMethod]):
        """Register a custom scoring method"""
        cls._methods[name] = method_class


class DefaultScoringConfig:
    """
    Default scoring configuration factory
    
    Provides common scoring configurations for different use cases.
    """
    
    @staticmethod
    def basic() -> ScoringConfig:
        """Basic scoring with just detection presence"""
        return ScoringConfig(
            method="weighted_sum",
            dimensions=[
                ScoringDimension(
                    name="detection_count",
                    weight=1.0,
                    scoring_type="linear",
                    scoring_config={
                        "min_value": 0,
                        "max_value": 5,
                        "min_score": 0,
                        "max_score": 100
                    }
                )
            ]
        )
    
    @staticmethod
    def exploit_analysis() -> ScoringConfig:
        """
        Scoring configuration for exploit analysis
        
        Dimensions:
        - exploiter_age: How old is the exploiter address (newer = higher risk)
        - entity_type: Is the entity tagged as hacker/malicious
        - gas_anomaly: Is gas price suspiciously high
        - value_transfer: Is the transfer value significant
        """
        return ScoringConfig(
            method="weighted_sum",
            dimensions=[
                ScoringDimension(
                    name="exploiter_age",
                    weight=0.3,
                    scoring_type="inverse_time",
                    scoring_config={
                        "field": "context.exploiter_age_days",
                        "max_days": 365,
                        "min_score": 0,
                        "max_score": 100
                    }
                ),
                ScoringDimension(
                    name="entity_type",
                    weight=0.4,
                    scoring_type="categorical",
                    scoring_config={
                        "field": "detector.arkm_label_detector.metadata.entity_type",
                        "values": {
                            "hacker": 100,
                            "suspicious": 70,
                            "unknown": 50,
                            "trusted": 0,
                            "default": 50
                        }
                    }
                ),
                ScoringDimension(
                    name="gas_anomaly",
                    weight=0.15,
                    scoring_type="threshold",
                    scoring_config={
                        "field": "detector.gas_price_detector.metadata.gas_price_usd",
                        "threshold": 100,
                        "score_above": 80,
                        "score_below": 20
                    }
                ),
                ScoringDimension(
                    name="value_transfer",
                    weight=0.15,
                    scoring_type="linear",
                    scoring_config={
                        "field": "context.value_in_eth",
                        "min_value": 0,
                        "max_value": 1000000,  # 1M ETH
                        "min_score": 0,
                        "max_score": 100
                    }
                )
            ]
        )
