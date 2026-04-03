"""tests/engine/test_validator.py — ChainValidator 测试"""

import pytest

from engine.parser import ChainParser
from engine.validator import ChainValidator


class TestStructureValidation:

    def test_valid_simple_chain(self):
        """trigger -> detector -> action 应通过校验"""
        config = {
            "nodes": [
                {"id": "t1", "type": "_test_trigger"},
                {"id": "d1", "type": "_test_detector"},
                {"id": "a1", "type": "_test_action"},
            ],
            "edges": [
                {"source": "t1", "sourcePort": "output", "target": "d1", "targetPort": "input"},
                {"source": "d1", "sourcePort": "output", "target": "a1", "targetPort": "input"},
            ],
        }
        chain = ChainParser.parse(config)
        errors = ChainValidator().validate(chain)
        assert len(errors) == 0

    def test_no_trigger(self):
        chain = ChainParser.parse({
            "nodes": [{"id": "d1", "type": "_test_detector"}],
            "edges": [],
        })
        errors = ChainValidator().validate(chain)
        assert any("trigger" in e.message.lower() for e in errors)

    def test_multiple_triggers(self):
        chain = ChainParser.parse({
            "nodes": [
                {"id": "t1", "type": "_test_trigger"},
                {"id": "t2", "type": "_test_trigger"},
            ],
            "edges": [],
        })
        errors = ChainValidator().validate(chain)
        assert any("一个" in e.message for e in errors)

    def test_isolated_node(self):
        chain = ChainParser.parse({
            "nodes": [
                {"id": "t1", "type": "_test_trigger"},
                {"id": "d1", "type": "_test_detector"},
                {"id": "d2", "type": "_test_detector"},  # 孤立
                {"id": "a1", "type": "_test_action"},
            ],
            "edges": [
                {"source": "t1", "sourcePort": "output", "target": "d1", "targetPort": "input"},
                {"source": "d1", "sourcePort": "output", "target": "a1", "targetPort": "input"},
            ],
        })
        errors = ChainValidator().validate(chain)
        assert any("不可达" in e.message for e in errors)

    def test_no_path_to_action_warning(self):
        chain = ChainParser.parse({
            "nodes": [
                {"id": "t1", "type": "_test_trigger"},
                {"id": "d1", "type": "_test_detector"},
                {"id": "d2", "type": "_test_detector"},  # 不通向 action
                {"id": "a1", "type": "_test_action"},
            ],
            "edges": [
                {"source": "t1", "sourcePort": "output", "target": "d1", "targetPort": "input"},
                {"source": "t1", "sourcePort": "output", "target": "d2", "targetPort": "input"},
                {"source": "d1", "sourcePort": "output", "target": "a1", "targetPort": "input"},
            ],
        })
        errors = ChainValidator().validate(chain)
        # d2 也没有 path to action (it goes to d2 but d2 doesn't connect to action)
        # Actually d2 IS reachable from trigger, but has no path to action
        assert any("无路径到达 action" in e.message for e in errors)

    def test_cycle_detection(self):
        chain = ChainParser.parse({
            "nodes": [
                {"id": "d1", "type": "_test_detector"},
                {"id": "d2", "type": "_test_detector"},
            ],
            "edges": [
                {"source": "d1", "sourcePort": "output", "target": "d2", "targetPort": "input"},
                {"source": "d2", "sourcePort": "output", "target": "d1", "targetPort": "input"},
            ],
        })
        errors = ChainValidator().validate(chain)
        assert any("环路" in e.message for e in errors)

    def test_duplicate_edges(self):
        chain = ChainParser.parse({
            "nodes": [
                {"id": "t1", "type": "_test_trigger"},
                {"id": "d1", "type": "_test_detector"},
            ],
            "edges": [
                {"source": "t1", "sourcePort": "output", "target": "d1", "targetPort": "input"},
                {"source": "t1", "sourcePort": "output", "target": "d1", "targetPort": "input"},
            ],
        })
        errors = ChainValidator().validate(chain)
        assert any("重复" in e.message for e in errors)


class TestPortValidation:

    def test_required_port_not_connected(self):
        chain = ChainParser.parse({
            "nodes": [
                {"id": "t1", "type": "_test_trigger"},
                {"id": "d1", "type": "_test_detector"},  # required input
            ],
            "edges": [],
        })
        errors = ChainValidator().validate(chain)
        assert any("必需端口" in e.message for e in errors)

    def test_nonexistent_source_port(self):
        chain = ChainParser.parse({
            "nodes": [
                {"id": "t1", "type": "_test_trigger"},
                {"id": "d1", "type": "_test_detector"},
            ],
            "edges": [
                {"source": "t1", "sourcePort": "nonexistent", "target": "d1", "targetPort": "input"},
            ],
        })
        errors = ChainValidator().validate(chain)
        assert any("输出端口" in e.message for e in errors)

    def test_nonexistent_target_port(self):
        chain = ChainParser.parse({
            "nodes": [
                {"id": "t1", "type": "_test_trigger"},
                {"id": "d1", "type": "_test_detector"},
            ],
            "edges": [
                {"source": "t1", "sourcePort": "output", "target": "d1", "targetPort": "nonexistent"},
            ],
        })
        errors = ChainValidator().validate(chain)
        assert any("输入端口" in e.message for e in errors)

    def test_nonexistent_source_node(self):
        chain = ChainParser.parse({
            "nodes": [{"id": "d1", "type": "_test_detector"}],
            "edges": [{"source": "ghost", "target": "d1"}],
        })
        errors = ChainValidator().validate(chain)
        assert any("不存在" in e.message for e in errors)

    def test_action_no_output_connection(self):
        chain = ChainParser.parse({
            "nodes": [
                {"id": "t1", "type": "_test_trigger"},
                {"id": "a1", "type": "_test_action"},
                {"id": "d1", "type": "_test_detector"},
            ],
            "edges": [
                {"source": "t1", "sourcePort": "output", "target": "a1", "targetPort": "input"},
                {"source": "a1", "sourcePort": "output", "target": "d1", "targetPort": "input"},
            ],
        })
        errors = ChainValidator().validate(chain)
        assert any("终端节点" in e.message for e in errors)


class TestDataTypeValidation:

    def test_trigger_to_logic_rejected(self):
        """Trigger -> Logic 应被拒绝（Logic 只接收布尔型输入）"""
        chain = ChainParser.parse({
            "nodes": [
                {"id": "t1", "type": "_test_trigger"},
                {"id": "l1", "type": "_test_logic"},
            ],
            "edges": [
                {"source": "t1", "sourcePort": "output", "target": "l1", "targetPort": "input_0"},
            ],
        })
        errors = ChainValidator().validate(chain)
        assert any("数据类型" in e.message for e in errors)

    def test_detector_to_logic_rejected(self):
        """Detector -> Logic 应被拒绝（需先经过 Comparator）"""
        chain = ChainParser.parse({
            "nodes": [
                {"id": "t1", "type": "_test_trigger"},
                {"id": "d1", "type": "_test_detector"},
                {"id": "l1", "type": "_test_logic"},
            ],
            "edges": [
                {"source": "t1", "sourcePort": "output", "target": "d1", "targetPort": "input"},
                {"source": "d1", "sourcePort": "output", "target": "l1", "targetPort": "input_0"},
            ],
        })
        errors = ChainValidator().validate(chain)
        assert any("数据类型" in e.message for e in errors)

    def test_comparator_to_logic_ok(self):
        """Comparator(true) -> Logic 应通过"""
        chain = ChainParser.parse({
            "nodes": [
                {"id": "t1", "type": "_test_trigger"},
                {"id": "d1", "type": "_test_detector"},
                {"id": "c1", "type": "_test_comparator"},
                {"id": "l1", "type": "_test_logic"},
                {"id": "a1", "type": "_test_action"},
            ],
            "edges": [
                {"source": "t1", "sourcePort": "output", "target": "d1", "targetPort": "input"},
                {"source": "d1", "sourcePort": "output", "target": "c1", "targetPort": "input_0"},
                {"source": "c1", "sourcePort": "true", "target": "l1", "targetPort": "input_0"},
                {"source": "l1", "sourcePort": "true", "target": "a1", "targetPort": "input"},
            ],
        })
        errors = ChainValidator().validate(chain)
        type_errors = [e for e in errors if "数据类型" in e.message]
        assert len(type_errors) == 0

    def test_trigger_to_detector_ok(self):
        chain = ChainParser.parse({
            "nodes": [
                {"id": "t1", "type": "_test_trigger"},
                {"id": "d1", "type": "_test_detector"},
            ],
            "edges": [{"source": "t1", "sourcePort": "output", "target": "d1", "targetPort": "input"}],
        })
        errors = ChainValidator().validate(chain)
        type_errors = [e for e in errors if "数据类型" in e.message]
        assert len(type_errors) == 0


class TestTopologyValidation:

    def test_unknown_node_type(self):
        chain = ChainParser.parse({
            "nodes": [
                {"id": "t1", "type": "_test_trigger"},
                {"id": "x1", "type": "nonexistent_type"},
            ],
            "edges": [],
        })
        errors = ChainValidator().validate(chain)
        assert any("未知节点类型" in e.message for e in errors)

    def test_no_action_warning(self):
        chain = ChainParser.parse({
            "nodes": [
                {"id": "t1", "type": "_test_trigger"},
                {"id": "d1", "type": "_test_detector"},
            ],
            "edges": [
                {"source": "t1", "sourcePort": "output", "target": "d1", "targetPort": "input"},
            ],
        })
        errors = ChainValidator().validate(chain)
        assert any("action" in e.message.lower() for e in errors)


class TestFullChainValidation:

    def test_valid_full_chain(self):
        """完整链: trigger -> detector -> comparator -> logic -> action"""
        from tests.engine.conftest import make_chain_with_comparator
        chain = ChainParser.parse(make_chain_with_comparator())
        errors = ChainValidator().validate(chain)
        # 应该没有 error 级别的错误（可能有 warning）
        error_errors = [e for e in errors if e.level == "error"]
        assert len(error_errors) == 0
