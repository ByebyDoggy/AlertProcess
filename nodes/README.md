# nodes 模块说明

`nodes/` 是 AlertProcessor 规则链的节点库。规则链引擎通过节点注册表按 `node_type` 实例化节点，节点之间通过统一的 `NodeOutput.context` 传递交易上下文、检测结果和动作执行结果。以后修改本目录下任何模块前，应先阅读本文，确认新增或修改的节点遵守现有注册、输入输出、上下文和测试约定。

## 模块定位

本模块负责提供规则链中可编排的节点类型：

- 入口节点：把外部告警或交易数据转成标准上下文。
- Provider 节点：补充链上 trace、日志解析、地址标签、价格等上下文字段。
- Detector 节点：读取上下文并输出风险评分、标签、严重级别和 evidence。
- Logic / scoring / memory / temporal / storage 节点：组合、缓存、跨时间关联或持久化中间状态。
- Action 节点：执行 Webhook、Telegram、数据库更新等终端动作。

规则链的执行逻辑不在 `nodes/` 内，而在 `engine/` 中；`nodes/` 只定义节点协议、节点实现和注册入口。

## 核心抽象

关键文件：

- `base.py`：定义所有节点共享的基础设施。
  - `PortType` / `PortDef`：描述节点输入输出端口。
  - `NodeCategory`：节点分类，对应前端节点面板分组。
  - `NodeOutput`：引擎内部统一运行时输出。
  - `NodeOutputMixin`：节点 `process()` 返回模型的通用字段。
  - `BaseNode`：所有节点的抽象基类。
  - `NodeRegistry`：节点类型注册、实例化、自动发现、schema/docs 导出。
- `models.py`：定义规则链中传递的标准数据模型。
  - `TransactionContext`：交易上下文基础模型。
  - `DetectorResult`：Detector 的检测结果模型。
- `__init__.py`：初始化节点注册表，优先自动发现，失败时降级到手动导入列表。

所有节点类都应有稳定的：

- `name`：节点类型名，规则链中通过它引用节点。
- `label` / `description`：前端和文档展示信息。
- `category`：节点分类。
- `get_inputs()` / `get_outputs()`：端口定义。
- `execute()`：引擎调用入口，通常由类别基类提供。

## 标准上下文模型

`TransactionContext` 是 Provider 和 Detector 的标准输入。它包含固定交易字段：

- `chain_id`
- `tx_hash`
- `block_number`
- `from_address`
- `to_address`
- `value`
- `gas_price`
- `gas_used`
- `input_data`
- `timestamp`
- `logs`

非标准字段会通过 `TransactionContext.from_dict()` 放入 `extra`，再由 `to_dict()` 展开回顶层。因此：

- Provider 注入的新字段应写入 `tx_context.extra`。
- Detector 读取 Provider 结果时应优先从 `tx_context.extra` 读取。
- 离线 fixture 或测试里包含 `transfers`、`trace_calls`、`top_profit_address` 等非标准字段时，应使用 `DetectorInputMixin.from_dict(...)` 或 `TransactionContext.from_dict(...)`，避免自定义字段被 Pydantic 丢弃。

常见 `extra` 字段包括：

- `trace_calls`
- `transfers`
- `parsed_transfers`
- `parsed_swaps`
- `token_prices`
- `token_decimals`
- `address_labels`
- `top_profit_address`
- `top_loss_address`
- detector-specific evidence inputs

## 执行流

规则链由 `ChainExecutor` 执行，节点侧需要理解以下运行语义：

1. 执行器通过 `NodeRegistry.create(node_type, node_id, config)` 实例化节点。
2. 执行器按拓扑层级并发执行节点。
3. 节点收到全局 `alert_data` 和上游 `NodeOutput` 列表。
4. 类别基类通常会把全局 context 与上游 `context` 合并。
5. Provider 将 `fetch()` 结果合入 `TransactionContext.extra`。
6. Detector 调用 `process(tx_context)` 生成评分、标签、严重级别和 detection。
7. Action 调用 `process(input)` 执行副作用；dry-run 时由 `BaseAction` 直接返回模拟结果，不应触发真实外部请求。
8. true/false 端口路由由执行器根据上游 `passed` 判断；节点自身仍只返回一个 `NodeOutput`。

## 目录职责

- `triggers/`：规则链入口。负责把外部输入整理成上下文。
- `providers/`：链内 Provider 节点。推荐新增 Provider 放在这里。
- `detectors/`：标准检测器。负责将上下文转成风险信号。
- `detectors/protocol/`：协议攻击类 trace/call-stack 检测器。
- `actions/`：终端副作用节点。必须尊重 dry-run。
- `logic/`：上下文或检测结果组合、条件逻辑。
- `memory/`：规则链记忆能力。
- `temporal/`：跨交易、跨时间窗口关联能力。
- `storage/`：外部存储或缓存节点。
- `scripting/`：脚本执行节点与沙箱。
- `context/`：旧式上下文 Provider / resolver 辅助能力。新增 Provider 默认不要放这里，除非维护兼容逻辑。
- `primitives/`：基础解析或低层构件。

## 选择器与函数名识别约定

实际攻击交易中，很多合约没有公开 ABI、函数名数据库也可能缺失或错误。Detector 不应把“识别到某个专用函数名 / 专用 selector”作为核心触发前提。新增或修改检测器时，应优先使用可泛化的行为特征：

- 资金流：资产净流入/流出、top profit/top loss、转账路径、金额阈值、价值估算。
- 调用流结构：调用方向、调用深度、重复模式、callback 关系、caller/callee 角色、CREATE 临时合约。
- 协议角色证据：地址标签、Provider 归一化结果、trace 结构、事件日志、余额变化。
- 多信号组合：用资金流 + 调用流 + 上下文证据共同判断，避免单点 selector 命中。

允许硬编码的 selector 应限于极通用、跨协议稳定、语义明确的基础接口，例如：

- ERC20 / ERC721 / ERC1155 等标准接口中的 `transfer`、`transferFrom`、`approve`、`balanceOf`。
- DEX Pair 等事实标准中高度稳定的 `swap`、`getReserves`，且最好只作为 LP / Pair 证据或加权信号。
- 已成为通用模式的基础操作 selector，但必须在 detector 注释、文档或 evidence 中说明它只是辅助证据还是硬触发条件。

不建议硬编码：

- 单一项目、单一协议、单一攻击交易中的业务函数 selector。
- 从某次 Phalcon / explorer 页面看到的非标准函数名。
- 只有函数名、没有资金流或调用结构佐证的模式识别。
- 将未知 selector 直接等同于恶意行为。

如果必须使用非通用 selector，应优先放到可配置签名库、Provider 输出或测试 fixture 中，并让 detector 以“可选加权信号”消费它，而不是把它写死为生产逻辑的唯一触发条件。

### Detector evidence 分层

Protocol / trace 类 detector 应按以下优先级组织证据和评分：

1. 主证据：资金流、余额变化、调用结构、callback / delegatecall / fanout、地址角色、临时合约、LP / vault / proxy 等可泛化行为证据。
2. 辅助证据：ERC20 `transfer` / `transferFrom` / `approve` / `balanceOf`、DEX Pair `swap` / `getReserves` 等跨协议稳定 selector，可参与加权或角色判断。
3. 调试或弱证据：协议/项目专用 selector、explorer 解析函数名、一次攻击样本里的业务函数名。此类证据可以进入 `evidence`、`labels` 或日志，但不应单独让 detector 通过阈值。

修改已有 detector 时，应优先加入 selector-only 回归测试：只命中专用 selector 但没有行为证据时不通过；缺少已知 selector 但行为证据充分时仍可通过。

## 新增 Detector 约定

新增检测器时：

1. 优先放在 `detectors/`；trace / protocol 类检测器放在 `detectors/protocol/`。
2. 继承 `BaseDetector`，复杂协议攻击可继承 `BaseProtocolAttackDetector`。
3. 定义 `name`、`label`、`description`、`icon`、`color`。
4. 如需配置，定义内部 `ConfigModel`，并继承 `DetectorConfigMixin`。
5. 输出模型继承或兼容 `DetectorOutputMixin`。
6. 实现 `process(tx_context: TransactionContext)`，不要覆写 `execute()`，除非确实需要改变通用执行语义。
7. 从 `tx_context.extra` 读取 Provider 注入字段；不要假设非标准字段在顶层属性中。
8. 返回字段应包含：
   - `score`
   - `passed`
   - `severity`
   - `labels`
   - `detection`
   - `logs`
9. `detection` 中应包含稳定、可测试的 `reason` 和 `evidence`。
10. 文件末尾或类装饰器必须注册到 `NodeRegistry`。
11. 若希望手动导入降级路径可用，还需要检查 `nodes/__init__.py` 的 `_REGISTRY_MODULES` 是否应加入新模块。
12. 同步添加单元测试；包含命中样本和至少一个误报控制样本。
13. 对已知攻击交易优先使用离线 fixture 回放，避免测试依赖外网。

Detector 不应：

- 在 import 阶段发起网络请求或重 IO。
- 重复实现已有 Provider 或其他 detector 的职责。
- 把单笔攻击地址硬编码进 production detector，除非检测器明确是黑名单类节点。
- 把非通用 selector 或 explorer 解析出的项目专用函数名作为核心触发条件。
- 只依赖 selector / 函数名命中，而缺少资金流、调用结构或角色证据交叉验证。
- 在 `process()` 中修改全局对象或其他节点输出。

## 新增 Provider 约定

新增 Provider 时：

1. 默认放在 `providers/`。
2. 继承 `BaseContextProviderNode`。
3. 声明 `provides`，说明会注入哪些 `extra` 字段。
4. 实现 `fetch(tx_context)`，返回要合入 `extra` 的 dict。
5. 不直接改写外部 `context`；让基类负责合并。
6. 对网络、RPC、第三方 API 调用做清晰的失败输出，避免让下游看到半结构化字段。
7. Provider 输出只补充上下文，不负责风险评分。

`context/` 下的旧式 resolver / decorator 更适合兼容已有逻辑。新增链内 Provider 不应优先使用旧模式。

## 新增 Action 约定

新增 Action 时：

1. 放在 `actions/`。
2. 继承 `BaseAction`。
3. 实现 `process(input: ActionInputMixin)`。
4. 副作用只允许发生在 `process()` 内。
5. 不要绕过 `BaseAction.execute()`，否则可能破坏 dry-run。
6. 输出 `ActionOutputMixin` 兼容字段，执行详情写入 `action_result`。
7. dry-run 下必须不发送真实 Webhook、Telegram、邮件、数据库写入或其他外部副作用。

## 注册与自动发现

节点可以通过以下方式注册：

- 模块导入时调用 `NodeRegistry.register(YourNode)`。
- 使用 `@NodeRegistry.register` 装饰器。

当前代码中两种方式都存在。新增节点建议保持同一文件内清晰注册，避免依赖隐式副作用之外的额外步骤。

`NodeRegistry.auto_discover("nodes")` 会导入 `nodes/` 下非私有、非 base 的模块。由于自动发现会触发模块顶层代码，节点模块的顶层逻辑应只包含：

- import
- 常量
- 模型/类定义
- 注册调用

不要在模块顶层执行网络访问、数据库连接、文件扫描或耗时初始化。

## 测试约定

修改或新增 `nodes/` 代码时，至少应覆盖：

- 节点注册测试：`NodeRegistry.get("node_name") is NodeClass`。
- 直接节点测试：构造输入模型，调用 `process()` 或 `execute()`。
- 对 Detector：命中样本、误报控制样本、关键 evidence 断言。
- 对 Provider：`fetch()` 返回字段和 `execute()` 合并到 context 的行为。
- 对 Action：正常执行和 dry-run 不触发副作用。
- 对规则链行为：必要时用 `ChainParser` + `ChainExecutor` 做最小链回放。

fixture 包含非标准字段时，应使用 `from_dict()` 构造上下文，保证字段进入 `extra`。

## 当前结构评估

当前 `nodes/` 的基础分层可以继续使用，暂不需要大规模拆分。主要原因：

- 基类边界明确：`BaseNode`、`BaseDetector`、`BaseContextProviderNode`、`BaseAction` 分工清晰。
- 执行器与节点库边界基本稳定。
- Provider、Detector、Action 的输入输出协议已经统一到 `TransactionContext` / `NodeOutput`。
- `detectors/protocol/` 已经为 trace/protocol 类检测提供了子领域拆分。

建议暂缓大拆，只做克制优化。

## 后续优化建议

1. 明确 Provider 新旧边界  
   `providers/` 与 `context/` 都能表达上下文补充能力。建议约定新增 Provider 一律使用 `providers/BaseContextProviderNode`，`context/` 只维护兼容逻辑。

2. 控制 detector 平铺增长  
   `detectors/` 下检测器数量持续增长。后续当某类 detector 达到多个文件并共享大量概念时，再按领域拆子目录，例如：
   - `detectors/economic/`
   - `detectors/protocol/`
   - `detectors/behavior/`

3. 收敛注册风格  
   当前存在文件末尾注册和装饰器注册两种风格。建议新增代码优先采用一种团队约定，并在 code review 中检查漏注册。

4. 谨慎修改 `BaseDetector.execute()`  
   该方法负责 context 合并、storage input 合并、threshold 统一判断和输出转换。修改它会影响所有检测器，必须有回归测试覆盖典型 detector。

5. 谨慎修改 `TransactionContext.from_dict()` / `to_dict()`  
   这是非标准字段进入 `extra` 并在规则链中继续传递的核心机制。任何改动都可能破坏离线 fixture、Provider 输出和 Detector 输入。

6. 文档与测试同步  
   如果新增节点类别、端口语义或上下文字段约定，应同步更新本文和对应测试。

## 修改前检查清单

在修改 `nodes/` 下文件前，先确认：

- 这次改动属于 Trigger、Provider、Detector、Logic、Action、Memory、Temporal、Storage 还是基础框架？
- 是否真的需要改基类？能否只改具体节点？
- 是否会影响 `TransactionContext.extra` 的字段传递？
- 是否会影响 dry-run 或外部副作用？
- 是否需要更新 `NodeRegistry` 注册或手动导入列表？
- 是否需要新增/更新单元测试和规则链回放测试？
- 是否新增了硬编码 selector / 函数名？如果有，它是否属于极通用基础接口，且不是唯一触发条件？
- 是否需要更新本文档？
