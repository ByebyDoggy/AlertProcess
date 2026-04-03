"""tests/engine/test_executor.py — ChainExecutor 异步执行测试"""

import pytest

from engine.executor import ChainExecutor
from engine.parser import ChainParser
from tests.engine.conftest import make_simple_chain, make_chain_with_comparator


class TestTopologicalLayers:

    def test_simple_chain_layers(self):
        """trigger -> detector -> action 应产生 3 层"""
        chain = ChainParser.parse(make_simple_chain())
        layers = ChainExecutor._topological_layers(chain)
        assert len(layers) == 3
        assert layers[0] == ["t1"]
        assert layers[1] == ["d1"]
        assert layers[2] == ["a1"]

    def test_parallel_detectors(self):
        """同层多个检测器应并发"""
        config = {
            "nodes": [
                {"id": "t1", "type": "_test_trigger"},
                {"id": "d1", "type": "_test_detector", "config": {"fixed_score": 60}},
                {"id": "d2", "type": "_test_detector", "config": {"fixed_score": 80}},
                {"id": "a1", "type": "_test_action"},
            ],
            "edges": [
                {"source": "t1", "sourcePort": "output", "target": "d1", "targetPort": "input"},
                {"source": "t1", "sourcePort": "output", "target": "d2", "targetPort": "input"},
                {"source": "d1", "sourcePort": "output", "target": "a1", "targetPort": "input"},
                {"source": "d2", "sourcePort": "output", "target": "a1", "targetPort": "input"},
            ],
        }
        chain = ChainParser.parse(config)
        layers = ChainExecutor._topological_layers(chain)
        assert len(layers) == 3
        assert set(layers[1]) == {"d1", "d2"}

    def test_cycle_returns_empty(self):
        """有环时应返回空列表"""
        config = {
            "nodes": [
                {"id": "d1", "type": "_test_detector"},
                {"id": "d2", "type": "_test_detector"},
            ],
            "edges": [
                {"source": "d1", "sourcePort": "output", "target": "d2", "targetPort": "input"},
                {"source": "d2", "sourcePort": "output", "target": "d1", "targetPort": "input"},
            ],
        }
        chain = ChainParser.parse(config)
        layers = ChainExecutor._topological_layers(chain)
        assert layers == []


class TestExecute:

    @pytest.mark.asyncio
    async def test_simple_chain_execution(self):
        """trigger -> detector -> action 应全部执行"""
        chain = ChainParser.parse(make_simple_chain())
        executor = ChainExecutor()
        ctx = await executor.execute(chain, {"tx_hash": "0x123"})

        assert ctx.get_success()
        assert len(ctx.node_outputs) == 3  # trigger + detector + action
        assert ctx.get_output("t1") is not None
        assert ctx.get_output("d1") is not None
        assert ctx.get_output("a1") is not None
        assert ctx.get_output("d1").score == 70.0
        assert ctx.get_output("d1").passed is True

    @pytest.mark.asyncio
    async def test_execution_logs(self):
        """执行后应记录日志"""
        chain = ChainParser.parse(make_simple_chain())
        executor = ChainExecutor()
        ctx = await executor.execute(chain, {})

        assert len(ctx.logs) == 3
        assert all(log.duration_ms >= 0 for log in ctx.logs)
        assert all(log.error is None for log in ctx.logs)

    @pytest.mark.asyncio
    async def test_labels_collected(self):
        """检测器标签应被聚合"""
        chain = ChainParser.parse(make_simple_chain())
        executor = ChainExecutor()
        ctx = await executor.execute(chain, {})

        assert "test_label" in ctx.collected_labels

    @pytest.mark.asyncio
    async def test_severity_aggregated(self):
        """严重级别应被聚合"""
        chain = ChainParser.parse(make_simple_chain())
        executor = ChainExecutor()
        ctx = await executor.execute(chain, {})

        # detector score=70 -> severity=HIGH (>=60)
        assert ctx.final_severity == "HIGH"
        assert ctx.final_score == 70.0

    @pytest.mark.asyncio
    async def test_action_recorded(self):
        """Action 执行应被记录"""
        chain = ChainParser.parse(make_simple_chain())
        executor = ChainExecutor()
        ctx = await executor.execute(chain, {})

        assert len(ctx.actions_executed) == 1
        assert ctx.actions_executed[0]["node_id"] == "a1"
        assert ctx.actions_executed[0]["result"]["status"] == "executed"

    @pytest.mark.asyncio
    async def test_full_chain_with_comparator(self):
        """trigger -> detector -> comparator -> logic -> action"""
        chain = ChainParser.parse(make_chain_with_comparator())
        executor = ChainExecutor()
        ctx = await executor.execute(chain, {})

        assert ctx.get_success()
        assert len(ctx.node_outputs) == 5
        assert ctx.get_output("c1").passed is True
        assert ctx.get_output("l1").passed is True

    @pytest.mark.asyncio
    async def test_conditional_branch_false(self):
        """comparator 不通过时 false 分支应执行"""
        config = {
            "nodes": [
                {"id": "t1", "type": "_test_trigger"},
                {"id": "d1", "type": "_test_detector", "config": {"fixed_score": 20}},
                {"id": "c1", "type": "_test_comparator", "config": {"always_pass": False}},
                {"id": "a1_true", "type": "_test_action"},
                {"id": "a1_false", "type": "_test_action"},
            ],
            "edges": [
                {"source": "t1", "sourcePort": "output", "target": "d1", "targetPort": "input"},
                {"source": "d1", "sourcePort": "output", "target": "c1", "targetPort": "input_0"},
                {"source": "c1", "sourcePort": "true", "target": "a1_true", "targetPort": "input"},
                {"source": "c1", "sourcePort": "false", "target": "a1_false", "targetPort": "input"},
            ],
        }
        chain = ChainParser.parse(config)
        executor = ChainExecutor()
        ctx = await executor.execute(chain, {})

        # comparator always_pass=False, 所以 c1.passed=False
        # true 分支不应执行, false 分支应执行
        assert ctx.get_output("a1_true") is None
        assert ctx.get_output("a1_false") is not None

    @pytest.mark.asyncio
    async def test_conditional_branch_true(self):
        """comparator 通过时 true 分支应执行"""
        config = {
            "nodes": [
                {"id": "t1", "type": "_test_trigger"},
                {"id": "d1", "type": "_test_detector", "config": {"fixed_score": 80}},
                {"id": "c1", "type": "_test_comparator", "config": {"always_pass": True}},
                {"id": "a1_true", "type": "_test_action"},
                {"id": "a1_false", "type": "_test_action"},
            ],
            "edges": [
                {"source": "t1", "sourcePort": "output", "target": "d1", "targetPort": "input"},
                {"source": "d1", "sourcePort": "output", "target": "c1", "targetPort": "input_0"},
                {"source": "c1", "sourcePort": "true", "target": "a1_true", "targetPort": "input"},
                {"source": "c1", "sourcePort": "false", "target": "a1_false", "targetPort": "input"},
            ],
        }
        chain = ChainParser.parse(config)
        executor = ChainExecutor()
        ctx = await executor.execute(chain, {})

        assert ctx.get_output("a1_true") is not None
        assert ctx.get_output("a1_false") is None

    @pytest.mark.asyncio
    async def test_validation_errors_stops_execution(self):
        """校验错误时应停止执行"""
        config = {
            "nodes": [
                {"id": "d1", "type": "_test_detector"},  # no trigger
            ],
            "edges": [],
        }
        chain = ChainParser.parse(config)
        executor = ChainExecutor()
        ctx = await executor.execute(chain, {})

        assert not ctx.get_success()
        assert len(ctx.errors) > 0

    @pytest.mark.asyncio
    async def test_cycle_chain_returns_error(self):
        """有环的链应返回错误"""
        config = {
            "nodes": [
                {"id": "d1", "type": "_test_detector"},
                {"id": "d2", "type": "_test_detector"},
            ],
            "edges": [
                {"source": "d1", "sourcePort": "output", "target": "d2", "targetPort": "input"},
                {"source": "d2", "sourcePort": "output", "target": "d1", "targetPort": "input"},
            ],
        }
        chain = ChainParser.parse(config)
        executor = ChainExecutor()
        ctx = await executor.execute(chain, {})

        assert not ctx.get_success()

    @pytest.mark.asyncio
    async def test_parallel_detectors_execution(self):
        """同层检测器应并发执行"""
        config = {
            "nodes": [
                {"id": "t1", "type": "_test_trigger"},
                {"id": "d1", "type": "_test_detector", "config": {"fixed_score": 30}},
                {"id": "d2", "type": "_test_detector", "config": {"fixed_score": 90}},
                {"id": "s1", "type": "_test_scorer"},
                {"id": "a1", "type": "_test_action"},
            ],
            "edges": [
                {"source": "t1", "sourcePort": "output", "target": "d1", "targetPort": "input"},
                {"source": "t1", "sourcePort": "output", "target": "d2", "targetPort": "input"},
                {"source": "d1", "sourcePort": "output", "target": "s1", "targetPort": "input_0"},
                {"source": "d2", "sourcePort": "output", "target": "s1", "targetPort": "input_0"},
                {"source": "s1", "sourcePort": "output", "target": "a1", "targetPort": "input"},
            ],
        }
        chain = ChainParser.parse(config)
        executor = ChainExecutor()
        ctx = await executor.execute(chain, {})

        assert ctx.get_success()
        assert len(ctx.node_outputs) == 5  # 所有节点都执行
        assert ctx.get_output("d1").score == 30.0
        assert ctx.get_output("d2").score == 90.0
