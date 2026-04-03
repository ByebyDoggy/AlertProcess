"""
节点基础模块

定义所有节点的抽象基类、统一输出模型、端口定义和节点注册表。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any, ClassVar

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 端口定义
# ---------------------------------------------------------------------------

class PortType(Enum):
    """端口类型"""
    INPUT = "input"
    OUTPUT = "output"
    TRUE = "true"
    FALSE = "false"


class PortDef(BaseModel):
    """
    端口定义 — 描述节点的一个输入或输出端口。

    Attributes:
        key:         端口唯一标识，如 "input_0", "output", "true", "false"
        label:       前端显示名
        data_type:   数据类型约束，校验器会检查上下游兼容性
        required:    是否必须连接
        multi:       是否允许连接多条边（多输入场景）
    """
    key: str
    label: str
    data_type: str = "any"
    required: bool = False
    multi: bool = False


# ---------------------------------------------------------------------------
# 节点分类
# ---------------------------------------------------------------------------

class NodeCategory(Enum):
    """节点分类 — 对应前端节点面板的分组"""
    INPUT = "input"
    DETECTION = "detection"
    COMPARISON = "comparison"
    SCORING = "scoring"
    LOGIC = "logic"
    ACTION = "action"


# ---------------------------------------------------------------------------
# 统一输出模型
# ---------------------------------------------------------------------------

class NodeOutput(BaseModel):
    """
    所有节点的统一输出模型。

    - Detector:    score 0-100（风险评分）
    - Comparator:  score 100（满足）/ 0（不满足）
    - Scorer:      score 0-100（聚合评分）
    - Logic:       score 100（真）/ 0（假）
    - Trigger:     score 0（始终传递）
    - Action:      继承上游 score（终端节点）
    """
    node_id: str
    node_type: str
    score: float = Field(ge=0.0, le=100.0, default=0.0)
    passed: bool = True
    context: dict[str, Any] = Field(default_factory=dict)
    labels: list[str] = Field(default_factory=list)
    severity: str = "UNKNOWN"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# 数据类型兼容性矩阵 — 校验引擎使用
# ---------------------------------------------------------------------------

# 源输出 data_type -> 可连接的目标输入 data_type 集合
ALLOWED_TYPE_MAPPING: dict[str, set[str]] = {
    "context":            {"context", "any"},
    "detection_output":   {"detection_output", "score_output", "any"},
    "comparison_output":  {"comparison_output", "any"},
    "score_output":       {"detection_output", "score_output", "any"},
    "logic_output":       {"logic_output", "comparison_output", "any"},
}

# 各节点分类允许接收的输入 data_type
CATEGORY_ALLOWED_INPUTS: dict[NodeCategory, set[str]] = {
    NodeCategory.INPUT:      set(),  # Trigger 无输入
    NodeCategory.DETECTION:  {"context", "any"},
    NodeCategory.COMPARISON: {"detection_output", "score_output"},
    NodeCategory.SCORING:    {"detection_output", "score_output"},
    NodeCategory.LOGIC:      {"comparison_output", "logic_output"},
    NodeCategory.ACTION:     {"any"},
}


# ---------------------------------------------------------------------------
# 严重级别映射
# ---------------------------------------------------------------------------

SEVERITY_SCORE_MAP: list[tuple[float, str]] = [
    (80.0, "CRITICAL"),
    (60.0, "HIGH"),
    (40.0, "MEDIUM"),
    (20.0, "LOW"),
]


def score_to_severity(score: float) -> str:
    """将 0-100 分映射为严重级别"""
    for threshold, severity in SEVERITY_SCORE_MAP:
        if score >= threshold:
            return severity
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# BaseNode 抽象基类
# ---------------------------------------------------------------------------

class BaseNode(ABC):
    """
    所有节点的抽象基类（全异步）。

    子类必须定义:
      - name: str              节点类型名（如 "gas_price_detector"）
      - label: str             显示名
      - description: str       描述
      - category: NodeCategory 节点分类
      - icon: str              图标
      - color: str             主题色
      - get_inputs()           输入端口列表
      - get_outputs()          输出端口列表
      - execute()              异步执行逻辑
    """

    name: ClassVar[str]
    label: ClassVar[str]
    description: ClassVar[str] = ""
    category: ClassVar[NodeCategory]
    icon: ClassVar[str] = ""
    color: ClassVar[str] = "#6366f1"

    # 实例属性（每个节点实例独立）
    node_id: str = ""
    config: dict[str, Any] = {}

    def __init__(self, node_id: str = "", config: dict[str, Any] | None = None) -> None:
        self.node_id = node_id
        self.config = config or self.get_default_config()

    @classmethod
    @abstractmethod
    def get_inputs(cls) -> list[PortDef]:
        """定义输入端口列表"""
        ...

    @classmethod
    @abstractmethod
    def get_outputs(cls) -> list[PortDef]:
        """定义输出端口列表"""
        ...

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        """返回 JSON Schema 格式的配置定义（供前端动态渲染）"""
        return {}

    @classmethod
    def get_default_config(cls) -> dict[str, Any]:
        """返回默认配置"""
        return {}

    @abstractmethod
    async def execute(
        self,
        context: dict[str, Any],
        inputs: dict[str, list[NodeOutput]],
    ) -> NodeOutput:
        """
        异步执行节点逻辑。

        Args:
            context: 全局执行上下文（含原始告警数据）
            inputs:  上游节点输出 { port_key: [NodeOutput, ...] }
        """
        ...

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        """校验配置，返回错误列表（空列表表示合法）"""
        return []

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _first_input(self, inputs: dict[str, list[NodeOutput]]) -> NodeOutput | None:
        """获取第一个可用的上游输入"""
        for port_key in sorted(inputs.keys()):
            if inputs[port_key]:
                return inputs[port_key][0]
        return None

    def _merge_context(
        self, context: dict[str, Any], upstream: NodeOutput | None
    ) -> dict[str, Any]:
        """合并全局上下文和上游输出上下文"""
        if upstream is None:
            return dict(context)
        return {**context, **upstream.context}


# ---------------------------------------------------------------------------
# NodeRegistry — 节点注册表
# ---------------------------------------------------------------------------

class NodeRegistry:
    """
    全局节点注册表，按 category 分组管理。

    使用 @register 装饰器注册节点，启动时自动导入各模块即可。
    """

    _nodes: dict[str, type[BaseNode]] = {}

    @classmethod
    def register(cls, node_class: type[BaseNode]) -> type[BaseNode]:
        """注册一个节点类"""
        name = node_class.name
        if name in cls._nodes:
            existing = cls._nodes[name]
            if existing is not node_class:
                # 允许重新注册同一类（热重载），但不允许不同类覆盖
                raise ValueError(
                    f"Node type '{name}' already registered by {existing.__name__}, "
                    f"cannot re-register with {node_class.__name__}"
                )
        cls._nodes[name] = node_class
        return node_class

    @classmethod
    def get(cls, name: str) -> type[BaseNode] | None:
        """按名称获取节点类"""
        return cls._nodes.get(name)

    @classmethod
    def get_by_category(cls, category: NodeCategory) -> list[type[BaseNode]]:
        """按分类获取所有节点类"""
        return [c for c in cls._nodes.values() if c.category == category]

    @classmethod
    def all(cls) -> dict[str, type[BaseNode]]:
        """获取所有已注册节点"""
        return dict(cls._nodes)

    @classmethod
    def clear(cls) -> None:
        """清空注册表（主要用于测试）"""
        cls._nodes.clear()

    @classmethod
    def get_schema_for_frontend(cls) -> list[dict[str, Any]]:
        """
        生成前端所需的节点类型列表。

        每个节点类型包含:
        - name, label, description, category, icon, color
        - inputs: 端口定义列表
        - outputs: 端口定义列表
        - config_schema: JSON Schema
        - default_config: 默认配置
        """
        result = []
        for name, node_class in sorted(cls._nodes.items()):
            result.append({
                "name": name,
                "label": node_class.label,
                "description": node_class.description,
                "category": node_class.category.value,
                "icon": node_class.icon,
                "color": node_class.color,
                "inputs": [p.model_dump() for p in node_class.get_inputs()],
                "outputs": [p.model_dump() for p in node_class.get_outputs()],
                "config_schema": node_class.get_config_schema(),
                "default_config": node_class.get_default_config(),
            })
        return result

    @classmethod
    def create(
        cls, node_type: str, node_id: str = "", config: dict[str, Any] | None = None
    ) -> BaseNode:
        """实例化一个节点"""
        node_class = cls.get(node_type)
        if node_class is None:
            raise ValueError(f"Unknown node type: '{node_type}'")
        return node_class(node_id=node_id, config=config)
