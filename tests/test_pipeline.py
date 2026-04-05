"""
Unit tests for Alert Processing Pipeline (engine-based)
"""
import pytest

import nodes
nodes.init_registry()

from engine import ChainParser, ChainExecutor, ChainValidator
from models import SeverityEnum


class TestChainExecutorPipeline:
    """Test basic pipeline execution via ChainExecutor"""

    @pytest.fixture(autouse=True)
    def _ensure_registry(self):
        """确保真实节点已注册（引擎 conftest 可能已清除）"""
        from nodes import force_init_registry
        force_init_registry()

    @pytest.mark.asyncio
    async def test_simple_trigger_chain(self):
        """Test a chain with only a trigger node"""
        chain_config = {
            "nodes": [{"id": "t1", "type": "alert_trigger", "config": {}, "position": {"x": 0, "y": 0}}],
            "edges": [],
        }
        parsed = ChainParser.parse(chain_config)
        executor = ChainExecutor()
        ctx = await executor.execute(parsed, {"chain_id": 1, "tx_hash": "0xabc"})
        assert ctx.get_success() is True
        assert ctx.final_score == 0.0

    @pytest.mark.asyncio
    async def test_validator_on_chain(self):
        """Test ChainValidator returns validation results"""
        chain_config = {
            "nodes": [
                {"id": "t1", "type": "alert_trigger", "config": {}, "position": {"x": 0, "y": 0}},
                {"id": "d1", "type": "gas_price_detector", "config": {}, "position": {"x": 100, "y": 0}},
            ],
            "edges": [{"id": "e1", "source": "t1", "sourcePort": "output", "target": "d1", "targetPort": "input"}],
        }
        parsed = ChainParser.parse(chain_config)
        validator = ChainValidator()
        errors = validator.validate(parsed)
        # Only warnings (no action node), no errors
        error_errors = [e for e in errors if e.level == "error"]
        assert len(error_errors) == 0


class TestSeverityEnum:
    """Test SeverityEnum from models"""

    def test_severity_values(self):
        assert SeverityEnum.UNKNOWN.value == "UNKNOWN"
        assert SeverityEnum.LOW.value == "LOW"
        assert SeverityEnum.MEDIUM.value == "MEDIUM"
        assert SeverityEnum.HIGH.value == "HIGH"
        assert SeverityEnum.CRITICAL.value == "CRITICAL"
