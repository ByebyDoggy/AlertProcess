# AlertProcessor

## 项目概述

AlertProcessor 是一个基于**可视化规则链（Rule Chain）**的区块链安全告警处理系统，灵感来自 [Forta Network](https://forta.org/) 和 [BlockSec](https://blocksec.com/)。通过拖拽式节点编排，对链上告警进行多维度检测、评分、比较和响应。

核心设计理念：**一切皆节点**。系统将告警处理流程抽象为可组合的有向无环图（DAG），每个节点负责单一职责，通过端口连接构建复杂的处理流水线。

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.13 / FastAPI / SQLAlchemy / Pydantic |
| 前端 | Vue 3 / Pinia / Tailwind CSS / Vite / Chart.js |
| 数据库 | SQLite（默认） |
| 区块链 | Web3.py / Moralis API / ARKM Intelligence API |
| 部署 | Docker Compose / Nginx |

## 主要特性

- **可视化规则链编辑器** — 拖拽节点、连线、动态配置表单，所见即所得
- **边级 Input Transformer** — 点击连线即可打开数据转换编辑面板，支持 Python/JavaScript 双语言表达式，将上游输出变换为下游期望的输入结构，带实时语法校验与预览；解决多对一/多对多输入场景的数据对齐问题
- **Pydantic 驱动的节点模型** — ConfigModel/OutputModel/InputModel 三层 Pydantic 模型，自动生成 JSON Schema 供前端动态渲染；每类节点定义模块级 InputMixin/OutputMixin 基类，具体节点的自定义模型在类外继承 Mixin；核心业务方法统一为 `process()`，基类 `execute()` 负责构造输入、调用 `process()`、转换输出
- **5 维校验引擎** — 结构、端口、数据类型（端口+字段双级）、节点配置、拓扑全方位校验
- **异步并发执行** — Kahn 算法拓扑排序 + 同层 `asyncio.gather` 并发
- **7 大节点分类** — 触发器、上下文查询、检测器、比较器、评分器、逻辑门、动作，共 29 内置节点（全部定义 output_fields）
- **布尔分支路由** — 比较器/逻辑门通过 `true`/`false` 输出端口实现条件分支
- **数据类型安全** — 完整的类型兼容性矩阵（端口级 + 字段级双层级校验）
- **多种通知渠道** — Webhook、Telegram Bot、数据库持久化
- **告警知识库** — 存储、浏览恶意交易样本，支持分类/搜索/导入导出
- **Dry-run / 逐节点测试** — 支持全链路 dry-run 和 n8n 式单节点调试

## 项目结构

```
AlertProcessor/
├── main.py                          # FastAPI 应用入口
├── config/                          # 配置管理
│   └── model.py                     # Pydantic Settings
├── engine/                          # 规则链执行引擎
│   ├── parser.py                    # JSON -> DAG 解析器
│   ├── validator.py                 # 5 维校验引擎
│   ├── executor.py                  # 异步执行引擎（拓扑排序 + 并发）
│   ├── transformer.py               # 输入转换器引擎（Python/JS 表达式求值）
│   └── context.py                   # 执行上下文管理
├── nodes/                           # 可插拔节点系统
│   ├── base.py                      # BaseNode 基类 + NodeRegistry 注册表（含 Pydantic ConfigModel/OutputModel/InputModel）
│   ├── models.py                    # TransactionContext 数据传输基础模型 + DetectorResult
│   ├── triggers/                    # 触发器（入口节点）
│   ├── detectors/                   # 检测器（风险评分 0-100）
│   ├── providers/                   # ContextProvider 节点（外部 API 数据注入）
│   ├── comparators/                 # 比较器（布尔判定）
│   ├── scorers/                     # 评分器（聚合评分）
│   ├── logic/                       # 逻辑门（AND / OR）
│   ├── actions/                     # 动作（终端节点）
│   ├── memory/                      # 记忆节点（时序检测支持，TTL 键值存储）
│   └── context/                      # 旧版 ContextProvider（保留兼容）
├── models/                          # 核心数据模型
│   └── __init__.py                  # AlertInput, FinalAlert, TransactionContext 等
├── database/                        # 数据库层
│   └── models.py                    # SQLAlchemy ORM（AlertDB, RuleChainDB 等）
├── routers/                         # API 路由
│   ├── rule_chain/router.py         # 规则链 CRUD + Schema + 校验 + 测试运行
│   ├── knowledge_base/              # 知识库 CRUD + 搜索 + 导入导出
│   ├── detectors/                   # 交易分析 + 日志接收
│   └── pool_config/                 # Pool 配置管理 (apipool-server)
├── data/                            # 预置数据
│   └── sample_alerts.json           # 知识库预置样本
├── frontend/                        # Vue 3 前端
│   └── src/
│       ├── views/                   # 页面视图（规则链编辑器、知识库管理）
│       ├── components/editor/        # 编辑器核心组件（Canvas, NodeCard, Edge, EdgeTransformerPanel）
│       ├── stores/                  # Pinia 状态管理
│       ├── composables/             # 组合式函数
│       ├── api/                     # API 封装
│       └── utils/                   # 工具函数
├── tests/                           # 单元测试
│   ├── engine/                      # 引擎测试
│   └── nodes/                       # 各类节点测试
├── Dockerfile.backend               # 后端 Docker 镜像
├── Dockerfile.frontend              # 前端 Docker 镜像（多阶段构建）
├── docker-compose.yml               # 一键部署
└── requirements.txt                 # Python 依赖
```

## 快速开始

### 1. 创建虚拟环境并安装依赖

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件：

```env
api_key=your-secret-api-key
moralis_api_key=your-moralis-api-key
arkm_cookie=your-arkm-cookie

# apipool-server 配置 (RPC 调用统一由 apipool-server 管理)
apipool_server_url=http://localhost:8000
apipool_username=your-username
apipool_password=your-password
# 每条链的 pool_identifier (JSON 格式)
apipool_pool_map={"1":"ethereum-rpc","56":"bsc-rpc","137":"polygon-rpc"}
```

### 3. 启动后端

```bash
python main.py
```

服务将在 http://localhost:8000 启动，API 文档：http://localhost:8000/docs

### 4. 启动前端（开发模式）

```bash
cd frontend
npm install
npm run dev
```

前端开发服务器将在 http://localhost:3000 启动，API 请求自动代理到后端。

### 5. Docker 一键部署

```bash
docker-compose up -d
```

- 后端：http://localhost:8000
- 前端（Nginx）：http://localhost:80

## 节点系统

所有节点继承 `BaseNode` 抽象基类，通过 `NodeRegistry` 装饰器自动注册。节点分为 6 大类别：

### 规则链数据流

```
Trigger → Provider(s) → Detector(s) → Comparator(s) / Scorer(s) → Logic Gate(s) → Action(s)
   ↓               ↓                    ↓
 入口节点    context 端口        true/false 端口分支
```

### 数据传输基础模型

所有 ContextProvider 节点和 Detector 节点的输入输出都基于 `TransactionContext` 数据传输基础模型：

```python
class TransactionContext(BaseModel):
    """数据传输基础模型 — 规则链中节点间传递的标准交易上下文"""
    chain_id: int           # 区块链网络 ID
    tx_hash: str            # 交易哈希
    block_number: int        # 区块号
    from_address: str       # 发起地址
    to_address: str          # 目标地址
    value: int              # 转账金额（wei）
    gas_price: int          # Gas 价格（wei）
    gas_used: int           # Gas 消耗
    input_data: str         # calldata
    timestamp: str           # 时间戳
    logs: list[dict]         # Event Logs
    extra: dict[str, Any]   # 扩展字段（Provider 节点注入的数据）
```

**架构说明**：
- `AlertTriggerOutput` 继承 `TransactionContext`，作为入口输出
- `ContextProvider` 节点：输入 `TransactionContext`，输出 `TransactionContext`（`extra` 中填充 Provider 获取的数据）
- `Detector` 节点：输入 `TransactionContext`，输出双端口 `context` + `detection`

### 内置节点一览

#### 触发器（INPUT）

| 节点 | 说明 |
|------|------|
| `alert_trigger` | 规则链入口，接收外部告警数据（chain_id, tx_hash 等） |

#### Provider 节点（DETECTION）— 上下文数据注入

| 节点 | 说明 |
|------|------|
| `moralis_address_provider` | Moralis API 查询地址首次活跃时间，注入 `address_create_time`、`address_age_days` |
| `arkm_label_provider` | ARKM Intelligence API 查询实体标签，注入 `entity_type`、`entity_name`、`entity_confidence` |

#### 检测器（DETECTION）— 评分 0-100

| 节点 | 说明 |
|------|------|
| `gas_price_detector` | 异常 Gas 费用（线性插值评分，多链原生代币价格映射） |
| `address_type_detector` | null 地址交易、合约创建模式检测 |
| `flash_loan_detector` | 闪电贷攻击（Aave/dYdX/Uniswap/Compound） |
| `token_approval_detector` | 可疑 ERC20 授权（无限授权、setApprovalForAll） |
| `token_anomaly_detector` | 异常代币转账（大额、新代币、异常合约交互） |
| `address_graph_detector` | 地址关系图谱（已知攻击者、交易所关联） |
| `address_age_detector` | 新建地址检测 |
| `arkm_label_detector` | ARKM Intelligence 恶意实体标签 |
| `reentrancy_detector` | 重入攻击检测（调用栈深度、外部调用模式分析） |

#### 比较器（COMPARISON）— 布尔判定

| 节点 | 说明 |
|------|------|
| `threshold_comparator` | 阈值比较（gt / lt / gte / lte / eq / neq） |
| `range_comparator` | 区间比较（inside / outside） |
| `regex_comparator` | 正则匹配（支持嵌套字段、search / fullmatch / match） |

#### 评分器（SCORING）— 聚合评分

| 节点 | 说明 |
|------|------|
| `average_scorer` | 算术平均 |
| `minmax_scorer` | 取最大 / 最小值 |
| `weighted_scorer` | 加权求和（可配置权重、归一化） |
| `constant_scorer` | 固定常量值（作为基准参考） |

#### 逻辑门（LOGIC）

| 节点 | 说明 |
|------|------|
| `and_gate` | AND 门 — 全部输入为 true 时输出 true |
| `or_gate` | OR 门 — 任一输入为 true 时输出 true |

#### 动作（ACTION）

| 节点 | 说明 |
|------|------|
| `set_severity_action` | 设置告警严重级别（always / passed / not_passed 条件） |
| `add_tag_action` | 添加自定义标签（支持去重） |
| `notify_webhook_action` | 发送 Webhook HTTP 请求（POST / PUT / PATCH） |
| `notify_telegram_action` | 发送 Telegram Bot 消息（模板变量替换） |
| `update_database_action` | 写入数据库（insert / upsert） |

### 自定义节点

继承对应类别基类（如 `BaseDetector`）并使用 `NodeRegistry.register` 装饰器即可注册新节点：

```python
from nodes.base import BaseNode, NodeOutput, NodeRegistry, PortDef, NodeCategory
from nodes.detectors.base import BaseDetector, DetectorConfigMixin, DetectorOutputMixin
from nodes.models import TransactionContext

# 1. 在类外定义 OutputModel（继承类别 Mixin）
class MyCustomOutput(DetectorOutputMixin):
    pass

@NodeRegistry.register
class MyCustomDetector(BaseDetector):
    name = "my_custom_detector"
    label = "自定义检测器"
    description = "我的自定义检测节点"

    # 2. ConfigModel 保持嵌套类
    class ConfigModel(DetectorConfigMixin):
        my_param: int = 10

    # 3. OutputModel 引用类外定义
    OutputModel = MyCustomOutput

    # 4. 实现 process() 方法，接收 TransactionContext
    async def process(self, tx_context: TransactionContext) -> MyCustomOutput:
        # 从 tx_context 读取标准字段
        chain_id = tx_context.chain_id
        from_address = tx_context.from_address
        # 从 tx_context.extra 读取 Provider 注入的数据
        address_age = tx_context.extra.get("address_age_days")
        # 实现检测逻辑...
        return MyCustomOutput(
            score=50.0, passed=True, severity="LOW",
            labels=[], detection={"result": "ok"},
        )
```

### 自定义 Provider 节点

继承 `BaseContextProviderNode` 并实现 `fetch()` 方法：

```python
from nodes.providers.base import BaseContextProviderNode
from nodes.models import TransactionContext
from nodes.base import NodeRegistry

@NodeRegistry.register
class MyDataProviderNode(BaseContextProviderNode):
    name = "my_data_provider"
    label = "我的数据查询"
    description = "从外部 API 获取数据"

    provides = ["custom_field1", "custom_field2"]  # 声明注入的字段

    async def fetch(self, tx_context: TransactionContext) -> dict[str, Any]:
        # 调用外部 API 获取数据
        # 返回要注入到 extra 的字段字典
        return {
            "custom_field1": "value1",
            "custom_field2": "value2",
        }
```

### Expression Selector 连线表达式选择器

连线（Edge）上集成了类似 n8n 的表达式选择功能，支持 `$json.path` 语法：

**交互流程**：
1. 点击连线上绿色表达式标签 → 弹出字段选择器
2. 字段列表自动从上游节点的 `output_fields` 收集，按类型着色
3. 点击字段项即选中（支持切换），显示 `$json.xxx.yyy` 格式路径
4. 点击「确认映射」保存到边的 `expression` + `fieldMapping` 数据
5. 下游节点输入面板自动展示已映射的上游字段

**数据结构**：
- `edge.expression` — 字符串形式如 `$json.detection.score`
- `edge.fieldMapping` — 对象形式 `{ "$json.detection.score": { key, label, type } }`

**组件架构**：`Canvas.vue` 管理弹窗状态 → `ExpressionSelector.vue` 渲染选择 UI → `Edge.vue` 展示表达式标签 + 点击触发

### n8n 风格结构化输出系统

前端节点卡片展示类似 n8n 的结构化输出面板，核心设计：

**后端 Schema 定义**（Pydantic 模型）：
```python
from nodes.base import BaseNode, NodeOutputMixin
from nodes.detectors.base import BaseDetector, DetectorOutputMixin

class MyDetectorOutput(DetectorOutputMixin):
    """检测器输出 — 自动生成 JSON Schema"""

class MyDetector(BaseDetector):
    OutputModel = MyDetectorOutput

    async def process(self, input):
        return MyDetectorOutput(score=80, passed=True, severity="HIGH", ...)
```

**前端功能**：
- 节点卡片 I/O 面板：期望输入结构面板（显示节点所需的输入字段和类型）+ 输出数据面板，按类型颜色标识（string=蓝, number=绿, boolean=橙, array=紫, object=粉）
- Input Transformer 输入转换器：连线后自动显示，支持 Python/JavaScript 双语言表达式编辑，带语法校验、实时预览、JS→Python 翻译预览
- Expression Selector：点击连线表达式标签打开字段选择弹窗，支持 `$json.path` 语法选择上游输出字段
- 连线 Edge 组件：显示已映射表达式标签（绿色 badge），点击触发编辑
- 端口锚点：节点四侧的连接端口（input/output），支持拖拽连线
- 字段类型兼容性矩阵在连线时自动校验

## API 接口

### 健康检查

```
GET /api/health
```

### 规则链管理

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/rule-chain/` | 列出所有规则链 |
| `GET` | `/rule-chain/{chain_id}` | 获取指定规则链 |
| `POST` | `/rule-chain/` | 创建规则链 |
| `PUT` | `/rule-chain/{chain_id}` | 更新规则链 |
| `DELETE` | `/rule-chain/{chain_id}` | 删除规则链 |
| `POST` | `/rule-chain/validate` | 校验规则链配置 |

所有规则链接口需要 `X-API-Key` 请求头认证。

### Schema 查询（无需认证）

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/rule-chain/schema/nodes` | 所有已注册节点完整 Schema（端口、配置） |
| `GET` | `/rule-chain/schema/node-types` | 节点类型列表 |
| `GET` | `/rule-chain/schema/detectors` | 检测器节点详细信息 |
| `GET` | `/rule-chain/schema/connection-rules` | 数据类型兼容性矩阵 |

### 输入转换器

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/rule-chain/transformer/validate` | 校验表达式语法（不执行） |
| `POST` | `/rule-chain/transformer/preview` | 使用示例输入预览表达式执行结果 |

**校验请求体**：
```json
{
  "expression": "{\"address\": input[\"from_address\"], \"val\": int(input[\"value\"])}",
  "language": "python"
}
```

**预览请求体**：
```json
{
  "expression": "{\"address\": input[\"from_address\"]}",
  "language": "python",
  "sample_input": {"from_address": "0xabc", "value": "100"}
}
```

支持 `language: "python"` 或 `"javascript"`。JS 表达式会自动翻译为 Python 等价形式执行。

### 规则链测试运行

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/rule-chain/{chain_id}/test-run` | 使用知识库样本或自定义数据测试规则链（dry-run） |

请求体：
```json
{
  "sample_ids": ["uuid-1", "uuid-2"],
  "alert_data": null
}
```

Action 节点在 dry-run 模式下仅模拟执行，不会产生实际副作用。

### 知识库管理

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/knowledge-base/` | 列出样本（支持分页、分类、搜索过滤） |
| `GET` | `/knowledge-base/{id}` | 获取样本详情 |
| `POST` | `/knowledge-base/` | 创建样本 |
| `PUT` | `/knowledge-base/{id}` | 更新样本 |
| `DELETE` | `/knowledge-base/{id}` | 删除样本 |
| `POST` | `/knowledge-base/import` | 批量导入 |
| `GET` | `/knowledge-base/export/all` | 导出全部 |
| `GET` | `/knowledge-base/meta/categories` | 获取预设分类列表 |

### Pool 配置管理 (apipool-server)

所有 RPC 调用统一由 apipool-server 管理，每条链使用独立的 `pool_identifier`。

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/pool-config/` | 获取所有链的 pool 配置 |
| `GET` | `/pool-config/chains` | 支持的链列表 |
| `GET` | `/pool-config/status` | 池运行状态 |
| `PUT` | `/pool-config/{chain_id}` | 更新链的 pool_identifier |
| `POST` | `/pool-config/health-check` | 健康检查 |
| `POST` | `/pool-config/reload` | 重新加载配置 |
| `POST` | `/pool-config/test-connection` | 测试 RPC URL 连通性 |

## 引擎架构

### 解析器（ChainParser）

将前端 JSON（nodes + edges）解析为内部 DAG 结构（`ParsedChain`），支持双向序列化。

### 校验器（ChainValidator）

5 维校验引擎，返回结构化错误列表：

1. **结构校验** — 单入口、无孤立节点、无环路
2. **端口校验** — 连接端口合法性
3. **数据类型校验** — 类型兼容性矩阵
4. **节点配置校验** — 配置参数合法性
5. **拓扑校验** — 节点可达性（入度为 0 的非触发节点报错）

### 执行器（ChainExecutor）

- Kahn 算法分层拓扑排序
- 同层节点 `asyncio.gather` 并发执行
- 基于输出端口（`true`/`false`）路由下游路径
- 完整的执行日志记录
- Dry-run 模式：Action 节点模拟执行，用于测试验证

## 测试

```bash
pytest tests/ -v
```

测试覆盖引擎（parser / validator / executor）、所有节点类型、API 端点和知识库功能。

## License

MIT
