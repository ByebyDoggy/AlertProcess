"""tests/engine/conftest.py — 公共 fixture"""

import pytest

from nodes.base import BaseNode, NodeCategory, NodeOutput, NodeRegistry, PortDef


# ---------------------------------------------------------------------------
# 测试用节点
# ---------------------------------------------------------------------------

class _TestTrigger(BaseNode):
    name = "_test_trigger"
    label = "Test Trigger"
    category = NodeCategory.INPUT
    icon = ""
    color = ""

    @classmethod
    def get_inputs(cls):
        return []

    @classmethod
    def get_outputs(cls):
        return [PortDef(key="output", label="输出", data_type="context")]

    async def execute(self, context, inputs):
        return NodeOutput(node_id=self.node_id, node_type="input", passed=True, context=dict(context))


class _TestDetector(BaseNode):
    name = "_test_detector"
    label = "Test Detector"
    category = NodeCategory.DETECTION
    icon = ""
    color = ""

    @classmethod
    def get_inputs(cls):
        return [PortDef(key="input", label="输入", required=True)]

    @classmethod
    def get_outputs(cls):
        return [PortDef(key="output", label="输出", data_type="detection_output")]

    async def execute(self, context, inputs):
        score = self.config.get("fixed_score", 70)
        from nodes.base import score_to_severity
        return NodeOutput(
            node_id=self.node_id, node_type="detection",
            score=score, passed=score >= 50,
            context={"detection": {"test": True}},
            labels=["test_label"],
            severity=score_to_severity(score),
        )


class _TestComparator(BaseNode):
    name = "_test_comparator"
    label = "Test Comparator"
    category = NodeCategory.COMPARISON
    icon = ""
    color = ""

    @classmethod
    def get_inputs(cls):
        return [PortDef(key="input_0", label="输入 1", data_type="detection_output", required=True)]

    @classmethod
    def get_outputs(cls):
        return [
            PortDef(key="true", label="满足", data_type="comparison_output"),
            PortDef(key="false", label="不满足", data_type="comparison_output"),
        ]

    async def execute(self, context, inputs):
        result = self.config.get("always_pass", True)
        return NodeOutput(
            node_id=self.node_id, node_type="comparison",
            score=100.0 if result else 0.0, passed=result,
        )


class _TestScorer(BaseNode):
    name = "_test_scorer"
    label = "Test Scorer"
    category = NodeCategory.SCORING
    icon = ""
    color = ""

    @classmethod
    def get_inputs(cls):
        return [PortDef(key="input_0", label="输入 1", data_type="detection_output",
                         required=True, multi=True)]

    @classmethod
    def get_outputs(cls):
        return [PortDef(key="output", label="聚合评分", data_type="score_output")]

    async def execute(self, context, inputs):
        return NodeOutput(
            node_id=self.node_id, node_type="scoring", score=85.0, passed=True,
        )


class _TestLogic(BaseNode):
    name = "_test_logic"
    label = "Test Logic"
    category = NodeCategory.LOGIC
    icon = ""
    color = ""

    @classmethod
    def get_inputs(cls):
        return [
            PortDef(key="input_0", label="输入 1", data_type="comparison_output", required=True),
        ]

    @classmethod
    def get_outputs(cls):
        return [
            PortDef(key="true", label="满足", data_type="logic_output"),
            PortDef(key="false", label="不满足", data_type="logic_output"),
        ]

    async def execute(self, context, inputs):
        result = self.config.get("always_pass", True)
        return NodeOutput(
            node_id=self.node_id, node_type="logic",
            score=100.0 if result else 0.0, passed=result,
        )


class _TestAction(BaseNode):
    name = "_test_action"
    label = "Test Action"
    category = NodeCategory.ACTION
    icon = ""
    color = ""

    @classmethod
    def get_inputs(cls):
        return [PortDef(key="input", label="输入", required=True)]

    @classmethod
    def get_outputs(cls):
        return []

    async def execute(self, context, inputs):
        return NodeOutput(
            node_id=self.node_id, node_type="action", score=0, passed=True,
            context={"action_result": {"status": "executed"}},
        )


@pytest.fixture(autouse=True)
def register_test_nodes():
    """每个测试前后注册/清理测试节点"""
    NodeRegistry.register(_TestTrigger)
    NodeRegistry.register(_TestDetector)
    NodeRegistry.register(_TestComparator)
    NodeRegistry.register(_TestScorer)
    NodeRegistry.register(_TestLogic)
    NodeRegistry.register(_TestAction)
    yield
    NodeRegistry.clear()


def make_simple_chain():
    """
    创建一个简单的测试链: trigger -> detector -> action
    """
    return {
        "nodes": [
            {"id": "t1", "type": "_test_trigger", "label": "Trigger"},
            {"id": "d1", "type": "_test_detector", "label": "Detector", "config": {"fixed_score": 70}},
            {"id": "a1", "type": "_test_action", "label": "Action"},
        ],
        "edges": [
            {"id": "e1", "source": "t1", "sourcePort": "output", "target": "d1", "targetPort": "input"},
            {"id": "e2", "source": "d1", "sourcePort": "output", "target": "a1", "targetPort": "input"},
        ],
    }


def make_chain_with_comparator():
    """
    trigger -> detector -> comparator -> logic -> action
    """
    return {
        "nodes": [
            {"id": "t1", "type": "_test_trigger", "label": "Trigger"},
            {"id": "d1", "type": "_test_detector", "label": "Detector", "config": {"fixed_score": 70}},
            {"id": "c1", "type": "_test_comparator", "label": "Comparator", "config": {"always_pass": True}},
            {"id": "l1", "type": "_test_logic", "label": "Logic", "config": {"always_pass": True}},
            {"id": "a1", "type": "_test_action", "label": "Action"},
        ],
        "edges": [
            {"id": "e1", "source": "t1", "sourcePort": "output", "target": "d1", "targetPort": "input"},
            {"id": "e2", "source": "d1", "sourcePort": "output", "target": "c1", "targetPort": "input_0"},
            {"id": "e3", "source": "c1", "sourcePort": "true", "target": "l1", "targetPort": "input_0"},
            {"id": "e4", "source": "l1", "sourcePort": "true", "target": "a1", "targetPort": "input"},
        ],
    }
