# 告警知识库（Alert Knowledge Base）开发文档

## 1. 功能概述

构建一个**告警知识库**模块，用于加载、存储和管理恶意交易日志。提供两大核心能力：

1. **知识管理** — 用户可浏览、搜索、导入/导出恶意交易样本，形成可复用的安全知识积累
2. **规则测验** — 将知识库中的样本作为输入，对规则链进行 dry-run 测试，验证规则是否按预期触发，无需真实告警

### 用户场景

```
场景 A（知识积累）:
  安全研究员发现一笔新攻击交易 → 录入知识库（附带标签、分类、原始上下文）
  → 团队成员随时查阅检索

场景 B（规则调试）:
  用户编辑一条规则链 → 选择知识库中的样本 → 点击"测试运行"
  → 查看每个节点的评分/通过/详情 → 调整规则参数 → 反复测试
```

---

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────┐
│                    前端 UI                           │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────┐ │
│  │ 知识库管理页面 │  │ 规则链编辑器   │  │ 测试面板 │ │
│  │ (浏览/搜索/   │  │ + "测试运行"  │  │ (结果展示)│ │
│  │  导入/导出)   │  │  按钮         │  │          │ │
│  └──────┬───────┘  └──────┬────────┘  └────┬─────┘ │
└─────────┼─────────────────┼────────────────┼───────┘
          │                 │                │
          ▼                 ▼                ▼
┌─────────────────────────────────────────────────────┐
│                   API Layer                          │
│  ┌──────────────────┐  ┌──────────────────────────┐ │
│  │ /knowledge-base  │  │ /rule-chain/{id}/test-run│ │
│  │   CRUD + 搜索    │  │  知识库样本 → 规则链执行  │ │
│  └────────┬─────────┘  └──────────┬───────────────┘ │
└───────────┼───────────────────────┼─────────────────┘
            │                       │
            ▼                       ▼
┌───────────────────┐   ┌──────────────────────────┐
│ KnowledgeBaseDB   │   │ ChainExecutor.dry_run()  │
│ (SQLite)          │   │ (已有引擎，新增 dry_run)  │
└───────────────────┘   └──────────────────────────┘
```

### 2.2 数据流

```
知识库样本 (alert_data dict)
    │
    ▼
AlertTrigger 节点 (透传 alert_data)
    │
    ▼
各检测器节点 (读取 context 字段: gas_price, to_address, input_data...)
    │
    ▼
比较器 / 评分器 / 逻辑门
    │
    ▼
动作节点 (dry-run 模式下仅模拟，不实际发送通知/写库)
    │
    ▼
返回完整 ExecutionContext (各节点评分、日志、标签)
```

---

## 3. 数据模型

### 3.1 数据库表 — `knowledge_base`

在 `database/models.py` 中新增：

```python
class KnowledgeBaseDB(Base):
    __tablename__ = "knowledge_base"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # 基本信息
    title = Column(String, nullable=False, index=True)           # 样本标题
    description = Column(Text, nullable=True)                     # 详细描述
    category = Column(String, index=True)                         # 分类: flash_loan / gas_manipulation / ...
    tags = Column(Text, default="[]")                             # JSON 数组: ["闪电贷","Aave"]
    chain_id = Column(Integer, index=True)                        # 链 ID
    
    # 告警输入 (最小字段，对应 AlertInput)
    tx_hash = Column(String, index=True)                          # 交易哈希
    attacked_address = Column(String, nullable=True)
    exploiter_address = Column(String, nullable=True)
    
    # 完整交易上下文 (JSON，对应 TransactionContext 全部字段)
    # 这是传给规则链引擎的原始数据
    alert_data = Column(Text, nullable=False)                     # JSON dict
    
    # 预期结果 (可选，用于自动化测试)
    expected_severity = Column(String, nullable=True)             # 预期严重级别
    expected_labels = Column(Text, default="[]")                  # 预期标签
    expected_min_score = Column(Integer, nullable=True)           # 预期最低评分
    
    # 元信息
    source = Column(String, default="manual")                     # 来源: manual / import / forta / api
    tx_explorer_url = Column(String, nullable=True)               # 区块链浏览器链接
    
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
```

### 3.2 Pydantic 模型

在 `models/` 中新增或扩展：

```python
class KnowledgeBaseCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category: Optional[str] = "uncategorized"
    tags: list[str] = []
    chain_id: int = 1
    tx_hash: str
    attacked_address: Optional[str] = None
    exploiter_address: Optional[str] = None
    alert_data: dict[str, Any]           # 完整的交易上下文
    expected_severity: Optional[str] = None
    expected_labels: list[str] = []
    expected_min_score: Optional[int] = None
    source: str = "manual"
    tx_explorer_url: Optional[str] = None

class KnowledgeBaseResponse(BaseModel):
    id: str
    title: str
    description: Optional[str]
    category: str
    tags: list[str]
    chain_id: int
    tx_hash: str
    attacked_address: Optional[str]
    exploiter_address: Optional[str]
    alert_data: dict[str, Any]
    expected_severity: Optional[str]
    expected_labels: list[str]
    expected_min_score: Optional[int]
    source: str
    tx_explorer_url: Optional[str]
    created_at: datetime
    updated_at: datetime

class TestRunRequest(BaseModel):
    sample_ids: list[str]                # 从知识库选取的样本 ID 列表
    # 或直接提供
    alert_data: Optional[dict[str, Any]] = None   # 手动输入的告警数据（不使用知识库时）

class TestRunResult(BaseModel):
    sample_id: Optional[str]             # 关联的知识库样本 ID
    sample_title: Optional[str]          # 样本标题
    chain_id: str                        # 规则链 ID
    chain_name: str                      # 规则链名称
    success: bool                        # 是否成功执行
    final_score: float                   # 最终评分
    final_severity: str                  # 最终严重级别
    labels: list[str]                    # 聚合标签
    actions_executed: list[dict]         # 执行的动作列表
    node_results: list[dict]             # 各节点执行详情
    errors: list[str]                    # 错误列表
    duration_ms: float                   # 总执行耗时
    expected_matched: Optional[bool]     # 是否匹配预期结果
    expected_details: Optional[dict]     # 预期匹配详情
```

---

## 4. API 接口设计

### 4.1 知识库 CRUD — `/knowledge-base`

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| `GET` | `/knowledge-base/` | 列出所有样本（支持分页、过滤） | 需要 |
| `GET` | `/knowledge-base/{id}` | 获取单个样本详情 | 需要 |
| `POST` | `/knowledge-base/` | 创建新样本 | 需要 |
| `PUT` | `/knowledge-base/{id}` | 更新样本 | 需要 |
| `DELETE` | `/knowledge-base/{id}` | 删除样本 | 需要 |
| `POST` | `/knowledge-base/import` | 批量导入（JSON/CSV） | 需要 |
| `GET` | `/knowledge-base/export` | 批量导出 | 需要 |

**列表接口查询参数：**

```
GET /knowledge-base/?skip=0&limit=20&category=flash_loan&chain_id=1&search=关键词&tag=闪电贷
```

### 4.2 规则链测试运行 — `/rule-chain/{chain_id}/test-run`

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| `POST` | `/rule-chain/{chain_id}/test-run` | 用知识库样本测试运行规则链 | 需要 |

**请求体：**

```json
{
  "sample_ids": ["uuid-1", "uuid-2"],
  "alert_data": null
}
```

或直接传入自定义数据：

```json
{
  "sample_ids": [],
  "alert_data": {
    "chain_id": 1,
    "tx_hash": "0xabc...",
    "gas_price": 50000000000,
    "gas_used": 21000,
    "to_address": "0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9",
    "input_data": "0x0906f8c8...",
    "value": "1000000000000000000"
  }
}
```

**响应体：**

```json
{
  "results": [
    {
      "sample_id": "uuid-1",
      "sample_title": "Aave V2 闪电贷攻击 - Euler Finance",
      "chain_id": "rule-chain-uuid",
      "chain_name": "闪电贷检测规则",
      "success": true,
      "final_score": 95.0,
      "final_severity": "CRITICAL",
      "labels": ["LARGE_FLASH_LOAN_ATTACK", "high_gas"],
      "actions_executed": [
        {
          "node_id": "node-3",
          "node_type": "notify_webhook_action",
          "passed": true,
          "result": {"dry_run": true, "status": "simulated"}
        }
      ],
      "node_results": [
        {
          "node_id": "node-1",
          "node_type": "alert_trigger",
          "label": "告警触发器",
          "score": 0,
          "passed": true,
          "duration_ms": 0.5
        },
        {
          "node_id": "node-2",
          "node_type": "flash_loan_detector",
          "label": "闪电贷检测",
          "score": 95,
          "passed": true,
          "duration_ms": 12.3,
          "details": {
            "protocol": "Aave V2",
            "value_usd": 150000.0,
            "detected_issues": ["LARGE_FLASH_LOAN_ATTACK:Aave V2"]
          }
        }
      ],
      "errors": [],
      "duration_ms": 45.2,
      "expected_matched": true,
      "expected_details": {
        "severity_match": true,
        "labels_match": true,
        "min_score_match": true
      }
    }
  ]
}
```

### 4.3 预置分类常量

```
flash_loan        — 闪电贷攻击
gas_manipulation  — Gas 价格操纵
rug_pull          — 跑路/Rug Pull
token_exploit     — Token 合约漏洞利用
approval_phishing — 授权钓鱼
address_spoofing  — 地址伪造
phishing          — 钓鱼攻击
mev               — MEV / 三明治攻击
unknown           — 未分类
```

---

## 5. 后端实现计划

### 5.1 新增文件

```
routers/
  knowledge_base/
    __init__.py
    router.py              # 知识库 CRUD + 搜索 + 导入导出

data/
  sample_alerts.json       # 预置样本数据文件

tests/
  test_knowledge_base_api.py
```

### 5.2 修改文件

| 文件 | 修改内容 |
|------|----------|
| `database/models.py` | 新增 `KnowledgeBaseDB` 表 |
| `routers/rule_chain/router.py` | 新增 `POST /{chain_id}/test-run` 端点 |
| `engine/executor.py` | 新增 `dry_run` 参数，Action 节点在 dry-run 下仅模拟执行 |
| `nodes/actions/base.py` | 支持 dry_run 模式 |
| `main.py` | 注册 `knowledgeBaseRouter` |

### 5.3 关键实现细节

#### Action 节点 Dry-Run 模式

在 `ExecutionContext` 中新增 `dry_run: bool = False` 标志。Action 节点的 `execute()` 检测此标志：

```python
# engine/context.py 新增字段
dry_run: bool = False

# nodes/actions/base.py 中
async def execute(self, context, inputs):
    ctx = ...  # 获取 ExecutionContext
    if ctx.dry_run:
        return NodeOutput(
            score=0, passed=True,
            context={"action_result": {"dry_run": True, "simulated": True}}
        )
    # 正常执行...
```

#### Test-Run 端点核心逻辑

```python
# routers/rule_chain/router.py 新增

@ruleChainRouter.post("/{chain_id}/test-run")
async def test_run_chain(chain_id: str, body: TestRunRequest):
    # 1. 加载规则链
    db_chain = db.query(RuleChainDB).filter_by(id=chain_id).first()
    chain_config = json.loads(db_chain.chain_config)
    parsed_chain = ChainParser.parse(chain_config)

    # 2. 准备测试数据
    if body.alert_data:
        test_cases = [(None, None, body.alert_data)]
    else:
        samples = db.query(KnowledgeBaseDB).filter(
            KnowledgeBaseDB.id.in_(body.sample_ids)
        ).all()
        test_cases = [
            (s.id, s.title, json.loads(s.alert_data)) for s in samples
        ]

    # 3. 逐个执行
    executor = ChainExecutor()
    results = []
    for sample_id, sample_title, alert_data in test_cases:
        ctx = ExecutionContext(alert_data=alert_data, dry_run=True)
        # 复用 execute 逻辑，注入 dry_run context
        ctx = await executor.execute(parsed_chain, alert_data)
        ctx.dry_run = True  # 设置 dry_run 标志（供后续检查）

        # 4. 预期匹配检查
        expected_matched = check_expectations(ctx, sample)

        results.append(TestRunResult(...))

    return {"results": results}
```

---

## 6. 预置样本数据

在 `data/sample_alerts.json` 中预置典型攻击样本，系统启动时自动加载到数据库（如不存在）：

```json
[
  {
    "title": "Euler Finance 闪电贷攻击",
    "description": "2023年3月 Euler Finance 被攻击，损失约 1.97 亿美元",
    "category": "flash_loan",
    "tags": ["闪电贷", "Aave V2", "DeFi"],
    "chain_id": 1,
    "tx_hash": "0xcc...模拟",
    "exploiter_address": "0xabc...",
    "alert_data": {
      "chain_id": 1,
      "tx_hash": "0xcc...",
      "to_address": "0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9",
      "input_data": "0x0906f8c8...",
      "value": "197000000000000000000",
      "gas_price": 35000000000,
      "gas_used": 650000,
      "from_address": "0xabc...",
      "block_number": 16866000
    },
    "expected_severity": "CRITICAL",
    "expected_labels": ["LARGE_FLASH_LOAN_ATTACK"],
    "expected_min_score": 80,
    "source": "preset",
    "tx_explorer_url": "https://etherscan.io/tx/0xcc..."
  },
  {
    "title": "异常 Gas 价格操纵",
    "description": "交易 Gas 费用异常高，疑似抢跑或 Gas 价格操纵",
    "category": "gas_manipulation",
    "tags": ["Gas", "MEV"],
    "chain_id": 1,
    "tx_hash": "0xgas...模拟",
    "alert_data": {
      "chain_id": 1,
      "tx_hash": "0xgas...",
      "to_address": "0xdef...",
      "gas_price": 800000000000,
      "gas_used": 300000,
      "value": "0",
      "from_address": "0xmev..."
    },
    "expected_severity": "HIGH",
    "expected_labels": ["high_gas"],
    "expected_min_score": 50,
    "source": "preset"
  },
  {
    "title": "可疑 ERC20 无限授权",
    "description": "用户向未知合约授予无限 Token 授权",
    "category": "approval_phishing",
    "tags": ["授权", "钓鱼", "ERC20"],
    "chain_id": 1,
    "tx_hash": "0xapr...模拟",
    "alert_data": {
      "chain_id": 1,
      "tx_hash": "0xapr...",
      "to_address": "0xmalicious_contract...",
      "input_data": "0x095ea7b3ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
      "value": "0",
      "from_address": "0xvictim...",
      "gas_price": 25000000000,
      "gas_used": 50000
    },
    "expected_severity": "MEDIUM",
    "expected_labels": ["suspicious_approval"],
    "expected_min_score": 40,
    "source": "preset"
  }
]
```

---

## 7. 前端设计

### 7.1 新增页面 — 知识库管理

**路由：** `/knowledge-base`

**功能：**

| 区域 | 说明 |
|------|------|
| 顶部搜索栏 | 关键词搜索 + 分类下拉筛选 + 链 ID 筛选 |
| 数据表格 | 列出样本：标题、分类、链 ID、交易哈希、标签、预期严重级别、创建时间 |
| 操作列 | 查看详情、编辑、删除、选择用于测试 |
| 批量操作 | 批量导入（JSON）、批量导出、批量删除 |
| 新建按钮 | 弹出表单，填写标题/描述/分类/标签/alert_data（支持 JSON 编辑器） |

### 7.2 规则链编辑器集成

**在规则链编辑器中新增"测试运行"入口：**

```
┌──────────────────────────────────────────┐
│  规则链编辑器                    [测试运行]│
│  ┌──────────────────────────────────────┐│
│  │  点击"测试运行"后弹出测试面板:       ││
│  │                                      ││
│  │  ┌─ 选择测试数据 ──────────────────┐ ││
│  │  │ ○ 从知识库选择 (多选)           │ ││
│  │  │   [搜索...] [勾选样本1] [勾选2] │ ││
│  │  │ ○ 手动输入 JSON                │ ││
│  │  │   { "chain_id": 1, ... }       │ ││
│  │  └────────────────────────────────┘ ││
│  │                                      ││
│  │  [▶ 执行测试]                        ││
│  │                                      ││
│  │  ┌─ 执行结果 ─────────────────────┐ ││
│  │  │ 样本1: Euler 闪电贷             │ ││
│  │  │   最终评分: 95  严重级别: CRITICAL│ ││
│  │  │   ✅ 匹配预期                   │ ││
│  │  │   节点执行详情:                 │ ││
│  │  │   ├─ 告警触发器    ✓ 0ms       │ ││
│  │  │   ├─ 闪电贷检测    ✓ 12ms  95分│ ││
│  │  │   ├─ Gas价格检测   ✓ 8ms   30分│ ││
│  │  │   └─ Webhook通知   (模拟) 1ms  │ ││
│  │  └────────────────────────────────┘ ││
│  └──────────────────────────────────────┘│
└──────────────────────────────────────────┘
```

### 7.3 前端新增文件

```
frontend/src/
  views/
    KnowledgeBase.vue           # 知识库管理页面
  components/
    knowledge/
      SampleTable.vue           # 样本列表表格
      SampleForm.vue            # 创建/编辑表单
      ImportExport.vue          # 导入导出对话框
    editor/
      TestRunPanel.vue          # 测试运行面板
      TestRunResult.vue         # 测试结果展示
      SampleSelector.vue        # 知识库样本选择器
  api/
    knowledgeBase.js            # 知识库 API 封装
  stores/
    knowledgeBase.js            # Pinia store
```

---

## 8. 开发步骤（建议顺序）

### Phase 1 — 后端核心（优先级最高）

| 步骤 | 任务 | 涉及文件 |
|------|------|----------|
| 1 | 新增 `KnowledgeBaseDB` 数据库模型 | `database/models.py` |
| 2 | 创建知识库 CRUD 路由 | `routers/knowledge_base/router.py`（新建） |
| 3 | 注册路由到 `main.py` | `main.py` |
| 4 | 在 `ExecutionContext` 中添加 `dry_run` 字段 | `engine/context.py` |
| 5 | Action 节点支持 dry_run 模式 | `nodes/actions/base.py` |
| 6 | 新增 test-run 端点 | `routers/rule_chain/router.py` |
| 7 | 创建预置样本数据 | `data/sample_alerts.json` |
| 8 | 启动时自动加载预置数据 | `main.py` 或独立 seed 脚本 |

### Phase 2 — 后端测试

| 步骤 | 任务 |
|------|------|
| 9 | 编写知识库 CRUD 测试 |
| 10 | 编写 test-run 端点测试（验证 dry_run 模式） |
| 11 | 编写预期匹配验证测试 |

### Phase 3 — 前端开发

| 步骤 | 任务 |
|------|------|
| 12 | 创建知识库 API 封装 + Pinia store |
| 13 | 实现知识库管理页面（列表/搜索/表单） |
| 14 | 实现导入/导出功能 |
| 15 | 在规则链编辑器中集成测试面板 |
| 16 | 实现测试结果可视化展示 |

### Phase 4 — 联调与优化

| 步骤 | 任务 |
|------|------|
| 17 | 前后端联调 |
| 18 | 补充更多预置样本（覆盖各检测器场景） |
| 19 | 更新 README 文档 |

---

## 9. 关键设计决策

| 决策点 | 方案 | 理由 |
|--------|------|------|
| 存储方式 | SQLite 表存储，不用文件系统 | 与现有 AlertDB / RuleChainDB 架构一致，支持查询索引 |
| 测试执行 | 复用现有 ChainExecutor，新增 dry_run 标志 | 不重复造轮子，保持引擎单一职责 |
| 预置数据 | JSON 文件 + 启动时 seed | 便于版本管理，用户也可自定义 |
| alert_data 格式 | JSON dict，与 AlertTrigger 输入格式一致 | 无需额外适配层，样本可直接喂入规则链 |
| 导入导出 | JSON 格式 | 灵活、易读、支持嵌套结构，且与内部存储格式一致 |
| 前端集成 | 规则链编辑器内嵌测试面板 | 用户编辑规则时即可测试，无需切换页面 |
