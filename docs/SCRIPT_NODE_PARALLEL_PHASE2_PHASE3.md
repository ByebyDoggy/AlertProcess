# ScriptNode Phase 2-3 并行开发计划

## 当前状态
- ✅ Phase 1 已完成并验证（ScriptSandbox + ScriptNode + ScriptContext 基础 API + 前端编辑器）
- ⚠️ Phase 2 部分完成（核心 API 已实现，缺模板库和高级工具函数）
- ❌ Phase 3 未开始（调试工具、集成测试、文档）

## 依赖关系分析

```
Phase 1 (已完成)
    ├─→ Team A3-Extended (后端高级 API) ✓ 无依赖，可立即开始
    ├─→ Team B2 (前端模板库) ✓ 无依赖，可立即开始
    ├─→ Team B3 (前端调试工具) ✓ 无依赖，可立即开始
    ├─→ Team C2 (集成测试) ✓ 无依赖，可立即开始
    └─→ Team C3 (文档和示例) ✓ 无依赖，可立即开始
```

**结论**: 所有剩余任务可以完全并行，无阻塞依赖。

---

## 并行开发方案

### 🔵 Team A3-Extended: ScriptContext 高级 API（后端）
**负责人**: Backend Developer  
**工作目录**: `engine/`, `tests/engine/`  
**预计时间**: 2-3 小时

#### 任务清单
- [ ] 实现 `get_balance_changes()` - 余额变化追踪
- [ ] 实现 `calculate_price_impact()` - 价格影响计算
- [ ] 实现 `detect_reentrancy()` - 重入检测工具
- [ ] 添加缓存机制（避免重复计算）
- [ ] 编写单元测试（`tests/engine/test_script_context_advanced.py`）
- [ ] 更新 `engine/script_context.py` 文档字符串

#### 输出文件
- `engine/script_context.py` (扩展)
- `tests/engine/test_script_context_advanced.py` (新增)

#### 验收标准
- 新增 API 单元测试通过
- 缓存机制有效（性能提升 > 30%）
- 文档字符串完整

---

### 🟢 Team B2: 脚本模板库（前端）
**负责人**: Frontend Developer  
**工作目录**: `frontend/src/components/templates/`, `frontend/src/views/`  
**预计时间**: 3-4 小时

#### 任务清单
- [ ] 创建 `TemplateLibrary.vue` 组件
  - 模板分类（检测器/过滤器/转换器）
  - 模板搜索和预览
  - 模板导入功能
- [ ] 创建常用模板（JSON 格式）
  - Flash Loan 检测模板
  - 价格操纵检测模板
  - 资金流向分析模板
  - ROI 计算模板
  - 重入攻击检测模板
  - 权限提升检测模板
- [ ] 集成到 `ScriptEditor.vue`（添加"从模板导入"按钮）
- [ ] 添加模板库演示路由 `/template-library-demo`

#### 输出文件
- `frontend/src/components/templates/TemplateLibrary.vue` (新增)
- `frontend/src/data/scriptTemplates.json` (新增)
- `frontend/src/components/editor/ScriptEditor.vue` (修改)
- `frontend/src/router.js` (修改)

#### 验收标准
- 模板库 UI 可用（搜索、预览、导入）
- 至少 6 个常用模板
- 模板可一键导入到编辑器

---

### 🟡 Team B3: 调试工具（前端）
**负责人**: Frontend Developer  
**工作目录**: `frontend/src/components/debug/`, `frontend/src/views/`  
**预计时间**: 3-4 小时

#### 任务清单
- [ ] 创建 `DebugPanel.vue` 组件
  - 日志查看器（显示脚本 print 输出）
  - 变量查看器（显示 result/score/labels/ctx）
  - 执行时间统计
  - 错误堆栈显示
- [ ] 创建 `PerformanceProfiler.vue` 组件
  - 脚本执行时间图表
  - 内存使用统计
  - API 调用次数统计
- [ ] 集成到 `ScriptEditorDemo.vue`（添加调试面板）
- [ ] 添加调试工具演示路由 `/debug-panel-demo`

#### 输出文件
- `frontend/src/components/debug/DebugPanel.vue` (新增)
- `frontend/src/components/debug/PerformanceProfiler.vue` (新增)
- `frontend/src/views/ScriptEditorDemo.vue` (修改)
- `frontend/src/router.js` (修改)

#### 验收标准
- 调试面板可显示日志和变量
- 性能分析器可显示执行时间
- 错误堆栈清晰可读

---

### 🟠 Team C2: 集成测试（测试）
**负责人**: QA Engineer  
**工作目录**: `tests/integration/`  
**预计时间**: 2-3 小时

#### 任务清单
- [ ] 创建 `tests/integration/test_script_node_chain.py`
  - 测试完整规则链（包含 ScriptNode）
  - 测试多个 ScriptNode 串联
  - 测试 ScriptNode 与其他节点交互
- [ ] 创建 `tests/integration/test_script_performance.py`
  - 测试脚本执行时间（< 5s）
  - 测试内存使用（< 100MB）
  - 测试并发执行（10 个脚本同时运行）
- [ ] 创建 `tests/integration/test_script_security.py`
  - 测试沙箱隔离（尝试突破）
  - 测试资源限制（超时、内存）
  - 测试恶意脚本拦截
- [ ] 运行所有集成测试并生成报告

#### 输出文件
- `tests/integration/test_script_node_chain.py` (新增)
- `tests/integration/test_script_performance.py` (新增)
- `tests/integration/test_script_security.py` (新增)
- `tests/integration/test_report.md` (新增)

#### 验收标准
- 集成测试通过率 100%
- 性能测试达标（< 5s, < 100MB）
- 安全测试无漏洞

---

### 🔴 Team C3: 文档和示例（文档）
**负责人**: Technical Writer  
**工作目录**: `docs/`, `examples/scripts/`  
**预计时间**: 3-4 小时

#### 任务清单
- [ ] 编写 `docs/SCRIPT_CONTEXT_API_REFERENCE.md`
  - 完整 API 列表
  - 每个方法的参数、返回值、示例
  - 常见用例和最佳实践
- [ ] 创建示例脚本库（`examples/scripts/`）
  - `flash_loan_detector.py` - Flash Loan 检测
  - `price_manipulation_detector.py` - 价格操纵检测
  - `reentrancy_detector.py` - 重入攻击检测
  - `fund_flow_analyzer.py` - 资金流向分析
  - `roi_calculator.py` - ROI 计算
  - `access_control_checker.py` - 权限检查
  - `gas_anomaly_detector.py` - Gas 异常检测
  - `token_approval_monitor.py` - Token 授权监控
  - `swap_analyzer.py` - Swap 分析
  - `balance_change_tracker.py` - 余额变化追踪
- [ ] 编写 `docs/SCRIPT_NODE_BEST_PRACTICES.md`
  - 性能优化技巧
  - 安全编码规范
  - 常见错误和解决方案
  - 调试技巧

#### 输出文件
- `docs/SCRIPT_CONTEXT_API_REFERENCE.md` (新增)
- `docs/SCRIPT_NODE_BEST_PRACTICES.md` (新增)
- `examples/scripts/*.py` (新增 10+ 个示例)

#### 验收标准
- API 文档完整（覆盖所有方法）
- 至少 10 个示例脚本
- 最佳实践指南清晰易懂

---

## 执行计划

### 第一轮并行（2-4 小时）
```
同时启动 5 个团队：
├─ Team A3-Extended (后端高级 API)
├─ Team B2 (前端模板库)
├─ Team B3 (前端调试工具)
├─ Team C2 (集成测试)
└─ Team C3 (文档和示例)
```

### 验收和集成（1 小时）
- 运行所有单元测试和集成测试
- 前端构建验证
- Playwright 端到端验证
- 文档审查

### 最终提交（30 分钟）
- 更新 `docs/RULE_CHAIN_SCRIPT_NODE_DEVELOPMENT.md` 状态
- Git 提交（Phase 2-3 完成）
- 生成最终验收报告

---

## 团队协作规范

### 文件冲突避免
- **Team A3-Extended**: 只修改 `engine/script_context.py` 和 `tests/engine/`
- **Team B2**: 只修改 `frontend/src/components/templates/` 和 `frontend/src/data/`
- **Team B3**: 只修改 `frontend/src/components/debug/`
- **Team C2**: 只修改 `tests/integration/`
- **Team C3**: 只修改 `docs/` 和 `examples/`

### 共享文件处理
- `frontend/src/router.js`: Team B2 和 B3 都需要修改
  - **解决方案**: Team B2 先添加路由，Team B3 后添加（顺序执行）
- `frontend/src/components/editor/ScriptEditor.vue`: Team B2 需要修改
  - **解决方案**: Team B2 独占修改权

### 通信机制
- 每个团队完成后更新 TODO 状态
- 遇到阻塞问题立即报告
- 共享文件修改需要协调

---

## 预期成果

### 完成后状态
- ✅ Phase 1: 脚本节点基础（已完成）
- ✅ Phase 2: 脚本 API 和工具库（完成）
- ✅ Phase 3: 高级特性（完成）

### 功能清单
- ✅ ScriptSandbox 安全执行
- ✅ ScriptNode 规则链集成
- ✅ ScriptContext 完整 API（基础 + 高级）
- ✅ 前端脚本编辑器
- ✅ 前端模板库
- ✅ 前端调试工具
- ✅ 单元测试 + 集成测试
- ✅ 完整文档 + 示例脚本库

### 质量指标
- 测试覆盖率 > 85%
- 脚本执行时间 < 5s
- 内存使用 < 100MB
- 文档完整度 100%
- 示例脚本 > 10 个

---

## 风险和缓解

### 风险 1: 前端路由冲突
- **影响**: Team B2 和 B3 同时修改 `router.js`
- **缓解**: Team B2 先完成路由添加，Team B3 后添加

### 风险 2: API 变更影响模板
- **影响**: Team A3-Extended 修改 API 可能影响 Team B2 模板
- **缓解**: Team A3-Extended 只添加新 API，不修改现有 API

### 风险 3: 集成测试依赖前端组件
- **影响**: Team C2 可能需要前端组件完成
- **缓解**: Team C2 专注后端集成测试，前端测试由 Team B2/B3 负责

---

## 开始执行

准备好后，按以下顺序启动：

1. **立即启动（并行）**:
   - Team A3-Extended: 后端高级 API
   - Team C2: 集成测试
   - Team C3: 文档和示例

2. **稍后启动（顺序）**:
   - Team B2: 前端模板库（先修改 router.js）
   - Team B3: 前端调试工具（后修改 router.js）

预计总时间: **4-6 小时**（并行执行）
