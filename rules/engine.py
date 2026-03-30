"""
Rule Engine for configurable alert rule evaluation
Supports user-defined rules with AND/OR/NOT conditions and data fetching
"""
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel
import re

from models import AlertInput, TransactionContext, DetectionResult


class ConditionOperator(str, Enum):
    """Supported condition operators"""
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    GREATER_THAN_OR_EQUALS = "greater_than_or_equals"
    LESS_THAN_OR_EQUALS = "less_than_or_equals"
    IN_LIST = "in_list"
    NOT_IN_LIST = "not_in_list"
    REGEX = "regex"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"


class RuleCondition(BaseModel):
    """Single condition definition"""
    field: str  # Field path to evaluate (e.g., "detections.gas_price_detector.detected" or "context.gas_price_usd")
    operator: ConditionOperator
    value: Any = None
    negation: bool = False  # If True, negate the condition result


class CompoundCondition(BaseModel):
    """AND/OR combination of conditions"""
    type: str  # "AND" or "OR"
    conditions: list[dict] = []  # List of RuleCondition or CompoundCondition
    negation: bool = False


class RuleAction(BaseModel):
    """Action to perform when rule matches"""
    set_severity: Optional[str] = None  # Set alert severity
    set_score: Optional[float] = None  # Set alert score
    add_tags: list[str] = []  # Add tags to alert
    set_metadata: dict[str, Any] = {}  # Set metadata fields


class RuleConfig(BaseModel):
    """Rule configuration"""
    name: str
    description: str = ""
    enabled: bool = True
    priority: int = 0  # Higher priority rules evaluated first
    condition: dict  # RuleCondition or CompoundCondition
    action: RuleAction = RuleAction()
    
    # Data sources required for this rule (optional)
    data_sources: list[dict] = []  # [{"provider": "arkm", "method": "get_labels", "params": {...}}]


class RuleEvaluationResult(BaseModel):
    """Result of rule evaluation"""
    rule_name: str
    matched: bool = False
    matched_conditions: list[str] = []
    severity: Optional[str] = None
    score: Optional[float] = None
    tags: list[str] = []
    metadata: dict[str, Any] = {}
    data_fetched: dict[str, Any] = {}  # Data fetched by this rule


class ConditionEvaluator:
    """
    Evaluates conditions against detection results and context
    """
    
    @staticmethod
    def evaluate_condition(
        condition: dict | RuleCondition | CompoundCondition,
        context: TransactionContext,
        detections: list[DetectionResult],
        fetched_data: dict[str, Any]
    ) -> tuple[bool, list[str]]:
        """
        Evaluate a condition (simple or compound)
        
        Returns:
            (result, matched_condition_descriptions)
        """
        # Handle dict input
        if isinstance(condition, dict):
            if condition.get("type") in ("AND", "OR"):
                return ConditionEvaluator._evaluate_compound(condition, context, detections, fetched_data)
            else:
                return ConditionEvaluator._evaluate_simple(condition, context, detections, fetched_data)
        
        # Handle model input
        if hasattr(condition, 'type') and condition.type in ("AND", "OR"):
            return ConditionEvaluator._evaluate_compound(condition, context, detections, fetched_data)
        else:
            return ConditionEvaluator._evaluate_simple(condition, context, detections, fetched_data)
    
    @staticmethod
    def _evaluate_compound(
        condition: dict | CompoundCondition,
        context: TransactionContext,
        detections: list[DetectionResult],
        fetched_data: dict[str, Any]
    ) -> tuple[bool, list[str]]:
        """Evaluate AND/OR compound condition"""
        results = []
        matched = []
        
        # Handle both dict and model
        conditions = condition.get("conditions") if isinstance(condition, dict) else condition.conditions
        cond_type = condition.get("type") if isinstance(condition, dict) else condition.type
        negation = condition.get("negation") if isinstance(condition, dict) else condition.negation
        
        for sub_condition in conditions:
            sub_result, sub_matched = ConditionEvaluator.evaluate_condition(
                sub_condition, context, detections, fetched_data
            )
            results.append(sub_result)
            matched.extend(sub_matched)
        
        if cond_type == "AND":
            final_result = all(results)
        elif cond_type == "OR":
            final_result = any(results)
        else:
            final_result = False
        
        if negation:
            final_result = not final_result
        
        return final_result, matched
    
    @staticmethod
    def _evaluate_simple(
        condition: dict | RuleCondition,
        context: TransactionContext,
        detections: list[DetectionResult],
        fetched_data: dict[str, Any]
    ) -> tuple[bool, list[str]]:
        """Evaluate a single condition"""
        # Handle both dict and model
        field = condition.get("field") if isinstance(condition, dict) else condition.field
        operator = condition.get("operator") if isinstance(condition, dict) else condition.operator
        value = condition.get("value") if isinstance(condition, dict) else condition.value
        negation = condition.get("negation") if isinstance(condition, dict) else condition.negation
        
        # Convert string operator to enum if needed
        if isinstance(operator, str):
            operator = ConditionOperator(operator)
        
        field_value = ConditionEvaluator._resolve_field(
            field, context, detections, fetched_data
        )
        
        result = ConditionEvaluator._apply_operator(
            operator, field_value, value
        )
        
        if negation:
            result = not result
        
        matched_desc = f"{field} {operator.value if isinstance(operator, ConditionOperator) else operator} {value}"
        return result, [matched_desc] if result else []
    
    @staticmethod
    def _resolve_field(
        field: str,
        context: TransactionContext,
        detections: list[DetectionResult],
        fetched_data: dict[str, Any]
    ) -> Any:
        """
        Resolve a field path to its value
        
        Field patterns:
        - "context.field_name" -> context attributes
        - "detection.detector_name.field" -> detection metadata
        - "fetched.provider_name.field" -> fetched external data
        - "detector.detector_name" -> shorthand for detection result
        """
        parts = field.split(".", 1)
        
        if parts[0] == "context":
            return getattr(context, parts[1], None)
        
        elif parts[0] == "detection" or parts[0] == "detector":
            if len(parts) < 2:
                return None
            detector_name = parts[1].split(".")[0]
            for d in detections:
                if d.detector_name == detector_name:
                    if "." in parts[1]:
                        return d.metadata.get(parts[1].split(".", 1)[1])
                    return d.detected
            return None
        
        elif parts[0] == "fetched":
            if len(parts) < 2:
                return None
            key = parts[1]
            return fetched_data.get(key)
        
        else:
            # Try context first, then detections
            if hasattr(context, field):
                return getattr(context, field)
            for d in detections:
                if d.detector_name == field:
                    return d.detected
            return None
    
    @staticmethod
    def _apply_operator(operator: ConditionOperator, field_value: Any, expected_value: Any) -> bool:
        """Apply operator to compare field value with expected value"""
        if operator == ConditionOperator.IS_NULL:
            return field_value is None
        elif operator == ConditionOperator.IS_NOT_NULL:
            return field_value is not None
        
        if field_value is None:
            return False
        
        try:
            if operator == ConditionOperator.EQUALS:
                return field_value == expected_value
            elif operator == ConditionOperator.NOT_EQUALS:
                return field_value != expected_value
            elif operator == ConditionOperator.CONTAINS:
                if isinstance(field_value, str):
                    return expected_value in field_value
                if isinstance(field_value, (list, tuple)):
                    return expected_value in field_value
                return False
            elif operator == ConditionOperator.NOT_CONTAINS:
                if isinstance(field_value, str):
                    return expected_value not in field_value
                if isinstance(field_value, (list, tuple)):
                    return expected_value not in field_value
                return True
            elif operator == ConditionOperator.GREATER_THAN:
                return float(field_value) > float(expected_value)
            elif operator == ConditionOperator.LESS_THAN:
                return float(field_value) < float(expected_value)
            elif operator == ConditionOperator.GREATER_THAN_OR_EQUALS:
                return float(field_value) >= float(expected_value)
            elif operator == ConditionOperator.LESS_THAN_OR_EQUALS:
                return float(field_value) <= float(expected_value)
            elif operator == ConditionOperator.IN_LIST:
                return field_value in expected_value
            elif operator == ConditionOperator.NOT_IN_LIST:
                return field_value not in expected_value
            elif operator == ConditionOperator.REGEX:
                return bool(re.match(expected_value, str(field_value)))
        except (ValueError, TypeError):
            return False
        
        return False


class Rule:
    """
    Base class for alert rules
    
    Rules evaluate conditions against detection results and context,
    then perform actions when matched.
    """
    
    def __init__(self, config: RuleConfig):
        self.config = config
        self.name = config.name
        self.description = config.description
        self.enabled = config.enabled
        self.priority = config.priority
    
    async def evaluate(
        self,
        context: TransactionContext,
        detections: list[DetectionResult],
        fetched_data: dict[str, Any]
    ) -> RuleEvaluationResult:
        """
        Evaluate this rule against the given context and detections
        
        Args:
            context: Transaction context
            detections: List of detection results from detectors
            fetched_data: Data fetched by data providers
            
        Returns:
            RuleEvaluationResult with match status and actions
        """
        if not self.enabled:
            return RuleEvaluationResult(rule_name=self.name, matched=False)
        
        try:
            matched, matched_conditions = ConditionEvaluator.evaluate_condition(
                self.config.condition,
                context,
                detections,
                fetched_data
            )
            
            result = RuleEvaluationResult(
                rule_name=self.name,
                matched=matched,
                matched_conditions=matched_conditions,
                data_fetched=fetched_data
            )
            
            if matched:
                if self.config.action.set_severity:
                    result.severity = self.config.action.set_severity
                if self.config.action.set_score is not None:
                    result.score = self.config.action.set_score
                result.tags = list(self.config.action.add_tags)
                result.metadata = dict(self.config.action.set_metadata)
            
            return result
            
        except Exception as e:
            return RuleEvaluationResult(
                rule_name=self.name,
                matched=False,
                metadata={"error": str(e)}
            )
    
    def __repr__(self) -> str:
        return f"Rule(name={self.name}, priority={self.priority}, enabled={self.enabled})"


class RuleRegistry:
    """
    Registry for managing rules
    """
    
    _rules: dict[str, Rule] = {}
    
    @classmethod
    def register(cls, rule: Rule):
        """Register a rule"""
        cls._rules[rule.name] = rule
    
    @classmethod
    def get(cls, name: str) -> Rule | None:
        """Get rule by name"""
        return cls._rules.get(name)
    
    @classmethod
    def unregister(cls, name: str):
        """Remove rule from registry"""
        if name in cls._rules:
            del cls._rules[name]
    
    @classmethod
    def list_rules(cls) -> list[str]:
        """List all registered rule names"""
        return list(cls._rules.keys())
    
    @classmethod
    def get_all(cls) -> list[Rule]:
        """Get all registered rules sorted by priority"""
        rules = sorted(cls._rules.values(), key=lambda r: -r.priority)
        return rules
    
    @classmethod
    def clear(cls):
        """Clear all rules"""
        cls._rules.clear()


class RuleEngine:
    """
    Engine for evaluating rules against alerts
    
    Coordinates rule evaluation, data fetching, and result aggregation.
    """
    
    def __init__(self, rules: list[Rule] | None = None):
        self.rules = rules or []
    
    def add_rule(self, rule: Rule):
        """Add a rule to the engine"""
        self.rules.append(rule)
        self.rules.sort(key=lambda r: -r.priority)  # Keep sorted by priority
    
    def remove_rule(self, name: str):
        """Remove a rule by name"""
        self.rules = [r for r in self.rules if r.name != name]
    
    async def evaluate(
        self,
        context: TransactionContext,
        detections: list[DetectionResult],
        fetched_data: dict[str, Any] | None = None
    ) -> list[RuleEvaluationResult]:
        """
        Evaluate all enabled rules against the given context and detections
        
        Args:
            context: Transaction context
            detections: List of detection results
            fetched_data: Pre-fetched external data (optional)
            
        Returns:
            List of RuleEvaluationResults for all rules
        """
        fetched_data = fetched_data or {}
        results = []
        
        for rule in self.rules:
            if not rule.enabled:
                continue
            
            result = await rule.evaluate(context, detections, fetched_data)
            results.append(result)
        
        return results
    
    async def evaluate_until_first_match(
        self,
        context: TransactionContext,
        detections: list[DetectionResult],
        fetched_data: dict[str, Any] | None = None
    ) -> RuleEvaluationResult | None:
        """
        Evaluate rules and return first match (for rule chain mode)
        
        Args:
            context: Transaction context
            detections: List of detection results
            fetched_data: Pre-fetched external data
            
        Returns:
            First matched RuleEvaluationResult or None
        """
        fetched_data = fetched_data or {}
        
        for rule in self.rules:
            if not rule.enabled:
                continue
            
            result = await rule.evaluate(context, detections, fetched_data)
            if result.matched:
                return result
        
        return None
