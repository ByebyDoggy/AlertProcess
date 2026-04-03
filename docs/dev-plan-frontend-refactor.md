# 前端重构开发计划 - 适配新规则链引擎

> 状态：已完成
> 日期：2026-04-03

---

## 一、背景

### 1.1 后端引擎已完成的变更

后端规则链引擎已完成全面重构（`nodes/` + `engine/`），核心变化：

| 旧架构 (v1) | 新架构 (v2) | 说明 |
|---|---|---|
| `trigger` | `trigger` | 不变 |
| `detector` | `detector` | 输出从 boolean → score 0-100，端口从 `true/false` → `output` |
| `condition` | 拆分为 `comparator` + `logic` | 比较操作 → comparator，逻辑组合 → logic |
| `scorer` | `scorer` | 独立节点类型，支持多输入聚合 |
| `filter` | 合并到 `comparator` | 阈值/区间/正则匹配 |
| `notifier` | `action` | 统一为 action 节点（actionType 区分） |
| `action` | `action` | 合并到 action 节点 |

### 1.2 新的 6 类节点体系

```
Trigger ──→ Detector ──→ Comparator ──→ Logic ──→ Action
                │              │
                └──→ Scorer ───┘
```

**关键约束**：
- Comparator/Scorer 只接收 `score` 类型输出（来自 Detector、Scorer）
- Logic 只接收 `boolean` 类型输出（来自 Comparator、Logic）
- Action 可接收任意类型输入
- Scorer/Comparator/Logic 支持**多输入端口**（`input_0`, `input_1`, `input_2`...）
- Detector/Scorer 输出 `output` 端口（不再有 `true/false`），Comparator/Logic 输出 `true`/`false`

### 1.3 前端当前状态

| 项目 | 状态 |
|---|---|
| 框架 | Vue 3 + Pinia + Vue Router + Vite |
| UI | Tailwind CSS，自定义暗色主题（n8n 风格） |
| 画布 | 纯 DOM + SVG 手动实现（无第三方流程图库） |
| API 层 | `src/api.js`（fetch 封装） |
| 状态管理 | `src/stores/ruleChain.js`（单一大 store） |
| 节点类型定义 | `src/config.js`（硬编码 5 种旧类型） |

**现有代码的问题**：
1. `config.js` 中 NODE_TYPES 仍为旧的 5 种（trigger/detector/condition/action/notifier）
2. CanvasEditor 中端口渲染硬编码为 `true/false` 或单个 `input`，不支持多输入
3. NodeConfigEditor 中配置表单用大量 `v-if` 按 type 分支，耦合严重
4. 所有状态集中在单个 Pinia store（235 行），职责不清
5. `utils.js` 中 `getNodeOutputs` 硬编码了旧端口映射
6. 后端 API (`/schema/node-types`) 仍返回旧类型，未对接新 NodeRegistry

---

## 二、开发目标

### 2.1 核心目标

1. **完全重写前端**，适配新后端 6 类节点类型（trigger/detector/comparator/scorer/logic/action）
2. **解耦架构**：按职责拆分 store、提取可复用组件、引入组合式函数
3. **动态节点类型**：从后端 `NodeRegistry.get_schema_for_frontend()` 动态获取节点定义，前端仅作为 fallback
4. **多输入端口**：comparator / scorer / logic 支持动态添加/删除输入端口
5. **数据类型约束**：前端绘制连接时实时校验数据类型兼容性（与后端 `ALLOWED_TYPE_MAPPING` 对齐）
6. **可扩展配置面板**：基于 JSON Schema 动态渲染配置表单，而非硬编码每种节点类型

### 2.2 开放策略

不做任何预设限制。可以：
- 引入第三方流程图库（如 Vue Flow）替代手写 DOM + SVG
- 重写视觉风格和主题
- 重构 Pinia store 结构（拆分为多个 store）
- 新增页面/路由
- 重写任何现有组件
- 引入新的依赖库（UI 组件库、状态管理工具等）

**唯一原则**：结构清晰、高内聚低耦合、可维护可扩展。

---

## 三、架构设计

### 3.1 目录结构

```
frontend/src/
├── api/                        # API 层
│   ├── index.js                # 统一导出
│   ├── ruleChain.js            # 规则链 CRUD + 验证
│   └── nodeSchema.js           # 节点 Schema 动态加载
│
├── composables/                # 组合式函数（hooks）
│   ├── useNodeTypes.js         # 节点类型数据（动态加载 + fallback）
│   ├── useConnection.js        # 连线逻辑（拖拽、校验、创建）
│   ├── useDragDrop.js          # 画布拖拽（节点移动、drop 新节点）
│   └── useKeyboard.js          # 键盘快捷键
│
├── stores/                     # Pinia 状态管理
│   ├── chainEditor.js          # 编辑器状态（画布、选择、临时连线）
│   ├── chainData.js            # 链数据（CRUD、保存、验证）
│   └── nodeTypes.js            # 节点类型注册表（从 API 加载）
│
├── components/
│   ├── editor/                 # 画布编辑器相关
│   │   ├── Canvas.vue          # 主画布（节点 + 连线渲染）
│   │   ├── NodeCard.vue        # 单个节点卡片（header + ports + body）
│   │   ├── Edge.vue            # 单条连线（Bezier 曲线）
│   │   ├── Port.vue            # 端口圆点（输入/输出）
│   │   └── TempEdge.vue        # 临时拖拽连线
│   │
│   ├── palette/                # 节点面板
│   │   ├── NodePalette.vue     # 面板容器（分类 + 搜索）
│   │   └── PaletteItem.vue     # 可拖拽的节点条目
│   │
│   ├── config/                 # 配置面板
│   │   ├── NodeConfigPanel.vue # 配置面板容器
│   │   ├── SchemaForm.vue      # JSON Schema 驱动的动态表单
│   │   ├── PortManager.vue     # 多输入端口管理器（+/- 按钮）
│   │   └── EdgeInfoPanel.vue   # 连线信息面板
│   │
│   ├── layout/                 # 布局组件
│   │   ├── Header.vue          # 顶部栏（名称、描述、保存）
│   │   ├── Toolbar.vue         # 工具栏（验证、删除等）
│   │   └── Sidebar.vue         # 侧边栏（规则链列表 + 节点面板）
│   │
│   └── common/                 # 通用组件
│       ├── Toast.vue           # 全局 Toast 提示
│       ├── Modal.vue           # 模态框容器
│       ├── FormInput.vue       # 表单输入
│       ├── FormSelect.vue      # 表单下拉
│       └── FormTextarea.vue    # 表单文本域
│
├── views/
│   └── RuleChainEditor.vue     # 主页面（组合所有子组件）
│
├── config/                     # 前端本地配置
│   ├── nodeTypesFallback.js    # 节点类型 fallback 定义（后端不可用时）
│   └── connectionRules.js      # 数据类型兼容性矩阵
│
├── utils/
│   ├── geometry.js             # 画布几何计算（Bezier、端口位置）
│   ├── connection.js           # 连线合法性校验
│   └── helpers.js              # 通用工具（ID 生成、深拷贝等）
│
├── styles/
│   └── main.css                # 全局样式（Tailwind + 自定义暗色主题）
│
├── App.vue
├── main.js
└── router.js
```

### 3.2 状态管理拆分

将现有 235 行的单一大 store 拆分为 3 个职责清晰的 store：

**`stores/nodeTypes.js`** — 节点类型注册表
```
state:    nodeTypeList[], loading, fallback
actions:  fetchNodeTypes(), getByCategory(), getByType()
```

**`stores/chainData.js`** — 规则链 CRUD
```
state:    chains[], currentChainId, chainName, chainDescription, chainEnabled
          nodes[], edges[]
actions:  fetchChains(), loadChain(), createNew(), save(), deleteChain()
          addNode(), removeNode(), updateNode(), updateNodeConfig()
          addEdge(), removeEdge(), validate()
getters:  currentChain, isModified
```

**`stores/chainEditor.js`** — 编辑器 UI 状态
```
state:    selectedNodeId, selectedEdgeId
          showNodeConfig, showEdgeConfig
          connecting, tempLine, saving
actions:  selectNode(), selectEdge(), clearSelection()
          openNodeConfig(), closeNodeConfig()
          startConnection(), updateTempLine(), finishConnection()
```

### 3.3 节点类型动态加载策略

前端不硬编码节点类型，而是：

1. **应用启动时**从后端 `/rule-chain/schema/node-types` 加载所有节点定义
2. 后端 `NodeRegistry.get_schema_for_frontend()` 返回每个节点的 `inputs`、`outputs`、`config_schema`、`default_config`
3. 前端 `stores/nodeTypes.js` 存储完整节点定义列表
4. **Fallback**：如果 API 不可用，使用 `config/nodeTypesFallback.js` 中的本地定义
5. `NodePalette.vue`、`NodeCard.vue`、`NodeConfigPanel.vue` 均从 store 读取节点定义

### 3.4 数据类型兼容性

与后端 `nodes/base.py` 中的 `ALLOWED_TYPE_MAPPING` 完全对齐：

```js
// config/connectionRules.js
export const ALLOWED_TYPE_MAPPING = {
  'context':            ['context', 'any'],
  'detection_output':   ['detection_output', 'score_output', 'any'],
  'comparison_output':  ['comparison_output', 'any'],
  'score_output':       ['detection_output', 'score_output', 'any'],
  'logic_output':       ['logic_output', 'comparison_output', 'any'],
}
```

前端在用户拖拽连线时实时校验：
- 合法：正常 Bezier 曲线
- 不合法：红色虚线 + tooltip 提示原因

---

## 四、核心组件设计

### 4.1 Canvas.vue — 主画布

**职责**：渲染所有节点和连线，处理鼠标事件（拖拽、连线、选择）

关键设计点：
- **节点渲染**：从 `chainData.nodes` 遍历，每个节点渲染为 `<NodeCard>`
- **连线渲染**：从 `chainData.edges` 遍历，每条边渲染为 `<Edge>`
- **SVG 层**：连线使用 SVG `<path>` 绘制 Bezier 曲线
- **DOM 层**：节点使用绝对定位的 DOM 元素
- **多输入端口**：`NodeCard` 根据节点 `config.inputPorts` 数组动态渲染输入端口
- **缩放与平移**（可选增强）：使用 CSS transform 实现画布缩放/平移

### 4.2 NodeCard.vue — 节点卡片

**职责**：渲染单个节点（header + 端口 + 摘要）

```
┌──────────────────────────┐
│ 🟢 检测器     Gas 价格  │  ← header（icon + label + type badge）
├──────────────────────────┤
│ ● 输入                   │  ← 输入端口（左侧圆点）
│        评分 ●            │  ← 输出端口（右侧圆点）
├──────────────────────────┤
│ gas_price_detector       │  ← 配置摘要
└──────────────────────────┘
```

- 端口数量由 `nodeType.inputs` 和 `nodeType.outputs` 决定
- 多输入节点：`config.inputPorts: ['input_0', 'input_1', 'input_2']` 控制实际端口数
- 端口颜色由 `data_type` 决定（与连接兼容性矩阵关联）
- 选中状态、hover 效果、删除按钮

### 4.3 SchemaForm.vue — 动态配置表单

**职责**：基于 JSON Schema 动态渲染表单字段

不再为每种节点类型硬编码配置表单，而是：
1. 后端每个节点提供 `get_config_schema()` 返回 JSON Schema
2. `SchemaForm.vue` 接收 schema 和 model (v-model)，动态渲染表单控件
3. 支持的字段类型：`text`, `number`, `select`, `boolean`, `textarea`
4. 支持 `showWhen` 条件显隐（如选择 actionType=weighted 后显示权重配置）
5. 对于特殊情况（如多输入端口管理），使用独立的 `PortManager.vue`

### 4.4 NodePalette.vue — 节点面板

**职责**：展示可拖拽的节点列表，按 category 分组

```
┌─────────────────────┐
│ 🔍 搜索节点...       │
├─────────────────────┤
│ 输入                  │
│  ⚡ 告警触发器        │
├─────────────────────┤
│ 安全检测              │
│  ⛽ Gas 价格检测器    │
│  🪙 地址类型检测器    │
│  💰 闪贷检测器        │
│  ✅ 代币授权检测器    │
│  📊 代币异常检测器    │
│  🔗 地址图谱检测器    │
│  📅 地址年龄检测器    │
│  🏷️ ARKM 标签检测器   │
├─────────────────────┤
│ 比较                  │
│  📏 阈值比较器        │
│  📐 区间比较器        │
│  🔤 正则比较器        │
├─────────────────────┤
│ 评分                  │
│  📈 均值评分器        │
│  📊 极值评分器        │
│  ⚖️ 加权评分器        │
├─────────────────────┤
│ 逻辑                  │
│  ✅ AND 门            │
│  🔀 OR 门             │
├─────────────────────┤
│ 动作                  │
│  🚨 设置严重级别      │
│  🏷️ 添加标签          │
│  🪝 Webhook 通知      │
│  📱 Telegram 通知     │
│  💾 更新数据库        │
└─────────────────────┘
```

关键变化：**直接展示每个具体节点**（如"Gas 价格检测器"而非笼统的"检测器"），因为后端 NodeRegistry 已经注册了所有具体节点。用户拖入的不再是"检测器"再配置子类型，而是直接拖入具体节点。

### 4.5 PortManager.vue — 多输入端口管理

**职责**：在配置面板中管理支持多输入的节点的端口数量

```
┌──────────────────────────────┐
│ 输入端口                      │
│ ┌──────────────────────────┐ │
│ │ ● input_0 (Gas 价格)     │ │
│ │ ● input_1 (闪贷)         │ │
│ │ ● input_2 (代币授权)     │ │
│ └──────────────────────────┘ │
│ [+ 添加端口]                 │
└──────────────────────────────┘
```

- 仅在节点的 `inputs` 定义中有 `multi: true` 的端口时显示
- 已连接的端口不可删除（需先断开连线）
- 添加端口时自动递增 key（`input_3`, `input_4`...）
- 保存时将端口列表写入 `node.config.inputPorts`

---

## 五、后端 API 适配

### 5.1 需要更新的后端 API

当前后端 `routers/rule_chain/router.py` 中的 `/schema/node-types` 仍返回旧类型定义。需要新增端点对接新 NodeRegistry：

```python
# 新增端点
GET /rule-chain/schema/nodes
# 返回 NodeRegistry.get_schema_for_frontend() 的结果

# 保留旧端点向后兼容
GET /rule-chain/schema/node-types  # 旧版，可逐步废弃
GET /rule-chain/schema/detectors   # 旧版，可逐步废弃
```

### 5.2 Edge 模型更新

当前 `RuleEdge` 缺少 `sourcePort` / `targetPort` 字段，需要补充：

```python
class RuleEdge(BaseModel):
    id: str
    source: str
    source_port: str = "output"   # 新增
    target: str
    target_port: str = "input"    # 新增
    label: str = ""
```

### 5.3 前端 API 层

```js
// api/nodeSchema.js
export async function fetchNodeTypes() {
  return request('/rule-chain/schema/nodes')
}

// api/ruleChain.js — 保存时携带端口信息
// node: { id, type, label, config, position }
// edge: { id, source, sourcePort, target, targetPort, label }
```

---

## 六、开发里程碑

### M1：项目骨架 + 基础设施（预计半天）

- [ ] 按新目录结构创建文件
- [ ] 拆分 Pinia stores（nodeTypes / chainData / chainEditor）
- [ ] 实现 `config/nodeTypesFallback.js` 和 `config/connectionRules.js`
- [ ] 实现 `utils/` 工具函数
- [ ] 提取 `composables/` 组合式函数
- [ ] 实现 `common/` 通用组件（Toast、Modal、FormInput 等）
- [ ] 更新后端 API（新增 `/schema/nodes` 端点 + Edge 模型补充端口字段）

### M2：画布编辑器（预计 1 天）

- [ ] 实现 `Canvas.vue`：SVG 连线层 + DOM 节点层
- [ ] 实现 `NodeCard.vue`：动态端口渲染、选中/hover 效果
- [ ] 实现 `Edge.vue`：Bezier 曲线渲染、选中/颜色区分
- [ ] 实现 `Port.vue`：端口圆点、hover 放大效果
- [ ] 实现 `TempEdge.vue`：拖拽连线实时预览
- [ ] 实现 `composables/useConnection.js`：连线合法性校验
- [ ] 实现 `composables/useDragDrop.js`：节点拖拽 + 面板拖入
- [ ] 数据类型校验：不兼容连接显示红色虚线

### M3：节点面板 + 配置面板（预计 1 天）

- [ ] 实现 `NodePalette.vue` + `PaletteItem.vue`：按 category 分组、搜索
- [ ] 实现 `NodeConfigPanel.vue`：动态配置表单容器
- [ ] 实现 `SchemaForm.vue`：JSON Schema 驱动的表单渲染
- [ ] 实现 `PortManager.vue`：多输入端口管理 UI
- [ ] 实现 `EdgeInfoPanel.vue`：连线信息面板

### M4：布局 + 路由 + 集成（预计半天）

- [ ] 实现 `layout/` 组件（Header、Toolbar、Sidebar）
- [ ] 重写 `RuleChainEditor.vue`：组合所有子组件
- [ ] 更新 `router.js`（按需新增路由）
- [ ] 实现 `composables/useKeyboard.js`：快捷键（Ctrl+S、Delete、Escape）
- [ ] 端到端测试：从后端加载节点类型 → 拖拽创建完整规则链 → 保存 → 加载
- [ ] 清理旧文件和旧代码

---

## 七、风险与注意事项

| 风险 | 说明 | 应对 |
|---|---|---|
| 后端 API 未更新 | `/schema/node-types` 仍返回旧类型，Edge 缺少端口字段 | M1 阶段先更新后端 API，再开发前端 |
| 旧数据库规则链 | 已有规则链配置使用旧节点类型 | 数据库中的旧规则链需清空或手动迁移 |
| 多输入端口连线冲突 | 同一目标端口被多次连线 | addEdge 时按 targetPort 去重检查 |
| 画布性能 | 大量节点和连线时的渲染 | 节点规模 < 50 应无问题；如需优化可考虑虚拟化 |
| JSON Schema 复杂度 | 后端 get_config_schema() 可能包含复杂类型 | SchemaForm 逐步支持，先覆盖基础类型 |

---

> 请审核以上计划，确认后开始 M1 开发。
