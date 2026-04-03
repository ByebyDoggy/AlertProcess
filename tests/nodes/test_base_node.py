"""tests/nodes/test_base_node.py — BaseNode 抽象、NodeOutput 模型、score_to_severity"""

import pytest

from nodes.base import (
    ALLOWED_TYPE_MAPPING,
    CATEGORY_ALLOWED_INPUTS,
    BaseNode,
    NodeCategory,
    NodeOutput,
    PortDef,
    PortType,
    score_to_severity,
)


# ---------------------------------------------------------------------------
# NodeOutput 模型测试
# ---------------------------------------------------------------------------

class TestNodeOutput:

    def test_default_values(self):
        out = NodeOutput(node_id="n1", node_type="detector")
        assert out.node_id == "n1"
        assert out.node_type == "detector"
        assert out.score == 0.0
        assert out.passed is True
        assert out.context == {}
        assert out.labels == []
        assert out.severity == "UNKNOWN"
        assert out.timestamp is not None

    def test_score_boundaries(self):
        out_max = NodeOutput(node_id="n1", node_type="detector", score=100.0)
        assert out_max.score == 100.0

        out_min = NodeOutput(node_id="n1", node_type="detector", score=0.0)
        assert out_min.score == 0.0

    def test_score_out_of_range_rejected(self):
        with pytest.raises(Exception):
            NodeOutput(node_id="n1", node_type="detector", score=150.0)
        with pytest.raises(Exception):
            NodeOutput(node_id="n1", node_type="detector", score=-10.0)

    def test_context_and_labels(self):
        out = NodeOutput(
            node_id="n1",
            node_type="detector",
            score=80.0,
            passed=True,
            context={"key": "value"},
            labels=["high_gas"],
            severity="HIGH",
        )
        assert out.context == {"key": "value"}
        assert out.labels == ["high_gas"]
        assert out.severity == "HIGH"

    def test_model_dump_roundtrip(self):
        out = NodeOutput(node_id="n1", node_type="detector", score=75.5)
        data = out.model_dump()
        out2 = NodeOutput(**data)
        assert out2.node_id == "n1"
        assert out2.score == 75.5

    def test_json_roundtrip(self):
        out = NodeOutput(node_id="n1", node_type="detector", score=60, labels=["tag1"])
        json_str = out.model_dump_json()
        out2 = NodeOutput.model_validate_json(json_str)
        assert out2.score == 60.0
        assert out2.labels == ["tag1"]


# ---------------------------------------------------------------------------
# PortDef 模型测试
# ---------------------------------------------------------------------------

class TestPortDef:

    def test_default_port(self):
        p = PortDef(key="input", label="输入")
        assert p.data_type == "any"
        assert p.required is False
        assert p.multi is False

    def test_required_multi_port(self):
        p = PortDef(key="input_0", label="输入1", data_type="detection_output", required=True, multi=True)
        assert p.required is True
        assert p.multi is True

    def test_model_dump(self):
        p = PortDef(key="output", label="输出", data_type="detection_output")
        data = p.model_dump()
        assert data["key"] == "output"
        assert data["data_type"] == "detection_output"


# ---------------------------------------------------------------------------
# PortType 枚举测试
# ---------------------------------------------------------------------------

class TestPortType:

    def test_values(self):
        assert PortType.INPUT.value == "input"
        assert PortType.OUTPUT.value == "output"
        assert PortType.TRUE.value == "true"
        assert PortType.FALSE.value == "false"


# ---------------------------------------------------------------------------
# NodeCategory 枚举测试
# ---------------------------------------------------------------------------

class TestNodeCategory:

    def test_values(self):
        assert NodeCategory.INPUT.value == "input"
        assert NodeCategory.DETECTION.value == "detection"
        assert NodeCategory.COMPARISON.value == "comparison"
        assert NodeCategory.SCORING.value == "scoring"
        assert NodeCategory.LOGIC.value == "logic"
        assert NodeCategory.ACTION.value == "action"


# ---------------------------------------------------------------------------
# score_to_severity 测试
# ---------------------------------------------------------------------------

class TestScoreToSeverity:

    @pytest.mark.parametrize("score,expected", [
        (0, "UNKNOWN"),
        (10, "UNKNOWN"),
        (19, "UNKNOWN"),
        (20, "LOW"),
        (39, "LOW"),
        (40, "MEDIUM"),
        (59, "MEDIUM"),
        (60, "HIGH"),
        (79, "HIGH"),
        (80, "CRITICAL"),
        (100, "CRITICAL"),
    ])
    def test_thresholds(self, score, expected):
        assert score_to_severity(score) == expected


# ---------------------------------------------------------------------------
# 数据类型兼容性矩阵测试
# ---------------------------------------------------------------------------

class TestTypeMapping:

    def test_context_to_detector(self):
        assert "context" in CATEGORY_ALLOWED_INPUTS[NodeCategory.DETECTION]

    def test_logic_restricted_inputs(self):
        allowed = CATEGORY_ALLOWED_INPUTS[NodeCategory.LOGIC]
        assert "comparison_output" in allowed
        assert "logic_output" in allowed
        assert "context" not in allowed
        assert "detection_output" not in allowed

    def test_allowed_type_mapping_keys(self):
        expected_types = {"context", "detection_output", "comparison_output", "score_output", "logic_output"}
        assert set(ALLOWED_TYPE_MAPPING.keys()) == expected_types

    def test_comparator_allowed_inputs(self):
        allowed = CATEGORY_ALLOWED_INPUTS[NodeCategory.COMPARISON]
        assert "detection_output" in allowed
        assert "score_output" in allowed
        assert "logic_output" not in allowed


# ---------------------------------------------------------------------------
# BaseNode 抽象基类测试
# ---------------------------------------------------------------------------

class TestBaseNode:

    def test_cannot_instantiate_abstract(self):
        """BaseNode 是抽象类，不能直接实例化"""
        with pytest.raises(TypeError):
            BaseNode()  # type: ignore[abstract]

    def test_concrete_subclass(self):
        """具体子类可以实例化"""

        class DummyNode(BaseNode):
            name = "dummy"
            label = "Dummy"
            category = NodeCategory.ACTION
            icon = ""
            color = ""

            @classmethod
            def get_inputs(cls):
                return []

            @classmethod
            def get_outputs(cls):
                return []

            async def execute(self, context, inputs):
                return NodeOutput(node_id=self.node_id, node_type="action")

        node = DummyNode(node_id="d1", config={"key": "val"})
        assert node.node_id == "d1"
        assert node.config == {"key": "val"}

    def test_default_config(self):
        class DummyNode(BaseNode):
            name = "dummy"
            label = "Dummy"
            category = NodeCategory.ACTION
            icon = ""
            color = ""

            @classmethod
            def get_inputs(cls):
                return []

            @classmethod
            def get_outputs(cls):
                return []

            @classmethod
            def get_default_config(cls):
                return {"threshold": 50}

            async def execute(self, context, inputs):
                return NodeOutput(node_id=self.node_id, node_type="action")

        node = DummyNode(node_id="d1")
        assert node.config == {"threshold": 50}

    def test_validate_config_default(self):
        class DummyNode(BaseNode):
            name = "dummy"
            label = "Dummy"
            category = NodeCategory.ACTION
            icon = ""
            color = ""

            @classmethod
            def get_inputs(cls):
                return []

            @classmethod
            def get_outputs(cls):
                return []

            async def execute(self, context, inputs):
                return NodeOutput(node_id=self.node_id, node_type="action")

        node = DummyNode(node_id="d1")
        assert node.validate_config({}) == []

    def test_first_input(self):
        class DummyNode(BaseNode):
            name = "dummy"
            label = "Dummy"
            category = NodeCategory.ACTION
            icon = ""
            color = ""

            @classmethod
            def get_inputs(cls):
                return []

            @classmethod
            def get_outputs(cls):
                return []

            async def execute(self, context, inputs):
                return NodeOutput(node_id=self.node_id, node_type="action")

        node = DummyNode(node_id="d1")

        out_a = NodeOutput(node_id="a", node_type="detector", score=60)
        out_b = NodeOutput(node_id="b", node_type="detector", score=80)

        assert node._first_input({"input_0": [out_a], "input_1": [out_b]}) is out_a
        assert node._first_input({}) is None

    def test_merge_context(self):
        class DummyNode(BaseNode):
            name = "dummy"
            label = "Dummy"
            category = NodeCategory.ACTION
            icon = ""
            color = ""

            @classmethod
            def get_inputs(cls):
                return []

            @classmethod
            def get_outputs(cls):
                return []

            async def execute(self, context, inputs):
                return NodeOutput(node_id=self.node_id, node_type="action")

        node = DummyNode(node_id="d1")
        upstream = NodeOutput(node_id="u", node_type="detector", context={"gas": 100})
        merged = node._merge_context({"tx_hash": "0x123"}, upstream)
        assert merged == {"tx_hash": "0x123", "gas": 100}

    def test_merge_context_no_upstream(self):
        class DummyNode(BaseNode):
            name = "dummy"
            label = "Dummy"
            category = NodeCategory.ACTION
            icon = ""
            color = ""

            @classmethod
            def get_inputs(cls):
                return []

            @classmethod
            def get_outputs(cls):
                return []

            async def execute(self, context, inputs):
                return NodeOutput(node_id=self.node_id, node_type="action")

        node = DummyNode(node_id="d1")
        merged = node._merge_context({"tx_hash": "0x123"}, None)
        assert merged == {"tx_hash": "0x123"}

    def test_config_schema_default(self):
        class DummyNode(BaseNode):
            name = "dummy"
            label = "Dummy"
            category = NodeCategory.ACTION
            icon = ""
            color = ""

            @classmethod
            def get_inputs(cls):
                return []

            @classmethod
            def get_outputs(cls):
                return []

            async def execute(self, context, inputs):
                return NodeOutput(node_id=self.node_id, node_type="action")

        assert DummyNode.get_config_schema() == {}
