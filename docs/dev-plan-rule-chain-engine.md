# 规则链检测引擎 - 后端架构重构开发计划

> 状态：已审核，待开发
> 作者：AI Assistant
> 日期：2026-04-03

---

## 一、背景与目标

### 1.1 现状分析

当前系统已具备：
- 8 个检测器（gas/flash_loan/token_approval/token_anomaly/address_graph/address_age/arkm_label/address_type）
- 规则链引擎（ChainParser + ChainExecutor，BFS 执行 DAG）
- 规则条件引擎（ConditionEvaluator，13 种操作符）
- 评分引擎（加权求和 / 最大值 / 规则匹配）
- 通知系统（Webhook / Log）
- 前端 n8n 风格拖拽编辑器

### 1.2 核心问题

| 问题 | 说明 |
|------|------|
| 检测器输出不统一 | 有的返回 boolean detected，有的没有明确的分数量化 |
| 节点类型混杂 | chain_engine 中 trigger/detector/condition/filter/action/scorer/notifier 共 7 种，职责边界模糊 |
| 模块耦合 | 评分、过滤、条件判断散落在不同模块，未形成统一的节点抽象 |
| 无配置校验引擎 | 前端提交的规则链仅做简单校验（单入口/边引用/无环），缺少输入输出端口连接校验 |
| 通知器未纳入规则链 | 当前通知走独立通道，不能在规则链中灵活编排 |
| 无异步支持 | 当前同步执行，Action（Webhook/Telegram）涉及网络 IO 时阻塞 |

### 1.3 目标

构建一个**清晰的、可扩展的、全异步的规则链检测引擎**：

1. **统一节点抽象** — 所有节点继承 `BaseNode`，定义清晰的输入/输出端口契约
2. **六类节点** — Trigger（输入）、Detector（检测器）、Comparator（条件比较器）、Scorer（评分器）、Logic（逻辑表达式）、Action（动作）
3. **多输入支持** — Logic / Scorer / Comparator 节点支持多个输入端口
4. **评分制输出** — Detector 输出 0-100 分；Comparator 输出布尔判定（score 100/0）；Scorer 聚合评分；Logic 输出逻辑结果
5. **全异步执行** — 整个链路 async/await，Action 中的 IO 操作不阻塞其他节点
6. **数据流约束** — 仅 Detector、Comparator、Scorer 和 Logic 的输出可作为 Logic 节点的输入
7. **模块化开发** — 每种节点类型独立文件夹，通过注册表自动发现
8. **配置校验** — 完整的规则链校验引擎，覆盖端口连接、类型约束、拓扑排序
9. **完全重写** — 不兼容旧规则链配置，直接使用新架构
10. **单元测试先行** — 每个模块独立可测

---

## 二、架构设计

### 2.1 节点类型定义

```
┌─────────────┐
│   Trigger   │  输入节点，接收告警数据，输出 TransactionContext
│   (输入)     │
└──────┬──────┘
       │ context
       ▼
┌─────────────┐
│  Detector   │  检测器，接收 context，输出 score(0-100) + context
│  (检测器)    │
└──────┬──────┘
       │ detection_output (score + context)
       ├─── ▼
       │  ┌──────────────┐
       │  │ Comparator   │  条件比较器，接收 score，输出布尔判定 (score=100/0)
       │  │ (条件比较器)   │  支持 >, <, >=, <=, ==, !=, between
       │  └──────┬───────┘
       │         │ comparison_output (boolean)
       ├─── ▼    │
       │  ┌──────────────┐
       │  │   Scorer     │  评分器，接收多个 score，聚合输出单一 score
       │  │  (评分器)     │  支持 min / max / avg / weighted_sum
       │  └──────┬───────┘
       │         │ score_output (aggregated score)
       ▼         ▼
┌─────────────┐
│    Logic     │  逻辑表达式，接收多个布尔型输入，输出逻辑结果
│ (逻辑表达式)  │  支持 AND / OR，可嵌套
└──────┬──────┘
       │ logic_output (boolean)
       ▼
┌─────────────┐
│   Action     │  执行动作，接收任意上游输出，执行副作用（全异步）
│  (动作)      │  notify_webhook / notify_telegram / update_db / set_tag ...
└─────────────┘
```

#### 各节点职责说明

| 节点类型 | 输入 | 输出 | 职责 |
|---------|------|------|------|
| **Trigger** | 外部告警数据 | `context`（完整交易数据） | 接收并解析输入，启动链路 |
| **Detector** | `context`（单输入） | `score: 0-100` + enriched context | 执行检测逻辑，量化风险 |
| **Comparator** | `score`（多输入） | `score: 100` 或 `0`（布尔） | 比较操作符，判断是否满足条件 |
| **Scorer** | `score`（多输入） | `score: 0-100`（聚合值） | 聚合多个检测/评分结果 |
| **Logic** | `boolean`（多输入） | `score: 100` 或 `0`（布尔） | AND/OR 逻辑组合 |
| **Action** | `any`（单输入） | 无（终端节点） | 执行副作用，异步 IO |

#### 数据流约束规则

```
Trigger ──→ Detector     (✓)
Trigger ──→ Comparator   (✗)  Comparator 需要 score 输入
Trigger ──→ Scorer       (✗)  Scorer 需要 score 输入
Trigger ──→ Logic        (✗)  Logic 只能接收布尔型输出
Trigger ──→ Action       (✓)

Detector ──→ Detector    (✓)  级联检测，后续检测器可引用前序 context
Detector ──→ Comparator  (✓)  对检测分数做条件判断
Detector ──→ Scorer      (✓)  对检测分数做聚合
Detector ──→ Logic       (✗)  Logic 只接收布尔型，应先经过 Comparator
Detector ──→ Action      (✓)

Comparator─→ Comparator  (✓)  对比较结果再次比较（如嵌套条件）
Comparator─→ Scorer      (✗)  Scorer 接收 score，Comparator 输出的是布尔
Comparator─→ Logic       (✓)  核心路径：比较结果 → 逻辑组合
Comparator─→ Action      (✓)

Scorer ───→ Detector    (✗)  检测器接收 context，不接收 score
Scorer ───→ Comparator  (✓)  对聚合分数做条件判断
Scorer ───→ Scorer      (✓)  多级聚合
Scorer ───→ Logic       (✗)  Logic 只接收布尔型，应先经过 Comparator
Scorer ───→ Action      (✓)

Logic ────→ Logic       (✓)  嵌套逻辑
Logic ────→ Comparator  (✗)  比较器接收 score，Logic 输出布尔
Logic ────→ Scorer      (✗)  Scorer 接收 score，Logic 输出布尔
Logic ────→ Detector    (✗)
Logic ────→ Action      (✓)

Action ────→ 任何节点    (✗)  Action 是终端节点，无输出
```

**简化规则**：
- **Trigger** → Detector, Action
- **Detector** → Detector, Comparator, Scorer, Action
- **Comparator** → Comparator, Logic, Action
- **Scorer** → Comparator, Scorer, Action
- **Logic** → Logic, Action
- **Action** → 无输出（终端节点）

### 2.2 统一输出模型

```python
class NodeOutput(BaseModel):
    """所有节点的统一输出"""
    node_id: str                        # 来源节点 ID
    node_type: str                      # trigger / detector / comparator / scorer / logic / action
    score: float                        # 0-100 评分（布尔型节点为 100 或 0）
    passed: bool                        # score >= 阈值（默认 50）即为通过
    context: dict[str, Any]             # 上下文数据（下游节点可引用）
    labels: list[str] = []              # 附加标签
    severity: str = "UNKNOWN"           # 严重级别
    timestamp: datetime = Field(default_factory=datetime.utcnow)
```

#### 输出语义约定

| 节点类型 | score 含义 | passed 含义 |
|---------|-----------|------------|
| **Trigger** | 0 | True（始终传递） |
| **Detector** | 0-100 风险评分 | score >= 配置阈值 |
| **Comparator** | 100（满足）/ 0（不满足） | 比较条件是否成立 |
| **Scorer** | 0-100 聚合评分 | score >= 配置阈值 |
| **Logic** | 100（真）/ 0（假） | 逻辑运算结果 |
| **Action** | 继承上游 score | 继承上游 passed |

#### 各节点输出的 context 字段约定

| 节点类型 | context 内容 |
|---------|-------------|
| **Trigger** | `{ chain_id, tx_hash, from_address, to_address, value, gas_price, input_data, block_number, ... }` |
| **Detector** | `{ detector_name, alert_type, raw_result, details: {...} }` + 继承上游 context |
| **Comparator** | `{ comparator_type: "gt"/"lt"/"between"/..., left_value, right_value, operator, result }` |
| **Scorer** | `{ scorer_type: "min"/"max"/"avg"/"weighted", input_scores: [...], weights: [...] }` |
| **Logic** | `{ logic_type: "and"/"or", conditions_result: [...], matched_count, total_count }` |
| **Action** | `{ action_type, action_result, target, ... }` + 继承上游 context |

### 2.3 目录结构

```
backend/
├── nodes/                          # 节点模块（核心重构）
│   ├── __init__.py                 # 统一导出 + NodeRegistry
│   ├── base.py                     # BaseNode 抽象基类 + NodeOutput + PortDef + NodeCategory
│   │
│   ├── triggers/                   # 输入节点模块
│   │   ├── __init__.py
│   │   └── alert_trigger.py        # AlertTrigger - 接收告警输入
│   │
│   ├── detectors/                  # 检测器节点模块
│   │   ├── __init__.py
│   │   ├── base.py                 # BaseDetector(BaseNode)
│   │   ├── gas_price.py            # GasPriceDetector
│   │   ├── flash_loan.py           # FlashLoanDetector
│   │   ├── token_approval.py       # TokenApprovalDetector
│   │   ├── token_anomaly.py        # TokenAnomalyDetector
│   │   ├── address_graph.py        # AddressGraphDetector
│   │   ├── address_age.py          # AddressAgeDetector
│   │   ├── arkm_label.py           # ARKMLabelDetector
│   │   └── address_type.py         # AddressTypeDetector
│   │
│   ├── comparators/                # 条件比较器节点模块
│   │   ├── __init__.py
│   │   ├── base.py                 # BaseComparator(BaseNode)
│   │   ├── threshold.py            # ThresholdComparator - 阈值比较 (> / < / >= / <= / ==)
│   │   ├── range.py                # RangeComparator - 区间比较 (between)
│   │   └── regex.py                # RegexComparator - 正则匹配
│   │
│   ├── scorers/                    # 评分器节点模块
│   │   ├── __init__.py
│   │   ├── base.py                 # BaseScorer(BaseNode)
│   │   ├── min_max.py              # MinMaxScorer - 取最小/最大值
│   │   ├── average.py              # AverageScorer - 求平均值
│   │   └── weighted.py             # WeightedScorer - 加权求和
│   │
│   ├── logic/                      # 逻辑表达式节点模块
│   │   ├── __init__.py
│   │   ├── base.py                 # BaseLogicNode(BaseNode)
│   │   ├── and_gate.py             # AndGate - 全部满足
│   │   └── or_gate.py              # OrGate - 任一满足
│   │
│   └── actions/                    # 动作节点模块
│       ├── __init__.py
│       ├── base.py                 # BaseAction(BaseNode)
│       ├── set_severity.py         # SetSeverityAction
│       ├── add_tag.py              # AddTagAction
│       ├── notify_webhook.py       # NotifyWebhookAction
│       ├── notify_telegram.py      # NotifyTelegramAction
│       └── update_database.py      # UpdateDatabaseAction
│
├── engine/                         # 规则链引擎
│   ├── __init__.py
│   ├── parser.py                   # ChainParser - 配置解析 + DAG 构建
│   ├── validator.py                # ChainValidator - 配置校验（5 个维度）
│   ├── executor.py                 # ChainExecutor - 异步执行引擎
│   └── context.py                  # ExecutionContext - 异步执行上下文管理
│
├── models/                         # 数据模型（现有，扩展）
├── database/                       # 数据库层（现有）
├── config/                         # 配置（现有）
├── routers/                        # API 路由（现有，适配新引擎）
├── main.py
│
└── tests/                          # 单元测试
    ├── nodes/
    │   ├── test_base_node.py
    │   ├── test_node_registry.py
    │   ├── test_triggers/
    │   ├── test_detectors/
    │   ├── test_comparators/
    │   ├── test_scorers/
    │   ├── test_logic/
    │   └── test_actions/
    ├── engine/
    │   ├── test_parser.py
    │   ├── test_validator.py
    │   └── test_executor.py
    └── test_integration.py         # 集成测试
```

---

## 三、核心模块设计

### 3.1 BaseNode 抽象基类（全异步）

```python
# nodes/base.py

from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
from typing import Any
from enum import Enum

class PortType(Enum):
    INPUT = "input"
    OUTPUT = "output"
    TRUE = "true"           # 条件分支 - 满足
    FALSE = "false"         # 条件分支 - 不满足

class PortDef(BaseModel):
    """端口定义"""
    key: str                    # 端口标识（支持多输入: "input_0", "input_1", ...）
    label: str                  # 显示名
    data_type: str = "any"      # 数据类型: context / detection_output / comparison_output / score_output / logic_output / any
    required: bool = False      # 是否必须连接
    multi: bool = False         # 是否允许多个连接（用于多输入场景）

class NodeCategory(Enum):
    INPUT = "input"              # Trigger
    DETECTION = "detection"      # Detector
    COMPARISON = "comparison"    # Comparator
    SCORING = "scoring"          # Scorer
    LOGIC = "logic"              # Logic Expression
    ACTION = "action"            # Action

class NodeOutput(BaseModel):
    """统一输出模型"""
    node_id: str
    node_type: str
    score: float = Field(ge=0, le=100)
    passed: bool = True
    context: dict[str, Any] = Field(default_factory=dict)
    labels: list[str] = Field(default_factory=list)
    severity: str = "UNKNOWN"

class BaseNode(ABC):
    """所有节点的抽象基类（全异步）"""

    name: str              # 节点类型名（如 "gas_price_detector"）
    label: str             # 显示名（如 "Gas 价格检测"）
    description: str       # 描述
    category: NodeCategory # 节点分类
    icon: str              # 图标 emoji
    color: str             # 主题色

    @classmethod
    @abstractmethod
    def get_inputs(cls) -> list[PortDef]:
        """定义输入端口列表（支持多输入）"""
        ...

    @classmethod
    @abstractmethod
    def get_outputs(cls) -> list[PortDef]:
        """定义输出端口列表"""
        ...

    @classmethod
    def get_config_schema(cls) -> dict:
        """返回 JSON Schema 格式的配置定义（供前端动态渲染）"""
        return {}

    @classmethod
    def get_default_config(cls) -> dict:
        """返回默认配置"""
        return {}

    @abstractmethod
    async def execute(self, context: dict[str, Any],
                      inputs: dict[str, list[NodeOutput]]) -> NodeOutput:
        """
        异步执行节点逻辑

        Args:
            context: 全局执行上下文（含原始告警数据）
            inputs: 上游节点输出 { port_key: [NodeOutput, ...] }
                    多输入时每个 port_key 对应一个列表

        Returns:
            NodeOutput: 执行结果
        """
        ...

    def validate_config(self, config: dict) -> list[str]:
        """校验配置，返回错误列表（空列表表示合法）"""
        return []
```

### 3.2 检测器模块 (detectors/)

```python
# nodes/detectors/base.py

class BaseDetector(BaseNode):
    """检测器基类"""

    category = NodeCategory.DETECTION

    @classmethod
    def get_inputs(cls) -> list[PortDef]:
        return [PortDef(key="input", label="输入", data_type="any", required=True)]

    @classmethod
    def get_outputs(cls) -> list[PortDef]:
        return [PortDef(key="output", label="输出", data_type="detection_output")]

    async def execute(self, context: dict, inputs: dict[str, list[NodeOutput]]) -> NodeOutput:
        # 取第一个输入的 context 进行合并
        upstream = self._first_input(inputs)
        merged_context = {**context, **(upstream.context if upstream else {})}

        inp = self.InputModel(context=merged_context)
        output = await self.process(inp)

        return NodeOutput(
            node_id=self.node_id,
            node_type=self.category.value,
            score=max(0, min(100, output.score)),
            passed=output.score >= self.config.get("threshold", 50),
            context={**merged_context, "detection": output.detection},
            labels=output.labels,
            severity=output.severity,
        )

    async def process(self, input: DetectorInputMixin) -> DetectorOutputMixin:
        """
        异步执行检测逻辑（子类实现）

        Args:
            input: 检测器输入模型，含合并后的上下文

        Returns:
            检测器输出模型（score, passed, severity, labels, detection）
        """
        raise NotImplementedError
```

#### 检测器评分规范

| 分数区间 | 含义 | passed |
|---------|------|--------|
| 80-100 | 高度确信检测到异常 | True |
| 50-79 | 有一定可疑性 | True（默认阈值 50） |
| 20-49 | 可疑但不确定 | False |
| 0-19 | 基本排除 | False |

#### 检测器示例 — GasPriceDetector

```python
# nodes/detectors/gas_price.py

class GasPriceDetectorConfig(BaseModel):
    enabled: bool = True
    high_gas_threshold_usd: float = 100.0    # 高 Gas 阈值（USD）
    extreme_gas_threshold_usd: float = 500.0 # 极端 Gas 阈值（USD）
    threshold: float = 50.0                  # passed 阈值

class GasPriceDetector(BaseDetector):
    name = "gas_price_detector"
    label = "Gas 价格检测"
    description = "检测异常高的 Gas 费用"
    icon = "⛽"
    color = "#f59e0b"

    async def process(self, input: DetectorInputMixin) -> GasPriceOutput:
        context = input.context
        gas_price_usd = context.get("gas_price_usd", 0)

        if gas_price_usd >= self.config.extreme_gas_threshold_usd:
            score = 95
        elif gas_price_usd >= self.config.high_gas_threshold_usd:
            # 线性插值 50-90
            ratio = (gas_price_usd - self.config.high_gas_threshold_usd) / \
                    (self.config.extreme_gas_threshold_usd - self.config.high_gas_threshold_usd)
            score = 50 + ratio * 40
        else:
            # 低 Gas，分数随 Gas 增加线性上升 0-30
            ratio = gas_price_usd / self.config.high_gas_threshold_usd
            score = ratio * 30

        details = {
            "gas_price_usd": gas_price_usd,
            "gas_price_gwei": context.get("gas_price_gwei", 0),
        }
        threshold = self.config.get("threshold", 50.0)
        return GasPriceOutput(
            score=min(100, max(0, score)),
            passed=score >= threshold,
            severity=score_to_severity(score),
            labels=["high_gas"] if score >= threshold else [],
            detection=details,
        )
```

### 3.3 条件比较器模块 (comparators/)

```python
# nodes/comparators/base.py

class BaseComparator(BaseNode):
    """条件比较器基类 — 支持 score 输入，输出布尔判定"""

    category = NodeCategory.COMPARISON

    @classmethod
    def get_inputs(cls) -> list[PortDef]:
        return [
            PortDef(key="input_0", label="输入 1", data_type="detection_output",
                     required=True, multi=False),
            PortDef(key="input_1", label="输入 2 (可选)", data_type="detection_output",
                     required=False, multi=False),
            # 支持动态添加更多输入端口（前端渲染时根据配置生成）
        ]

    @classmethod
    def get_outputs(cls) -> list[PortDef]:
        return [
            PortDef(key="true", label="满足", data_type="comparison_output"),
            PortDef(key="false", label="不满足", data_type="comparison_output"),
        ]

    async def execute(self, context: dict, inputs: dict[str, list[NodeOutput]]) -> NodeOutput:
        scores = []
        for port_key in sorted(inputs.keys()):
            for inp in inputs[port_key]:
                scores.append(inp.score)

        inp = self.InputModel(scores=scores)
        output = await self.process(inp)

        result = output.passed
        details = output.detection
        details.setdefault("comparator_type", self.name)
        details["result"] = result

        return NodeOutput(
            node_id=self.node_id,
            node_type=self.category.value,
            score=output.score,
            passed=result,
            context=details,
        )

    async def process(self, input: ComparatorInputMixin) -> ComparatorOutputMixin:
        """
        执行比较逻辑（子类实现）

        Args:
            input: 比较器输入模型，含上游 score 列表

        Returns:
            比较器输出模型（score, passed, severity, detection）
        """
        raise NotImplementedError
```

#### 比较器实现

| 比较器 | 文件 | 说明 | 配置参数 |
|--------|------|------|---------|
| **ThresholdComparator** | `threshold.py` | 单值阈值比较 | `operator`: gt/lt/gte/lte/eq/neq, `value`: 阈值 |
| **RangeComparator** | `range.py` | 区间比较 | `min`: 下界, `max`: 上界 |
| **RegexComparator** | `regex.py` | 正则匹配（对 context 字段） | `field`: context 字段名, `pattern`: 正则表达式 |

#### ThresholdComparator 示例

```python
# nodes/comparators/threshold.py

class ThresholdComparator(BaseComparator):
    name = "threshold_comparator"
    label = "阈值比较"
    description = "将分数与阈值进行比较"

    @classmethod
    def get_config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "operator": {
                    "type": "string",
                    "enum": ["gt", "lt", "gte", "lte", "eq", "neq"],
                    "default": "gte",
                    "description": "比较操作符"
                },
                "value": {
                    "type": "number",
                    "minimum": 0, "maximum": 100,
                    "default": 50,
                    "description": "阈值"
                }
            }
        }

    async def process(self, input: ComparatorInputMixin) -> ComparatorOutputMixin:
        score = input.scores[0] if input.scores else 0
        op = self.config.get("operator", "gte")
        threshold = self.config.get("value", 50)

        ops = {"gt": lambda a, b: a > b, "lt": lambda a, b: a < b,
               "gte": lambda a, b: a >= b, "lte": lambda a, b: a <= b,
               "eq": lambda a, b: a == b, "neq": lambda a, b: a != b}

        result = ops[op](score, threshold)
        return ComparatorOutputMixin(
            score=100.0 if result else 0.0,
            passed=result,
            severity="UNKNOWN",
            detection={
                "comparator_type": "threshold",
                "score": score,
                "threshold": threshold,
                "operator": op,
                "result": result,
            },
        )
```

### 3.4 评分器模块 (scorers/)

```python
# nodes/scorers/base.py

class BaseScorer(BaseNode):
    """评分器基类 — 聚合多个 score 输入为单一 score"""

    category = NodeCategory.SCORING

    @classmethod
    def get_inputs(cls) -> list[PortDef]:
        return [
            PortDef(key="input_0", label="输入 1", data_type="detection_output",
                     required=True, multi=False),
            PortDef(key="input_1", label="输入 2", data_type="detection_output",
                     required=False, multi=False),
            # 支持动态添加更多输入端口
        ]

    @classmethod
    def get_outputs(cls) -> list[PortDef]:
        return [PortDef(key="output", label="聚合评分", data_type="score_output")]

    async def execute(self, context: dict, inputs: dict[str, list[NodeOutput]]) -> NodeOutput:
        scores = []
        for port_key in sorted(inputs.keys()):
            for inp in inputs[port_key]:
                scores.append(inp.score)

        inp = self.InputModel(scores=scores)
        output = await self.process(inp)

        agg_score = max(0.0, min(100.0, output.score))

        return NodeOutput(
            node_id=self.node_id,
            node_type=self.category.value,
            score=agg_score,
            passed=agg_score >= self.config.get("threshold", 50),
            context=output.detection,
        )

    async def process(self, input: ScorerInputMixin) -> ScorerOutputMixin:
        """
        聚合多个分数（子类实现）

        Returns:
            评分器输出模型（score, passed, severity, labels, detection）
        """
        raise NotImplementedError
```

#### 评分器实现

| 评分器 | 文件 | 说明 | 配置参数 |
|--------|------|------|---------|
| **MinMaxScorer** | `min_max.py` | 取最小或最大值 | `mode`: min/max |
| **AverageScorer** | `average.py` | 求平均值 | 无额外参数 |
| **WeightedScorer** | `weighted.py` | 加权求和 | `weights`: 权重数组（与输入数量一致） |

### 3.5 逻辑表达式模块 (logic/)

```python
# nodes/logic/base.py

class BaseLogicNode(BaseNode):
    """逻辑表达式基类 — 接收多个布尔型输入，输出逻辑结果"""

    category = NodeCategory.LOGIC

    @classmethod
    def get_inputs(cls) -> list[PortDef]:
        return [
            PortDef(key="input_0", label="输入 1", data_type="comparison_output",
                     required=True, multi=False),
            PortDef(key="input_1", label="输入 2", data_type="comparison_output",
                     required=True, multi=False),
            # 支持动态添加更多输入端口
        ]

    @classmethod
    def get_outputs(cls) -> list[PortDef]:
        return [
            PortDef(key="true", label="满足", data_type="logic_output"),
            PortDef(key="false", label="不满足", data_type="logic_output"),
        ]

    async def execute(self, context: dict, inputs: dict[str, list[NodeOutput]]) -> NodeOutput:
        # 收集所有输入的 passed 状态
        passed_list = []
        for port_key in sorted(inputs.keys()):
            for inp in inputs[port_key]:
                passed_list.append(inp.passed)

        inp = self.InputModel(passed_list=passed_list)
        output = await self.process(inp)

        result = output.passed
        details = output.detection

        return NodeOutput(
            node_id=self.node_id,
            node_type=self.category.value,
            score=output.score,
            passed=result,
            context=details,
        )

    async def process(self, input: LogicInputMixin) -> LogicOutputMixin:
        """
        评估逻辑表达式（子类实现）

        Returns:
            逻辑门输出模型（score, passed, severity, detection）
        """
        raise NotImplementedError
```

#### AND Gate

```python
# nodes/logic/and_gate.py

class AndGate(BaseLogicNode):
    name = "and_gate"
    label = "AND (全部满足)"
    description = "所有输入均满足条件时输出 true"

    async def process(self, input: LogicInputMixin) -> LogicOutputMixin:
        result = all(input.passed_list)
        return LogicOutputMixin(
            score=100.0 if result else 0.0,
            passed=result,
            severity="UNKNOWN",
            detection={
                "logic_type": "and",
                "matched_count": sum(input.passed_list),
                "total_count": len(input.passed_list),
                "all_passed": result,
            },
        )
```

#### OR Gate

```python
# nodes/logic/or_gate.py

class OrGate(BaseLogicNode):
    name = "or_gate"
    label = "OR (任一满足)"
    description = "任一输入满足条件时输出 true"

    async def process(self, input: LogicInputMixin) -> LogicOutputMixin:
        result = any(input.passed_list)
        return LogicOutputMixin(
            score=100.0 if result else 0.0,
            passed=result,
            severity="UNKNOWN",
            detection={
                "logic_type": "or",
                "matched_count": sum(input.passed_list),
                "total_count": len(input.passed_list),
                "any_passed": result,
            },
        )
```

### 3.6 动作模块 (actions/) — 全异步

```python
# nodes/actions/base.py

class BaseAction(BaseNode):
    """动作基类 — 终端节点，全异步执行副作用"""

    category = NodeCategory.ACTION

    @classmethod
    def get_inputs(cls) -> list[PortDef]:
        return [PortDef(key="input", label="输入", data_type="any", required=True)]

    @classmethod
    def get_outputs(cls) -> list[PortDef]:
        return []  # Action 是终端节点，无输出

    async def execute(self, context: dict, inputs: dict[str, list[NodeOutput]]) -> NodeOutput:
        upstream = self._first_input(inputs)
        merged_context = {**context, **(upstream.context if upstream else {})}

        inp = self.InputModel(
            context=merged_context,
            upstream_score=upstream.score if upstream else 0.0,
            upstream_passed=upstream.passed if upstream else True,
        )
        output = await self.process(inp)

        return NodeOutput(
            node_id=self.node_id,
            node_type=self.category.value,
            score=output.score,
            passed=output.passed,
            context={**merged_context, "action_result": output.action_result},
        )

    async def process(self, input: ActionInputMixin) -> ActionOutputMixin:
        """执行具体动作（子类实现），返回输出模型"""
        raise NotImplementedError
```

#### Action 实现（框架）

| Action | 文件 | 功能 | IO 类型 |
|--------|------|------|---------|
| `SetSeverityAction` | `set_severity.py` | 设置告警严重级别 | 纯计算 |
| `AddTagAction` | `add_tag.py` | 添加标签 | 纯计算 |
| `NotifyWebhookAction` | `notify_webhook.py` | Webhook 推送 | 网络 IO (httpx) |
| `NotifyTelegramAction` | `notify_telegram.py` | Telegram 推送 | 网络 IO (httpx) |
| `UpdateDatabaseAction` | `update_database.py` | 更新本地数据库 | 数据库 IO |

> "框架实现" = 完整的类结构和配置 schema，核心逻辑用 `raise NotImplementedError` 或简单占位，后续逐步填充。

### 3.7 节点注册表

```python
# nodes/__init__.py

class NodeRegistry:
    """统一节点注册表，按 category 分组管理"""

    _nodes: dict[str, type[BaseNode]] = {}

    @classmethod
    def register(cls, node_class: type[BaseNode]):
        instance = node_class.__new__(node_class)
        cls._nodes[instance.name] = node_class
        return node_class

    @classmethod
    def get(cls, name: str) -> type[BaseNode] | None:
        return cls._nodes.get(name)

    @classmethod
    def get_by_category(cls, category: NodeCategory) -> list[type[BaseNode]]:
        return [c for c in cls._nodes.values() if c.category == category]

    @classmethod
    def all(cls) -> dict[str, type[BaseNode]]:
        return dict(cls._nodes)

    @classmethod
    def get_schema_for_frontend(cls) -> list[dict]:
        """生成前端所需的节点类型列表（含端口定义 + 配置 schema）"""
        ...

# 启动时自动注册所有节点
from nodes.triggers.alert_trigger import AlertTrigger
from nodes.detectors import *
from nodes.comparators import *
from nodes.scorers import *
from nodes.logic import *
from nodes.actions import *
```

---

## 四、规则链引擎

### 4.1 ChainParser（配置解析）

职责：将前端提交的 JSON 配置解析为内部 DAG 结构。

```python
# engine/parser.py

@dataclass
class ParsedNode:
    node_id: str
    node_type: str                   # registry name
    label: str
    config: dict
    position: dict                   # 前端坐标（保留用于还原）

@dataclass
class ParsedEdge:
    edge_id: str
    source_id: str
    source_port: str                 # "output" / "true" / "false"
    target_id: str
    target_port: str                 # "input" / "input_0" / "input_1" / ...

@dataclass
class ParsedChain:
    nodes: list[ParsedNode]
    edges: list[ParsedEdge]
    trigger_node: ParsedNode | None
    adjacency: dict[str, list[str]]       # node_id -> [target_node_ids]
    reverse_adj: dict[str, list[str]]     # node_id -> [source_node_ids]
```

### 4.2 ChainValidator（配置校验）

```python
# engine/validator.py

class ValidationError(BaseModel):
    node_id: str | None = None
    edge_id: str | None = None
    level: str = "error"            # error / warning
    message: str

class ChainValidator:
    """
    规则链配置校验引擎

    校验维度：
    1. 结构校验 - 单入口、无孤立节点、无环路
    2. 端口校验 - 输入/输出端口连接合法性
    3. 类型校验 - 数据流类型兼容性（严格约束）
    4. 节点校验 - 节点配置是否合法
    5. 拓扑校验 - 节点执行顺序、终端节点检查
    """

    def validate(self, chain: ParsedChain) -> list[ValidationError]:
        errors = []
        errors.extend(self._validate_structure(chain))
        errors.extend(self._validate_ports(chain))
        errors.extend(self._validate_data_types(chain))
        errors.extend(self._validate_node_configs(chain))
        errors.extend(self._validate_topology(chain))
        return errors
```

#### 校验规则详解

**4.2.1 结构校验**

| 规则 | 级别 | 说明 |
|------|------|------|
| 单入口 | error | 必须有且仅有 1 个 trigger 节点 |
| 无孤立节点 | error | 所有节点必须可达（从 trigger 出发） |
| 无效用节点 | warning | 所有节点必须有路径到达 action 节点 |
| 无环路 | error | DAG 不能有环 |
| 无重复边 | error | 相同 source+port -> target+port 不能重复 |

**4.2.2 端口校验**

| 规则 | 级别 | 说明 |
|------|------|------|
| 必需输入 | error | required=True 的端口必须有连接 |
| 端口存在 | error | edge 引用的 port key 必须在目标节点的端口定义中 |
| 多输入限制 | error | 非 multi=True 的端口只允许一个连接 |
| 无输出连接 | warning | Action 节点的输出端口不应有连接 |

**4.2.3 数据类型校验（严格约束）**

```python
# 输出端口的 data_type → 可连接的目标输入端口的 data_type
ALLOWED_TYPE_MAPPING = {
    # Trigger 输出 context
    "context":              {"context": True, "any": True},
    # Detector 输出 detection_output
    "detection_output":     {"detection_output": True, "score": True, "any": True},
    # Comparator 输出 comparison_output
    "comparison_output":    {"comparison_output": True, "any": True},
    # Scorer 输出 score_output
    "score_output":         {"detection_output": True, "score_output": True, "any": True},
    # Logic 输出 logic_output
    "logic_output":         {"logic_output": True, "comparison_output": True, "any": True},
}

# 各节点分类允许接收的输入数据类型
CATEGORY_ALLOWED_INPUTS = {
    "trigger":     [],          # Trigger 无输入
    "detector":    {"context", "any"},
    "comparator":  {"detection_output", "score_output", "any"},
    "scorer":      {"detection_output", "score_output", "any"},
    "logic":       {"comparison_output", "logic_output", "any"},
    "action":      {"any"},
}
```

**4.2.4 节点配置校验**

调用每个节点的 `validate_config(config)` 方法。

**4.2.5 拓扑校验**

| 规则 | 级别 | 说明 |
|------|------|------|
| 节点注册 | error | 所有 node_type 必须在 NodeRegistry 中注册 |
| 执行顺序 | warning | 建议顺序: trigger → detector(s) → comparator/scorer → logic(s) → action(s) |
| 终端节点 | warning | 至少有一个 action 节点 |

### 4.3 ChainExecutor（异步执行引擎）

```python
# engine/executor.py

class ExecutionContext:
    """异步执行上下文，管理整个规则链执行过程中的数据流"""

    def __init__(self, chain: ParsedChain, alert_data: dict):
        self.chain = chain
        self.alert_data = alert_data
        self.node_outputs: dict[str, NodeOutput] = {}      # node_id -> output
        self.collected_labels: list[str] = []
        self.final_severity: str = "UNKNOWN"
        self.final_score: float = 0
        self.actions_executed: list[dict] = []
        self.errors: list[str] = []
        self.execution_log: list[dict] = []

class ChainExecutor:
    """
    规则链异步执行引擎

    执行策略：
    - 拓扑排序确定执行顺序
    - 同层级（无依赖关系）的节点使用 asyncio.gather 并发执行
    - 根据输出端口（true/false）决定下游路径
    - 全链路 async/await，不阻塞事件循环
    """

    async def execute(self, chain: ParsedChain, alert_data: dict) -> ExecutionContext:
        """
        异步执行完整规则链

        1. 校验规则链（调用 ChainValidator）
        2. 构建执行上下文
        3. 拓扑排序 + 分层（确定并发层级）
        4. 逐层并发执行
        5. 根据 passed/端口 裁剪后续路径
        6. 返回完整执行上下文
        """
        ...

    async def _execute_layer(
        self, layer: list[str], exec_ctx: ExecutionContext
    ) -> None:
        """并发执行同层节点"""
        tasks = []
        for node_id in layer:
            task = asyncio.create_task(self._execute_node(node_id, exec_ctx))
            tasks.append(task)
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _execute_node(
        self, node_id: str, exec_ctx: ExecutionContext
    ) -> NodeOutput:
        """执行单个节点（收集输入 → 实例化 → 调用 execute）"""
        ...
```

#### 异步执行策略图示

```
Layer 0:  [Trigger]                        ← 串行（唯一入口）
Layer 1:  [Detector_A, Detector_B, ...]    ← 并发（互相独立）
Layer 2:  [Comparator_X, Scorer_Y, ...]    ← 并发
Layer 3:  [Logic_AND, Logic_OR, ...]       ← 并发
Layer 4:  [Action_1, Action_2, ...]        ← 并发（终端节点）
```

---

## 五、与现有系统的集成

### 5.1 迁移策略（完全重写）

**不兼容旧配置**。直接使用新架构，数据库中旧的规则链配置需要手动迁移或清空。

```
Phase 1: 搭建框架（本次开发）
├── 创建 nodes/ 目录结构（6 种节点类型）
├── 实现 BaseNode + NodeRegistry + NodeOutput（全异步）
├── 实现 BaseDetector / BaseComparator / BaseScorer / BaseLogicNode / BaseAction
├── 实现 ChainParser + ChainValidator + ChainExecutor（异步）
├── 迁移 1-2 个检测器作为示范（GasPrice + AddressType）
├── 实现 ThresholdComparator + AverageScorer 示范
└── 完整单元测试

Phase 2: 迁移现有检测器
├── 将 8 个检测器迁移到新 nodes/detectors/ 架构
├── 统一评分输出（0-100）
└── 每个检测器的单元测试

Phase 3: 完善比较器 / 评分器 / 逻辑表达式
├── RangeComparator / RegexComparator
├── MinMaxScorer / WeightedScorer
├── AND / OR Gate
└── 多输入端口的前端适配

Phase 4: 实现 Action
├── NotifyWebhook / NotifyTelegram（全异步 httpx）
├── UpdateDatabase（async 数据库操作）
├── SetSeverity / AddTag
└── 前端节点配置面板适配

Phase 5: 集成 + API 适配
├── 替换现有 API 端点为新引擎
├── 前端 6 种节点类型适配
├── 集成测试
└── 清理旧代码
```

### 5.2 API 适配

现有 API 端点保持不变，内部调用切换到新引擎：

| 现有端点 | 变化 |
|---------|------|
| `POST /alert/submit` | 内部调用新 ChainExecutor |
| `POST /rule-chain/validate` | 调用新 ChainValidator |
| `GET /rule-chain/schema/node-types` | 从 NodeRegistry 动态生成 |
| `GET /rule-chain/schema/detectors` | 从 NodeRegistry.get_by_category(DETECTION) 生成 |

### 5.3 前端适配

前端需要从 5 种节点类型调整为 6 种：

| 旧类型 | 新类型 | 说明 |
|--------|--------|------|
| `trigger` | `trigger` | 不变 |
| `detector` | `detector` | 不变 |
| `condition` | `comparator` + `logic` | 拆分：比较操作 → comparator，逻辑组合 → logic |
| `scorer` | `scorer` | 独立节点类型 |
| `filter` | `comparator` | 合并到 comparator |
| `notifier` | `action` | actionType 区分（notify_webhook / notify_telegram） |
| `action` | `action` | 不变 |

---

## 六、单元测试计划

### 6.1 测试目录结构

```
tests/
├── nodes/
│   ├── test_base_node.py          # BaseNode 抽象、NodeOutput 模型
│   ├── test_node_registry.py      # 注册/查询/分类
│   ├── test_triggers/
│   │   └── test_alert_trigger.py
│   ├── test_detectors/
│   │   ├── conftest.py            # 公共 fixture（mock context）
│   │   ├── test_gas_price.py
│   │   └── ...
│   ├── test_comparators/
│   │   ├── conftest.py
│   │   ├── test_threshold.py
│   │   ├── test_range.py
│   │   └── test_regex.py
│   ├── test_scorers/
│   │   ├── conftest.py
│   │   ├── test_min_max.py
│   │   ├── test_average.py
│   │   └── test_weighted.py
│   ├── test_logic/
│   │   ├── test_and_gate.py
│   │   └── test_or_gate.py
│   └── test_actions/
│       ├── test_set_severity.py
│       ├── test_notify_webhook.py
│       └── ...
│
├── engine/
│   ├── test_parser.py
│   ├── test_validator.py
│   └── test_executor.py
│
└── test_integration.py
```

### 6.2 测试覆盖率目标

| 模块 | 最低覆盖率 | 说明 |
|------|-----------|------|
| `nodes/base.py` | 95% | 核心抽象 |
| `nodes/detectors/*` | 90% | 每个检测器独立测试 |
| `nodes/comparators/*` | 95% | 所有操作符 + 边界值 |
| `nodes/scorers/*` | 95% | 所有聚合策略 + 边界值 |
| `nodes/logic/*` | 95% | 逻辑组合各种情况 |
| `nodes/actions/*` | 80% | 框架测试，具体 IO 后续补充 |
| `engine/parser.py` | 90% | 各种配置格式 |
| `engine/validator.py` | 95% | 所有校验规则 |
| `engine/executor.py` | 85% | 异步执行 + 并发 + 异常处理 |

### 6.3 核心测试用例示例

#### Comparator 测试

```python
@pytest.mark.asyncio
class TestThresholdComparator:

    async def test_gte_passes_when_score_above_threshold(self):
        """score >= threshold 时 passed=True"""
        comp = ThresholdComparator(config={"operator": "gte", "value": 50})
        inputs = {"input_0": [NodeOutput(node_id="d1", score=75, passed=True)]}
        result = await comp.execute(context={}, inputs=inputs)
        assert result.score == 100
        assert result.passed is True

    async def test_lt_fails_when_score_above_threshold(self):
        """score > threshold 时 lt 比较应不通过"""
        comp = ThresholdComparator(config={"operator": "lt", "value": 50})
        inputs = {"input_0": [NodeOutput(node_id="d1", score=75, passed=True)]}
        result = await comp.execute(context={}, inputs=inputs)
        assert result.score == 0
        assert result.passed is False

    async def test_multi_input(self):
        """多输入时取第一个 score"""
        ...
```

#### Scorer 测试

```python
@pytest.mark.asyncio
class TestAverageScorer:

    async def test_average_of_three_scores(self):
        """三个分数取平均"""
        scorer = AverageScorer(config={})
        inputs = {
            "input_0": [NodeOutput(node_id="d1", score=60, passed=True)],
            "input_1": [NodeOutput(node_id="d2", score=80, passed=True)],
            "input_2": [NodeOutput(node_id="d3", score=100, passed=True)],
        }
        result = await scorer.execute(context={}, inputs=inputs)
        assert result.score == pytest.approx(80.0)

    async def test_single_input(self):
        """单个输入时 score 不变"""
        ...
```

#### Executor 异步测试

```python
@pytest.mark.asyncio
class TestChainExecutor:

    async def test_parallel_detectors(self):
        """同层检测器应并发执行"""
        chain = make_chain(...)
        exec_ctx = await executor.execute(chain, alert_data)
        # 验证两个检测器的执行时间重叠（并发）
        assert exec_ctx.execution_log[...]["parallel"]

    async def test_conditional_branch(self):
        """false 端口连接的节点不应执行"""
        ...

    async def test_action_timeout_handling(self):
        """Action 超时应优雅处理"""
        ...
```

#### Validator 测试

```python
class TestChainValidator:

    def test_logic_only_accepts_comparison_or_logic_output(self):
        """Logic 节点只能接收 comparison_output 或 logic_output"""
        chain = make_chain(trigger="t1", edges=[
            ("t1", "logic1")  # trigger → logic，应报错
        ])
        errors = ChainValidator().validate(chain)
        assert any("数据类型" in e.message for e in errors)

    def test_comparator_requires_score_input(self):
        """Comparator 需要 score 类输入"""
        ...

    def test_scorer_multi_input(self):
        """Scorer 支持多输入端口"""
        ...

    def test_detector_cannot_receive_logic_output(self):
        """检测器不能接收 logic 输出"""
        ...
```

---

## 七、开发顺序与里程碑

### Milestone 1: 节点框架（预计 1-2 天）

- [ ] `nodes/base.py` — BaseNode + NodeOutput + PortDef + NodeCategory + NodeRegistry
- [ ] `nodes/triggers/alert_trigger.py` — AlertTrigger 实现
- [ ] `nodes/detectors/base.py` — BaseDetector
- [ ] `nodes/comparators/base.py` — BaseComparator
- [ ] `nodes/scorers/base.py` — BaseScorer
- [ ] `nodes/logic/base.py` — BaseLogicNode
- [ ] `nodes/actions/base.py` — BaseAction
- [ ] 单元测试: `test_base_node.py`, `test_node_registry.py`

### Milestone 2: 引擎核心（预计 1-2 天）

- [ ] `engine/parser.py` — ChainParser
- [ ] `engine/validator.py` — ChainValidator（全部 5 个维度校验）
- [ ] `engine/executor.py` — ChainExecutor（异步 + 并发执行）
- [ ] `engine/context.py` — ExecutionContext
- [ ] 单元测试: `test_parser.py`, `test_validator.py`, `test_executor.py`

### Milestone 3: 检测器 + 比较器 + 评分器示范（预计 2-3 天）

- [ ] 迁移 GasPriceDetector（示范）
- [ ] 迁移 AddressTypeDetector（示范）
- [ ] 实现 ThresholdComparator + RangeComparator（示范）
- [ ] 实现 AverageScorer（示范）
- [ ] 实现 AND / OR Gate（示范）
- [ ] 每个节点的单元测试

### Milestone 4: 迁移所有检测器 + 完善比较器/评分器（预计 2-3 天）

- [ ] 迁移剩余 6 个检测器 + 单元测试
- [ ] 实现 MinMaxScorer + WeightedScorer + 测试
- [ ] 实现 RegexComparator + 测试

### Milestone 5: Action 框架 + 集成（预计 2 天）

- [ ] SetSeverity / AddTag 框架实现
- [ ] NotifyWebhook / NotifyTelegram（异步 httpx）框架实现
- [ ] UpdateDatabase 框架实现
- [ ] 替换现有 API 端点
- [ ] 集成测试

---

## 八、已确认的设计决策

1. **多输入支持** — Logic / Scorer / Comparator 节点均支持多个输入端口（`input_0`, `input_1`, ...）
2. **全异步执行** — 整个链路 async/await，同层节点 `asyncio.gather` 并发执行
3. **不兼容旧配置** — 完全重写，旧规则链配置需手动处理
4. **Scorer 独立节点** — 评分聚合作为独立节点类型，不内嵌在 Logic 中
5. **Comparator 独立节点** — 条件比较（阈值/区间/正则）作为独立节点类型

---

> 请审核以上设计，确认后开始 Milestone 1 开发。
