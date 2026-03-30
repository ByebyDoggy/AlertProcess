"""
Unit tests for Rule Engine
"""
import pytest
import asyncio
from datetime import datetime

import sys
sys.path.insert(0, '/workspace')

from models import AlertInput, TransactionContext, DetectionResult, SeverityEnum
from rules.engine import (
    Rule,
    RuleConfig,
    RuleAction,
    RuleCondition,
    CompoundCondition,
    RuleEvaluationResult,
    ConditionEvaluator,
    ConditionOperator,
    RuleRegistry,
    RuleEngine,
)


class TestConditionEvaluator:
    """Test ConditionEvaluator"""
    
    def test_evaluate_equals_true(self):
        """Test equals operator - true case"""
        condition = RuleCondition(
            field="context.chain_id",
            operator=ConditionOperator.EQUALS,
            value=1
        )
        
        context = TransactionContext(chain_id=1, tx_hash="0x123")
        
        result, matched = ConditionEvaluator.evaluate_condition(
            condition.model_dump(), context, [], {}
        )
        
        assert result is True
    
    def test_evaluate_equals_false(self):
        """Test equals operator - false case"""
        condition = RuleCondition(
            field="context.chain_id",
            operator=ConditionOperator.EQUALS,
            value=2
        )
        
        context = TransactionContext(chain_id=1, tx_hash="0x123")
        
        result, matched = ConditionEvaluator.evaluate_condition(
            condition.model_dump(), context, [], {}
        )
        
        assert result is False
    
    def test_evaluate_not_equals(self):
        """Test not equals operator"""
        condition = RuleCondition(
            field="context.chain_id",
            operator=ConditionOperator.NOT_EQUALS,
            value=2
        )
        
        context = TransactionContext(chain_id=1, tx_hash="0x123")
        
        result, matched = ConditionEvaluator.evaluate_condition(
            condition.model_dump(), context, [], {}
        )
        
        assert result is True
    
    def test_evaluate_greater_than(self):
        """Test greater than operator"""
        condition = RuleCondition(
            field="context.value",
            operator=ConditionOperator.GREATER_THAN,
            value=1000
        )
        
        context = TransactionContext(chain_id=1, tx_hash="0x123", value=2000)
        
        result, matched = ConditionEvaluator.evaluate_condition(
            condition.model_dump(), context, [], {}
        )
        
        assert result is True
    
    def test_evaluate_less_than(self):
        """Test less than operator"""
        condition = RuleCondition(
            field="context.value",
            operator=ConditionOperator.LESS_THAN,
            value=100
        )
        
        context = TransactionContext(chain_id=1, tx_hash="0x123", value=50)
        
        result, matched = ConditionEvaluator.evaluate_condition(
            condition.model_dump(), context, [], {}
        )
        
        assert result is True
    
    def test_evaluate_contains(self):
        """Test contains operator with string"""
        condition = RuleCondition(
            field="context.from_address",
            operator=ConditionOperator.CONTAINS,
            value="0xabc"
        )
        
        context = TransactionContext(chain_id=1, tx_hash="0x123", from_address="0xabcdef123")
        
        result, matched = ConditionEvaluator.evaluate_condition(
            condition.model_dump(), context, [], {}
        )
        
        assert result is True
    
    def test_evaluate_regex(self):
        """Test regex operator"""
        condition = RuleCondition(
            field="context.from_address",
            operator=ConditionOperator.REGEX,
            value=r"^0x[0-9a-f]{40}$"
        )
        
        context = TransactionContext(chain_id=1, tx_hash="0x123", from_address="0xabcdef1234567890abcdef1234567890abcdef12")
        
        result, matched = ConditionEvaluator.evaluate_condition(
            condition.model_dump(), context, [], {}
        )
        
        assert result is True
    
    def test_evaluate_in_list(self):
        """Test in_list operator"""
        condition = RuleCondition(
            field="context.chain_id",
            operator=ConditionOperator.IN_LIST,
            value=[1, 56, 137]
        )
        
        context = TransactionContext(chain_id=56, tx_hash="0x123")
        
        result, matched = ConditionEvaluator.evaluate_condition(
            condition.model_dump(), context, [], {}
        )
        
        assert result is True
    
    def test_evaluate_is_null(self):
        """Test is_null operator"""
        condition = RuleCondition(
            field="context.nonce",
            operator=ConditionOperator.IS_NULL,
            value=None
        )
        
        context = TransactionContext(chain_id=1, tx_hash="0x123", nonce=None)
        
        result, matched = ConditionEvaluator.evaluate_condition(
            condition.model_dump(), context, [], {}
        )
        
        assert result is True
    
    def test_evaluate_is_not_null(self):
        """Test is_not_null operator"""
        condition = RuleCondition(
            field="context.from_address",
            operator=ConditionOperator.IS_NOT_NULL,
            value=None
        )
        
        context = TransactionContext(chain_id=1, tx_hash="0x123", from_address="0xabc")
        
        result, matched = ConditionEvaluator.evaluate_condition(
            condition.model_dump(), context, [], {}
        )
        
        assert result is True
    
    def test_evaluate_detection_result(self):
        """Test evaluating detection result"""
        condition = RuleCondition(
            field="detector.gas_price_detector",
            operator=ConditionOperator.EQUALS,
            value=True
        )
        
        context = TransactionContext(chain_id=1, tx_hash="0x123")
        detections = [
            DetectionResult(detector_name="gas_price_detector", detected=True)
        ]
        
        result, matched = ConditionEvaluator.evaluate_condition(
            condition.model_dump(), context, detections, {}
        )
        
        assert result is True
    
    def test_evaluate_fetched_data(self):
        """Test evaluating fetched external data"""
        condition = RuleCondition(
            field="fetched.arkm_label",
            operator=ConditionOperator.EQUALS,
            value="hacker"
        )
        
        context = TransactionContext(chain_id=1, tx_hash="0x123")
        fetched_data = {"arkm_label": "hacker"}
        
        result, matched = ConditionEvaluator.evaluate_condition(
            condition.model_dump(), context, [], fetched_data
        )
        
        assert result is True


class TestCompoundConditions:
    """Test compound AND/OR conditions"""
    
    def test_and_condition_all_true(self):
        """Test AND condition - all true"""
        condition = CompoundCondition(
            type="AND",
            conditions=[
                {"field": "context.chain_id", "operator": "equals", "value": 1},
                {"field": "context.from_address", "operator": "is_not_null", "value": None}
            ]
        )
        
        context = TransactionContext(chain_id=1, tx_hash="0x123", from_address="0xabc")
        
        result, matched = ConditionEvaluator.evaluate_condition(
            condition.model_dump(), context, [], {}
        )
        
        assert result is True
        assert len(matched) == 2
    
    def test_and_condition_one_false(self):
        """Test AND condition - one false"""
        condition = CompoundCondition(
            type="AND",
            conditions=[
                {"field": "context.chain_id", "operator": "equals", "value": 1},
                {"field": "context.chain_id", "operator": "equals", "value": 2}
            ]
        )
        
        context = TransactionContext(chain_id=1, tx_hash="0x123")
        
        result, matched = ConditionEvaluator.evaluate_condition(
            condition.model_dump(), context, [], {}
        )
        
        assert result is False
        assert len(matched) == 1  # Only first condition matched
    
    def test_or_condition_one_true(self):
        """Test OR condition - one true"""
        condition = CompoundCondition(
            type="OR",
            conditions=[
                {"field": "context.chain_id", "operator": "equals", "value": 1},
                {"field": "context.chain_id", "operator": "equals", "value": 2}
            ]
        )
        
        context = TransactionContext(chain_id=1, tx_hash="0x123")
        
        result, matched = ConditionEvaluator.evaluate_condition(
            condition.model_dump(), context, [], {}
        )
        
        assert result is True
    
    def test_nested_conditions(self):
        """Test nested AND/OR conditions"""
        condition = CompoundCondition(
            type="AND",
            conditions=[
                {"field": "context.chain_id", "operator": "equals", "value": 1},
                {
                    "type": "OR",
                    "conditions": [
                        {"field": "detector.gas_price_detector", "operator": "equals", "value": True},
                        {"field": "context.value", "operator": "greater_than", "value": 1000}
                    ]
                }
            ]
        )
        
        context = TransactionContext(chain_id=1, tx_hash="0x123", value=5000)
        detections = [DetectionResult(detector_name="gas_price_detector", detected=False)]
        
        result, matched = ConditionEvaluator.evaluate_condition(
            condition.model_dump(), context, detections, {}
        )
        
        assert result is True


class TestRule:
    """Test Rule class"""
    
    def test_rule_creation(self):
        """Test basic rule creation"""
        config = RuleConfig(
            name="test_rule",
            description="Test rule",
            condition={"field": "context.chain_id", "operator": "equals", "value": 1},
            action=RuleAction(set_severity="HIGH", set_score=100)
        )
        
        rule = Rule(config)
        
        assert rule.name == "test_rule"
        assert rule.enabled is True
        assert rule.priority == 0
    
    def test_rule_disabled(self):
        """Test disabled rule always returns not matched"""
        config = RuleConfig(
            name="disabled_rule",
            enabled=False,
            condition={"field": "context.chain_id", "operator": "equals", "value": 1}
        )
        
        rule = Rule(config)
        context = TransactionContext(chain_id=1, tx_hash="0x123")
        
        result = asyncio.run(rule.evaluate(context, [], {}))
        
        assert result.matched is False
    
    @pytest.mark.asyncio
    async def test_rule_matches(self):
        """Test rule matching and action execution"""
        config = RuleConfig(
            name="match_rule",
            condition={"field": "context.chain_id", "operator": "equals", "value": 1},
            action=RuleAction(set_severity="CRITICAL", set_score=100, add_tags=["test_tag"])
        )
        
        rule = Rule(config)
        context = TransactionContext(chain_id=1, tx_hash="0x123")
        
        result = await rule.evaluate(context, [], {})
        
        assert result.matched is True
        assert result.severity == "CRITICAL"
        assert result.score == 100
        assert "test_tag" in result.tags


class TestRuleEngine:
    """Test RuleEngine"""
    
    def test_engine_creation(self):
        """Test engine creation"""
        engine = RuleEngine()
        assert engine.rules == []
    
    def test_add_rule(self):
        """Test adding rules to engine"""
        engine = RuleEngine()
        config = RuleConfig(name="rule1", condition={"field": "context.chain_id", "operator": "equals", "value": 1})
        rule = Rule(config)
        
        engine.add_rule(rule)
        
        assert len(engine.rules) == 1
    
    def test_rules_sorted_by_priority(self):
        """Test rules are sorted by priority"""
        engine = RuleEngine()
        
        config1 = RuleConfig(name="low_priority", priority=1, condition={"field": "context.chain_id", "operator": "equals", "value": 1})
        config2 = RuleConfig(name="high_priority", priority=10, condition={"field": "context.chain_id", "operator": "equals", "value": 1})
        config3 = RuleConfig(name="medium_priority", priority=5, condition={"field": "context.chain_id", "operator": "equals", "value": 1})
        
        engine.add_rule(Rule(config1))
        engine.add_rule(Rule(config2))
        engine.add_rule(Rule(config3))
        
        # Should be sorted by priority descending
        assert engine.rules[0].name == "high_priority"
        assert engine.rules[1].name == "medium_priority"
        assert engine.rules[2].name == "low_priority"
    
    @pytest.mark.asyncio
    async def test_evaluate_all_rules(self):
        """Test evaluating all rules"""
        engine = RuleEngine()
        
        config1 = RuleConfig(name="rule1", condition={"field": "context.chain_id", "operator": "equals", "value": 1})
        config2 = RuleConfig(name="rule2", condition={"field": "context.chain_id", "operator": "equals", "value": 2})
        
        engine.add_rule(Rule(config1))
        engine.add_rule(Rule(config2))
        
        context = TransactionContext(chain_id=1, tx_hash="0x123")
        
        results = await engine.evaluate(context, [], {})
        
        assert len(results) == 2
        assert results[0].matched is True  # rule1 matches
        assert results[1].matched is False  # rule2 doesn't match
    
    @pytest.mark.asyncio
    async def test_evaluate_until_first_match(self):
        """Test first match evaluation mode"""
        engine = RuleEngine()
        
        config1 = RuleConfig(name="rule1", priority=1, condition={"field": "context.chain_id", "operator": "equals", "value": 1})
        config2 = RuleConfig(name="rule2", priority=2, condition={"field": "context.chain_id", "operator": "equals", "value": 1})
        
        engine.add_rule(Rule(config1))
        engine.add_rule(Rule(config2))
        
        context = TransactionContext(chain_id=1, tx_hash="0x123")
        
        result = await engine.evaluate_until_first_match(context, [])
        
        assert result is not None
        assert result.rule_name == "rule2"  # Higher priority rule returns first


class TestRuleRegistry:
    """Test RuleRegistry"""
    
    def test_register_and_get(self):
        """Test registering and retrieving rules"""
        RuleRegistry.clear()
        
        config = RuleConfig(name="registry_test", condition={"field": "context.chain_id", "operator": "equals", "value": 1})
        rule = Rule(config)
        
        RuleRegistry.register(rule)
        
        retrieved = RuleRegistry.get("registry_test")
        assert retrieved is not None
        assert retrieved.name == "registry_test"
    
    def test_unregister(self):
        """Test unregistering rules"""
        RuleRegistry.clear()
        
        config = RuleConfig(name="to_remove", condition={"field": "context.chain_id", "operator": "equals", "value": 1})
        rule = Rule(config)
        RuleRegistry.register(rule)
        
        RuleRegistry.unregister("to_remove")
        
        assert RuleRegistry.get("to_remove") is None
    
    def test_list_rules(self):
        """Test listing all rules"""
        RuleRegistry.clear()
        
        config1 = RuleConfig(name="rule1", condition={"field": "context.chain_id", "operator": "equals", "value": 1})
        config2 = RuleConfig(name="rule2", condition={"field": "context.chain_id", "operator": "equals", "value": 1})
        
        RuleRegistry.register(Rule(config1))
        RuleRegistry.register(Rule(config2))
        
        names = RuleRegistry.list_rules()
        
        assert "rule1" in names
        assert "rule2" in names


class TestRuleConfigFromYaml:
    """Test RuleConfig can be created from YAML-style dict"""
    
    def test_yaml_style_condition(self):
        """Test creating rule from YAML-style configuration"""
        yaml_config = {
            "name": "high_gas_price_critical",
            "description": "Alert for high gas price transactions",
            "enabled": True,
            "priority": 10,
            "condition": {
                "type": "AND",
                "conditions": [
                    {
                        "field": "detector.gas_price_detector",
                        "operator": "equals",
                        "value": True
                    },
                    {
                        "field": "fetched.gas_price_usd",
                        "operator": "greater_than",
                        "value": 100
                    }
                ]
            },
            "action": {
                "set_severity": "CRITICAL",
                "set_score": 100,
                "add_tags": ["high_gas", "suspicious"]
            }
        }
        
        config = RuleConfig(**yaml_config)
        rule = Rule(config)
        
        assert rule.name == "high_gas_price_critical"
        assert rule.config.priority == 10
        assert rule.enabled is True


def run_tests():
    """Run all tests"""
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    run_tests()
