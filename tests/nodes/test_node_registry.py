"""tests/nodes/test_node_registry.py — NodeRegistry 注册/查询/分类"""

import pytest

from nodes.base import BaseNode, NodeCategory, NodeOutput, NodeRegistry, PortDef


# ---------------------------------------------------------------------------
# 辅助: 创建具体子类用于测试
# ---------------------------------------------------------------------------

class FakeTrigger(BaseNode):
    name = "fake_trigger"
    label = "Fake Trigger"
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
        return NodeOutput(node_id=self.node_id, node_type="input")


class FakeDetector(BaseNode):
    name = "fake_detector"
    label = "Fake Detector"
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
        return NodeOutput(node_id=self.node_id, node_type="detection", score=50)


class FakeComparator(BaseNode):
    name = "fake_comparator"
    label = "Fake Comparator"
    category = NodeCategory.COMPARISON
    icon = ""
    color = ""

    @classmethod
    def get_inputs(cls):
        return [PortDef(key="input_0", label="输入 1", required=True)]

    @classmethod
    def get_outputs(cls):
        return [
            PortDef(key="true", label="满足", data_type="comparison_output"),
            PortDef(key="false", label="不满足", data_type="comparison_output"),
        ]

    async def execute(self, context, inputs):
        return NodeOutput(node_id=self.node_id, node_type="comparison", score=100)


class FakeScorer(BaseNode):
    name = "fake_scorer"
    label = "Fake Scorer"
    category = NodeCategory.SCORING
    icon = ""
    color = ""

    @classmethod
    def get_inputs(cls):
        return [PortDef(key="input_0", label="输入 1", required=True)]

    @classmethod
    def get_outputs(cls):
        return [PortDef(key="output", label="聚合评分", data_type="score_output")]

    async def execute(self, context, inputs):
        return NodeOutput(node_id=self.node_id, node_type="scoring", score=75)


class FakeLogic(BaseNode):
    name = "fake_logic"
    label = "Fake Logic"
    category = NodeCategory.LOGIC
    icon = ""
    color = ""

    @classmethod
    def get_inputs(cls):
        return [PortDef(key="input_0", label="输入 1", required=True)]

    @classmethod
    def get_outputs(cls):
        return [
            PortDef(key="true", label="满足", data_type="logic_output"),
            PortDef(key="false", label="不满足", data_type="logic_output"),
        ]

    async def execute(self, context, inputs):
        return NodeOutput(node_id=self.node_id, node_type="logic", score=100)


class FakeAction(BaseNode):
    name = "fake_action"
    label = "Fake Action"
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
        return NodeOutput(node_id=self.node_id, node_type="action")


# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_registry():
    """每个测试前后清空注册表"""
    NodeRegistry.clear()
    yield
    NodeRegistry.clear()


class TestNodeRegistry:

    def test_register_and_get(self):
        NodeRegistry.register(FakeDetector)
        assert NodeRegistry.get("fake_detector") is FakeDetector

    def test_register_decorator(self):
        """@register 返回原类"""

        @NodeRegistry.register
        class MyNode(BaseNode):
            name = "my_node"
            label = "My"
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

        assert NodeRegistry.get("my_node") is MyNode

    def test_get_unknown_returns_none(self):
        assert NodeRegistry.get("nonexistent") is None

    def test_get_by_category(self):
        NodeRegistry.register(FakeDetector)
        NodeRegistry.register(FakeTrigger)
        NodeRegistry.register(FakeAction)

        detectors = NodeRegistry.get_by_category(NodeCategory.DETECTION)
        assert len(detectors) == 1
        assert detectors[0] is FakeDetector

        triggers = NodeRegistry.get_by_category(NodeCategory.INPUT)
        assert len(triggers) == 1
        assert triggers[0] is FakeTrigger

    def test_all(self):
        NodeRegistry.register(FakeDetector)
        NodeRegistry.register(FakeTrigger)

        all_nodes = NodeRegistry.all()
        assert len(all_nodes) == 2
        assert "fake_detector" in all_nodes
        assert "fake_trigger" in all_nodes

    def test_clear(self):
        NodeRegistry.register(FakeDetector)
        NodeRegistry.clear()
        assert NodeRegistry.all() == {}

    def test_duplicate_register_same_class_ok(self):
        """同一次类重复注册不报错"""
        NodeRegistry.register(FakeDetector)
        NodeRegistry.register(FakeDetector)  # 应该不报错
        assert NodeRegistry.get("fake_detector") is FakeDetector

    def test_duplicate_register_different_class_raises(self):
        """不同类注册同名应报错"""
        NodeRegistry.register(FakeDetector)

        class OtherDetector(BaseNode):
            name = "fake_detector"  # 同名
            label = "Other"
            category = NodeCategory.DETECTION
            icon = ""
            color = ""

            @classmethod
            def get_inputs(cls):
                return []

            @classmethod
            def get_outputs(cls):
                return []

            async def execute(self, context, inputs):
                return NodeOutput(node_id=self.node_id, node_type="detection")

        with pytest.raises(ValueError, match="already registered"):
            NodeRegistry.register(OtherDetector)

    def test_create(self):
        NodeRegistry.register(FakeDetector)
        node = NodeRegistry.create("fake_detector", node_id="d1", config={"threshold": 80})
        assert isinstance(node, FakeDetector)
        assert node.node_id == "d1"
        assert node.config == {"threshold": 80}

    def test_create_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown node type"):
            NodeRegistry.create("nonexistent")

    def test_get_schema_for_frontend(self):
        NodeRegistry.register(FakeDetector)
        NodeRegistry.register(FakeAction)

        schemas = NodeRegistry.get_schema_for_frontend()
        assert len(schemas) == 2

        # 按 name 排序后应为 fake_action, fake_detector
        assert schemas[0]["name"] == "fake_action"
        assert schemas[0]["category"] == "action"
        assert len(schemas[0]["inputs"]) == 1
        assert len(schemas[0]["outputs"]) == 0

        assert schemas[1]["name"] == "fake_detector"
        assert schemas[1]["category"] == "detection"
        assert len(schemas[1]["inputs"]) == 1
        assert len(schemas[1]["outputs"]) == 1

    def test_get_schema_for_frontend_empty(self):
        assert NodeRegistry.get_schema_for_frontend() == []

    def test_register_all_categories(self):
        """注册所有 6 种分类的节点"""
        NodeRegistry.register(FakeTrigger)
        NodeRegistry.register(FakeDetector)
        NodeRegistry.register(FakeComparator)
        NodeRegistry.register(FakeScorer)
        NodeRegistry.register(FakeLogic)
        NodeRegistry.register(FakeAction)

        assert len(NodeRegistry.all()) == 6
        assert len(NodeRegistry.get_by_category(NodeCategory.INPUT)) == 1
        assert len(NodeRegistry.get_by_category(NodeCategory.DETECTION)) == 1
        assert len(NodeRegistry.get_by_category(NodeCategory.COMPARISON)) == 1
        assert len(NodeRegistry.get_by_category(NodeCategory.SCORING)) == 1
        assert len(NodeRegistry.get_by_category(NodeCategory.LOGIC)) == 1
        assert len(NodeRegistry.get_by_category(NodeCategory.ACTION)) == 1
