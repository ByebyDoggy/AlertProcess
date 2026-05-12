"""
节点基础模块

定义所有节点的抽象基类、统一输出模型、端口定义和节点注册表。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any, ClassVar

from pydantic import BaseModel, Field, ValidationError as PydanticValidationError

from detectors.trace.token_price_cache import TokenPriceCache


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
        description: 端口用途说明（前端 tooltip 显示）
    """
    key: str
    label: str
    data_type: str = "any"
    required: bool = False
    multi: bool = False
    description: str = ""


# ---------------------------------------------------------------------------
# 节点分类
# ---------------------------------------------------------------------------

class NodeCategory(Enum):
    """节点分类 — 对应前端节点面板的分组"""
    INPUT = "input"
    PROVIDER = "provider"
    DETECTION = "detection"
    COMPARISON = "comparison"
    SCORING = "scoring"
    LOGIC = "logic"
    ACTION = "action"
    MEMORY = "memory"
    SCRIPTING = "scripting"
    STORAGE = "storage"
    TEMPORAL = "temporal"


# ---------------------------------------------------------------------------
# 统一输出模型
# ---------------------------------------------------------------------------

class NodeOutput(BaseModel):
    """
    所有节点的统一运行时输出模型（引擎内部使用）。

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
    logs: list[str] = Field(default_factory=list, description="评分原因日志")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# 节点 Pydantic 输出/输入 Mixin（类外定义，供子类继承扩展）
# ---------------------------------------------------------------------------

class NodeOutputMixin(BaseModel):
    """
    所有节点的默认输出数据结构 Mixin。

    子类（各类别基类 OutputMixin）继承此模型并扩展字段。
    与 NodeOutput（运行时模型）分离，NodeOutputMixin 描述 process() 返回值。
    """
    score: float = Field(ge=0.0, le=100.0, default=0.0)
    passed: bool = True
    severity: str = "UNKNOWN"
    labels: list[str] = Field(default_factory=list)
    detection: dict[str, Any] = Field(default_factory=dict)


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
    "memory_output":      {"memory_output", "context", "any"},
}

# 各节点分类允许接收的输入 data_type
CATEGORY_ALLOWED_INPUTS: dict[NodeCategory, set[str]] = {
    NodeCategory.INPUT:      set(),  # Trigger 无输入
    NodeCategory.PROVIDER:   {"context", "any"},
    NodeCategory.DETECTION:  {"context", "any"},
    NodeCategory.COMPARISON: {"detection_output", "score_output"},
    NodeCategory.SCORING:    {"detection_output", "score_output"},
    NodeCategory.LOGIC:      {"comparison_output", "logic_output", "context", "any"},
    NodeCategory.ACTION:     {"any"},
    NodeCategory.MEMORY:     {"detection_output", "score_output", "context", "any"},
    NodeCategory.SCRIPTING:  {"detection_output", "score_output", "context", "any"},
    NodeCategory.STORAGE:    set(),  # 存储节点无输入
    NodeCategory.TEMPORAL:   {"context", "detection_output", "score_output", "logic_output", "comparison_output", "any"},
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

    上下文声明:
      通过 @require("provider_name") 装饰器声明额外上下文需求。
      未标注的节点默认只使用 eth_logs 上下文（零 API 调用）。

    Pydantic 模型声明:
      - ConfigModel:  节点配置参数模型 → 自动派生 get_config_schema / get_default_config / validate_config
      - OutputModel:  节点输出数据结构 → 自动派生 get_output_schema → 前端展示 + 边级 Transformer 提示
      - InputModel:   节点期望输入结构 → 自动派生 get_input_schema → 前端映射 UI
    """

    name: ClassVar[str]
    label: ClassVar[str]
    description: ClassVar[str] = ""
    category: ClassVar[NodeCategory]
    icon: ClassVar[str] = ""
    color: ClassVar[str] = "#6366f1"

    # @require 装饰器设置的上下文需求
    __required_providers__: ClassVar[tuple[str, ...]] = ()

    # ── Pydantic 配置模型 (子类可选覆盖) ──
    # 子类定义 ConfigModel 后，get_config_schema / get_default_config / validate_config
    # 自动从 Pydantic model 派生，无需手写 dict schema
    ConfigModel: type[BaseModel] | None = None

    # ── Pydantic 输出/输入模型 (子类可选覆盖) ──
    # 方式 A（多端口节点）：定义 InputModels / OutputModels 列表，每个元素对应一个端口
    InputModels: list[type[BaseModel]] | None = None
    OutputModels: list[type[BaseModel]] | None = None
    # 方式 B（单端口节点，兼容旧写法）：定义单一模型
    InputModel: type[BaseModel] | None = None
    OutputModel: type[BaseModel] = NodeOutputMixin

    # 实例属性（每个节点实例独立）
    node_id: str = ""
    config: dict[str, Any] = {}
    _token_price_cache: TokenPriceCache | None = None

    def __init__(self, node_id: str = "", config: dict[str, Any] | None = None) -> None:
        self.node_id = node_id
        self.config = config or self.get_default_config()

    @property
    def token_price_instance(self) -> TokenPriceCache:
        """
        获取全局 TokenPriceCache 单例，供任意节点查询代币价格。

        用法:
          price = self.token_price_instance.get_price(chain_id=1, token_address="0x...")
          meta = self.token_price_instance.get(chain_id=1, token_address="0x...")

        注意: 原生代币价格（ETH/BNB/MATIC 等）已由 TokenPriceCache 内置
              硬编码 fallback 价格，无需在节点配置中单独设置。
        """
        if self._token_price_cache is None:
            from detectors.trace.token_price_cache import get_token_price_cache
            self._token_price_cache = get_token_price_cache()
        return self._token_price_cache

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
        """
        返回 JSON Schema 格式的配置定义（供前端动态渲染）。

        优先级:
          1. 如果子类定义了 ConfigModel (Pydantic)，自动从 model 生成 JSON Schema
          2. 否则返回空 dict（子类可重写此方法返回手写 schema）
        """
        if cls.ConfigModel is not None:
            return cls._pydantic_config_schema()
        return {}

    @classmethod
    def get_default_config(cls) -> dict[str, Any]:
        """
        返回默认配置。

        优先级:
          1. ConfigModel 存在 → 从 Pydantic model 的 default 值构建
          2. 否则返回空 dict（子类可重写）
        """
        if cls.ConfigModel is not None:
            try:
                instance = cls.ConfigModel()
                # 使用 model_dump 排除未设置的字段，只保留有默认值的字段
                return instance.model_dump(exclude_unset=False)
            except Exception:
                return {}
        return {}

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        """
        校验配置，返回错误列表（空列表表示合法）。

        优先级:
          1. ConfigModel 存在 → 用 Pydantic 校验，返回结构化错误
          2. 否则调用子类重写的 validate_config 方法（默认返回空列表）
        """
        if self.ConfigModel is not None:
            try:
                self.ConfigModel(**config)
                return []
            except PydanticValidationError as e:
                return [f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}"
                        for err in e.errors()]
        return []

    @classmethod
    def _pydantic_config_schema(cls) -> dict[str, Any]:
        """从 ConfigModel 生成前端兼容的 JSON Schema。"""
        raw = cls.ConfigModel.model_json_schema()
        # 转换为前端期望的简化格式: { type, properties: { field: { type, default, ... } } }
        props = raw.get("properties", {})
        result_props = {}
        for key, val in props.items():
            entry = {"type": val.get("type", "string")}
            if "default" in val:
                entry["default"] = val["default"]
            if "description" in val and val["description"]:
                entry["description"] = val["description"]
            if "minimum" in val:
                entry["minimum"] = val["minimum"]
            if "maximum" in val:
                entry["maximum"] = val["maximum"]
            if "enum" in val:
                entry["enum"] = val["enum"]
            # 透传 x-editor 扩展（Pydantic json_schema_extra）
            if "x-editor" in val:
                entry["x-editor"] = val["x-editor"]
            result_props[key] = entry

        return {
            "type": "object",
            "properties": result_props,
        }

    @classmethod
    def _resolve_models(cls) -> tuple[list[type[BaseModel]], list[type[BaseModel]]]:
        """
        解析实际的输入/输出模型列表。

        优先使用 InputModels/OutputModels（list），否则从单值 InputModel/OutputModel 包装为 list。

        Returns:
            (input_models_list, output_models_list) — 长度与 get_inputs()/get_outputs() 一一对应
        """
        # 解析输入模型
        if cls.InputModels is not None:
            in_models = cls.InputModels
        elif cls.InputModel is not None:
            in_models = [cls.InputModel]
        else:
            in_models = []

        # 解析输出模型
        if cls.OutputModels is not None:
            out_models = cls.OutputModels
        else:
            out_models = [cls.OutputModel]

        return in_models, out_models

    @classmethod
    def get_input_schemas(cls) -> list[dict[str, Any]]:
        """
        返回每个输入端口对应的 JSON Schema 列表。

        长度与 get_inputs() 一致，index 对齐。
        """
        models, _ = cls._resolve_models()
        return [m.model_json_schema() for m in models]

    @classmethod
    def get_output_schemas(cls) -> list[dict[str, Any]]:
        """
        返回每个输出端口对应的 JSON Schema 列表。

        长度与 get_outputs() 一致，index 对齐。
        """
        _, models = cls._resolve_models()
        return [m.model_json_schema() for m in models]

    @classmethod
    def get_output_schema(cls) -> dict[str, Any]:
        """
        从 OutputModel 生成 JSON Schema（供前端展示 + 边级 Transformer 提示）。

        当 OutputModels 存在时返回第一个输出模型的 schema；否则从单值 OutputModel 生成。
        """
        schemas = cls.get_output_schemas()
        return schemas[0] if schemas else {}

    @classmethod
    def get_input_schema(cls) -> dict[str, Any]:
        """
        从 InputModel 生成 JSON Schema（供前端映射 UI）。

        当 InputModels 存在时返回第一个输入模型的 schema；否则从单值 InputModel 生成。
        InputModel 不存在时返回空 dict。
        """
        schemas = cls.get_input_schemas()
        return schemas[0] if schemas else {}

    @classmethod
    def get_required_providers(cls) -> tuple[str, ...]:
        """
        返回此节点所需的上下文 Provider 名称列表。

        通过 @require 装饰器设置，未标注的节点返回空元组。
        """
        return getattr(cls, "__required_providers__", ())

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
    支持自动发现机制，无需手动维护模块列表。
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
    def auto_discover(cls, base_package: str = "nodes") -> int:
        """
        自动扫描并注册节点

        Args:
            base_package: 基础包路径，默认为 "nodes"

        Returns:
            注册的节点数量

        工作原理:
            1. 递归扫描 base_package 下的所有 Python 模块
            2. 导入模块，触发 @register 装饰器自动注册
            3. 跳过以 _ 开头的模块（私有模块）
            4. 跳过 base.py（基类模块）
        """
        import importlib
        import pkgutil
        import logging

        logger = logging.getLogger(__name__)
        initial_count = len(cls._nodes)

        try:
            # 导入基础包
            base_module = importlib.import_module(base_package)
            base_path = base_module.__path__

            # 递归扫描所有子模块
            for importer, modname, ispkg in pkgutil.walk_packages(
                path=base_path,
                prefix=f"{base_package}.",
                onerror=lambda x: None
            ):
                # 跳过私有模块和基类模块
                if modname.split(".")[-1].startswith("_") or modname.endswith(".base"):
                    continue

                try:
                    importlib.import_module(modname)
                    logger.debug(f"[NodeRegistry] Loaded module: {modname}")
                except Exception as e:
                    logger.warning(f"[NodeRegistry] Failed to load module {modname}: {e}")

            registered_count = len(cls._nodes) - initial_count
            logger.info(f"[NodeRegistry] Auto-discovered {registered_count} nodes from {base_package}")
            return registered_count

        except Exception as e:
            logger.error(f"[NodeRegistry] Auto-discovery failed: {e}")
            return 0

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
        - input_schemas: 每个输入端口对应的 JSON Schema 列表（index 与 inputs 对齐）
        - output_schemas: 每个输出端口对应的 JSON Schema 列表（index 与 outputs 对齐）
        - input_schema / output_schema: 旧字段（返回第一个端口的 schema），保留兼容
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
                "input_schemas": node_class.get_input_schemas(),
                "output_schemas": node_class.get_output_schemas(),
                "input_schema": node_class.get_input_schema(),
                "output_schema": node_class.get_output_schema(),
            })
        return result

    @classmethod
    def get_docs_for_frontend(cls) -> list[dict[str, Any]]:
        """
        生成节点文档专用数据（比 get_schema_for_frontend 更丰富）。

        额外包含:
        - category_label: 分类中文标签
        - base_class: 节点基类名称
        - required_providers: @require 声明的上下文依赖
        - provides: Provider 节点注入的字段列表
        - module: 节点类所在模块路径
        - config_schema_raw: 原始 Pydantic JSON Schema（含 $defs、嵌套等完整信息）
        """
        CATEGORY_LABELS = {
            NodeCategory.INPUT: "输入",
            NodeCategory.PROVIDER: "上下文查询",
            NodeCategory.DETECTION: "安全检测",
            NodeCategory.COMPARISON: "比较",
            NodeCategory.SCORING: "评分",
            NodeCategory.LOGIC: "逻辑",
            NodeCategory.ACTION: "动作",
            NodeCategory.MEMORY: "记忆",
            NodeCategory.SCRIPTING: "脚本",
            NodeCategory.STORAGE: "存储",
            NodeCategory.TEMPORAL: "时序",
        }

        result = []
        for name, node_class in sorted(cls._nodes.items()):
            provides = list(getattr(node_class, "provides", []))
            result.append({
                "name": name,
                "label": node_class.label,
                "description": node_class.description,
                "category": node_class.category.value,
                "category_label": CATEGORY_LABELS.get(node_class.category, node_class.category.value),
                "base_class": node_class.__bases__[0].__name__ if node_class.__bases__ else "BaseNode",
                "module": node_class.__module__,
                "icon": node_class.icon,
                "color": node_class.color,
                "inputs": [p.model_dump() for p in node_class.get_inputs()],
                "outputs": [p.model_dump() for p in node_class.get_outputs()],
                "config_schema": node_class.get_config_schema(),
                "config_schema_raw": node_class.ConfigModel.model_json_schema() if node_class.ConfigModel else {},
                "default_config": node_class.get_default_config(),
                "input_schemas": node_class.get_input_schemas(),
                "output_schemas": node_class.get_output_schemas(),
                "required_providers": list(node_class.get_required_providers()),
                "provides": provides,
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
