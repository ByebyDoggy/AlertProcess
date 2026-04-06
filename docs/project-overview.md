# AlertProcessor 项目概览

> **最后更新**: 2026-04-06
> **当前分支**: `260330-refactor-migrate-from-processor-to-detector`
> **项目定位**: 区块链安全告警处理与分析平台

---

## 一、项目架构总览

```
AlertProcessor/
├── main.py                    # FastAPI 入口，启动服务
├── config/                    # 配置管理 (pydantic-settings)
├── models/                    # 核心数据模型 (Pydantic)
├── database/                  # SQLAlchemy 数据库层
├── routers/                   # API 路由层
│   ├── alert/                 # 告警接收 Webhook
│   ├── detectors/             # 交易追踪分析 API
│   ├── knowledge_base/        # 知识库 CRUD
│   └── rule_chain/            # 规则链引擎 API
├── detectors/                 # 检测器模块（交易分析核心）
│   ├── trace/                 # 追踪引擎 (analyzer, provider, signature_db)
│   └── trace/behaviors/       # 行为检测子模块
├── nodes/                     # 规则链节点系统
│   ├── triggers/              # 触发器节点
│   ├── detectors/             # 检测器节点 (9种)
│   ├── comparators/           # 比较器节点
│   ├── scorers/               # 评分器节点
│   ├── logic/                 # 逻辑门节点
│   └── actions/               # 动作执行节点
├── engine/                    # 规则链执行引擎 (parser, executor, validator, context)
├── data_providers/            # 数据提供者抽象层
├── frontend/                  # Vue 3 前端应用
│   └── src/
│       ├── api/               # Axios API 封装
│       ├── components/        # Vue 组件库
│       │   ├── analysis/      # 分析面板 (FundFlow, BalanceChanges, Behavior 等)
│       │   ├── editor/        # 规则链编辑器 (Canvas, NodeCard, Edge)
│       │   ├── config/        # 配置面板
│       │   ├── knowledge/     # 知识库组件
│       │   ├── layout/        # 布局组件
│       │   └── palette/       # 节点面板
│       ├── views/             # 页面视图
│       ├── stores/            # Pinia 状态管理
│       ├── composables/       # 组合式函数
│       ├── utils/             # 工具函数
│       └── config/            # 前端配置
├── tests/                     # 测试套件 (pytest)
├── data/                      # 运行时数据与样本
└── docs/                      # 项目文档
    ├── alert-knowledge-base.md
    ├── dev-plan-frontend-refactor.md
    ├── dev-plan-rule-chain-engine.md
    └── dev-plan-trace-analysis.md
```

---

## 二、技术栈

### 后端

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.13 (Docker) / 3.11 (本地) | 运行时 |
| FastAPI | ~0.123.2 | Web 框架 |
| Uvicorn | ~0.38.0 | ASGI 服务器 |
| Pydantic | ~2.12.5 | 数据验证 |
| SQLAlchemy | - | ORM |
| pydantic-settings | - | 配置管理 |
| Web3.py (web3) | - | 链上交互 |
| Moralis | - | 链上数据源 |
| arkm-client | - | ARKM 标签数据 |
| httpx | - | HTTP 客户端 |

### 前端

| 技术 | 版本 | 用途 |
|------|------|------|
| Vue | ^3.5.13 | UI 框架 (Composition API) |
| Vite | ^6.0.0 | 构建工具 |
| Vue Router | ^4.5.0 | 路由管理 |
| Pinia | ^2.3.0 | 状态管理 |
| Axios | ^1.7.0 | HTTP 请求 |
| Chart.js | ^4.4.0 | 图表库 |
| vue-chartjs | ^5.3.0 | Vue Chart.js 封装 |
| @vueuse/core | ^12.0.0 | 组合式工具集 |
| Tailwind CSS | ^3.4.0 | 样式框架 |

### 基础设施

| 技术 | 用途 |
|------|------|
| Docker Compose | 容器编排 (backend:8000 + frontend:80) |
| Nginx (Alpine) | 前端静态文件服务 |
| SQLite | 数据库 (alerts.db) |
| pytest | 测试框架 |

---

## 三、后端 API 接口

### 3.1 告警模块 (`/alert`)
- **Webhook 接收**: 接收外部告警推送
- 触发规则链检测流程

### 3.2 交易追踪分析 (`/detectors` 或 `/trace`)
- `POST /trace/analyze` — 对交易哈希进行深度链路分析
- 返回结构化数据：调用树、资金流向、余额变化、行为标签、签名识别
- 支持多链 (ETH/BSC/Polygon)

**核心分析能力**:
- **调用树重建**: 解码函数签名，还原完整调用路径
- **资金流向图**: ETH/ERC20 转移追踪，纯 SVG 有向图渲染
- **行为检测**: Flash Loan 检测、Tornado Cash 交互等
- **协议识别**: Uniswap/Aave/Compound/Weth 等主流协议签名库

### 3.3 知识库 (`/knowledge-base`)
- 历史告警样本的增删改查
- 支持 JSON 导入/导出
- 预置样本自动加载 (startup seed)

### 3.4 规则链 (`/rule-chain`)
- 规则定义的 CRUD 管理
- 规则测试运行接口
- 节点 schema 动态查询

### 3.5 其他
- `GET /api/health` — 健康检查端点

---

## 四、核心业务模块详解

### 4.1 规则链引擎 (`engine/` + `nodes/`)

采用**可视化节点编排**的规则检测系统:

**节点类型体系**:
- **Triggers(触发器)**: AlertTrigger — 接收告警输入
- **Detectors(检测器)**: 9 种检测节点
  - `address_age` — 地址年龄检测
  - `address_graph` — 地址图谱分析
  - `address_type` — 地址类型分类 (EOA/Contract)
  - `arkm_label` — ARKM 标签匹配
  - `flash_loan` — 闪电贷检测
  - `gas_price` — Gas 价格异常
  - `token_anomaly` — 代币异常
  - `token_approval` — 代币授权风险
- **Comparators(比较器)**: Range / Regex / Threshold
- **Scorers(评分器)**: Average / Constant / MinMax / Weighted
- **Logic(逻辑门)**: AND / OR
- **Actions(动作)**:
  - `add_tag` — 添加标签
  - `set_severity` — 设置严重级别
  - `update_database` — 写入数据库
  - `notify_telegram` — Telegram 通知
  - `notify_webhook` — Webhook 回调

**执行引擎流程**: YAML/JSON 定义 → Parser 解析 → Validator 校验 → Context 构建 → Executor 执行

### 4.2 交易追踪引擎 (`detectors/trace/`)

| 文件 | 职责 |
|------|------|
| `analyzer.py` (32KB) | 主分析器，协调各模块完成交易分析 |
| `provider.py` (10KB) | 多源数据获取 (Alchemy RPC + Moralis + ARKM) |
| `signature_db.py` (23KB) | 函数签名数据库 (4 bytes selector → 名称) |
| `protocol_registry.py` (7KB) | 协议地址注册表 (Uniswap/Aave 等) |
| `models.py` (10KB) | 分析结果数据模型 |
| `behaviors/` | 行为检测插件 (Flash Loan, Tornado Cash 等) |

**数据源配置** (`config/model.py`):
```python
chainId_to_provider_url = {
    1: "https://eth-mainnet.g.alchemy.com/v2/",   # ETH
    56: "https://bsc-dataseed.binance.org/",       # BNB
    137: "https://polygon-rpc.com/",               # Polygon
}
```

---

## 五、前端架构

### 5.1 页面路由

| 路由 | 功能 | 核心组件 |
|------|------|----------|
| `/alert` | 告警列表与管理 | AlertList |
| `/rule-chain` | 规则链可视化编辑 | Canvas + NodePalette |
| `/knowledge-base` | 知识库管理 | SampleTable + SampleForm |
| `/trace/:txHash` | 交易深度分析 | FundFlowPanel + BehaviorPanel + CallTreeView + BalanceChangesPanel |

### 5.2 关键前端组件

#### 分析面板组 (`components/analysis/`)
- **`FundFlowPanel.vue`** (30KB) — **资金流向有向图**
  - 纯 SVG 实现，无第三方图库依赖
  - BFS 最长路径分层布局算法
  - 三次贝塞尔曲线边路由，支持并行边偏移
  - SVG `<marker>` 箭头渲染 (`markerUnits="userSpaceOnUse"`, 18×14px 固定尺寸)
  - BlockSec 风格交互: 悬浮高亮、双向激活、流动粒子动画 (CSS keyframe stroke-dashoffset)、发光滤镜
  - 4 层渲染顺序: Grid → Edges → Nodes → Labels
- **`CallTreeView.vue`** — 调用树可视化
- **`BalanceChangesPanel.vue`** — 余额变化表格
- **`BehaviorPanel.vue`** — 行为检测结果展示
- **`TokenFlowPanel.vue`** — ERC20 代币流转
- **`SignatureTag.vue`** — 函数签名标签

#### 规则链编辑器 (`components/editor/`)
- **`Canvas.vue`** — 画布容器，拖拽连线
- **`NodeCard.vue`** — 可拖拽节点卡片
- **`Edge.vue`** — 连线组件
- **`TestRunPanel.vue`** — 规则测试面板

### 5.3 前端开发命令

```bash
cd frontend
npm install          # 安装依赖
npm run dev          # 开发服务器 (Vite)
npm run build        # 生产构建 → dist/
npm run preview      # 预览构建产物
```

---

## 六、环境配置

### 6.1 本地开发

**前置条件**:
- Python 3.11+
- Node.js 18+
- 推荐: 创建虚拟环境 `.venv` 或 `venv`

**启动步骤**:
```bash
# 后端
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py          # 启动 FastAPI (http://localhost:8000)

# 前端 (另一个终端)
cd frontend
npm install
npm run dev            # 启动 Vite Dev Server (http://localhost:5173)
```

### 6.2 Docker 部署

```bash
docker-compose up --build -d
# backend → http://localhost:8000
# frontend → http://localhost:80
```

### 6.3 环境变量 (`.env`)

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `api_key` | API 密钥 | `default_secret_key_change_in_production` |
| `database_url` | SQLite 连接串 | `sqlite:///./alerts.db` |
| `moralis_api_key` | Moralis API Key | (空) |
| `arkm_cookie` | ARKM Cookie | (空) |
| `notify_webhook_url` | 通知回调 URL | (空) |
| `host` | 监听地址 | `0.0.0.0` |
| `port` | 监听端口 | `8000` |
| `reload` | 热重载 | `True` |

> Docker 环境下通过 `DOCKER_ENV=true` 跳过 `.env` 加载，使用环境变量注入。

---

## 七、当前开发进度

### 已完成功能

| 模块 | 状态 | 说明 |
|------|------|------|
| 告警 Webhook 接收 | ✅ | 基础接收与入库 |
| 规则链引擎 (Parser/Executor/Validator) | ✅ | 完整的节点编排执行系统 |
| 规则链可视化编辑器 | ✅ | Canvas 拖拽编辑 + 节点面板 |
| 交易追踪分析引擎 | ✅ | 多数据源、调用树、协议识别 |
| 资金流向图 (FundFlowPanel) | ✅ | SVG 有向图 + 箭头 + 流动动画 + 悬浮交互 |
| 调用树可视化 | ✅ | CallNode 递归渲染 |
| 余额变化面板 | ✅ | 表格展示 |
| 行为检测面板 | ✅ | Flash Loan / Tornado Cash 等 |
| 知识库 CRUD | ✅ | 含导入导出、预置样本 |
| 前后端 Docker 化 | ✅ | docker-compose 一键部署 |
| CORS & SPA Fallback | ✅ | 生产级部署就绪 |

### 当前分支重点: Processor → Detector 重构

正在将旧的 `processor` 架构迁移至新的 `detector` 架构:
- 分支名: `260330-refactor-migrate-from-processor-to-detector`
- 涉及文件: 大量 `routers/`, `frontend/src/` 下文件的修改
- 清理了各模块的 `__pycache__` 缓存文件

### 近期优化项 (FundFlowPanel)

1. **箭头渲染修复**: 从 `markerUnits="strokeWidth"` 改为 `"userSpaceOnUse"`，固定 18×14px 尺寸，marker ID 使用数字索引避免特殊字符问题
2. **交互体验升级**: 实现 BlockSec 风格悬浮高亮 — 节点↔边双向激活、流动粒子动画 (CSS keyframe)、发光滤镜、背景淡化
3. **布局优化**: COL_GAP=380px, ROW_GAP=120px, NODE_W=230×72px, ARROW_GAP=14px

---

## 八、项目规范

### Git 提交规范
- 提交前必须检查是否包含敏感数据 (API Key、Cookie 等)
- 不允许提交 `__pycache__/` 目录

### 测试
- 使用 pytest，配置文件: `pytest.ini`
- 测试目录: `tests/` (36 个测试文件)

### 代码风格
- 后端: Python 3.11+ 特性，类型注解 (typing + Pydantic)
- 前端: Vue 3 Composition API (Options API style setup), `<script setup>` 模式
- CSS: Tailwind CSS 工具类优先

---

## 九、快速上手指南 (给其他 AI)

### 如果需要修改后端逻辑
1. 找到对应的 `routers/` 路由文件或 `detectors/` 模块
2. 修改后运行 `python main.py` 验证
3. 确认虚拟环境已激活 (`.venv` 或 `venv`)

### 如果需要修改前端页面
1. 找到 `frontend/src/components/` 或 `views/` 下的组件
2. 修改后运行 `cd frontend && npm run build` 验证构建
3. 开发模式用 `npm run dev` 实时预览

### 如果需要修改资金流向图
- 核心文件: `frontend/src/components/analysis/FundFlowPanel.vue` (~637 行)
- 纯 SVG 实现，关键参数在 `<script>` 顶部常量区域
- 注意 marker 定义使用 `markerUnits="userSpaceOnUse"` 和数字 ID

### 如果需要添加新检测器
1. 在 `nodes/detectors/` 创建新类，继承 `base.py` 的基类
2. 在 `nodes/__init__.py` 注册到 `NodeRegistry`
3. 在前端 `palette/` 添加对应面板项

### 如果需要调试交易分析
- 示例数据: `temp/fundflow.example.json`
- 分析入口: `routers/detectors/trace_router.py` → `detectors/trace/analyzer.py`
