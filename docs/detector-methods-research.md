# 业界主流检测方法研究报告

> **整理日期**: 2026-04-17  
> **适用版本**: AlertProcessor 当前分支  
> **用途**: 为后续新检测器开发提供方法论参考

---

## 一、综述与项目现状

### 1.1 项目已实现的检测器

| 检测器 | 类型标识 | 当前评分逻辑 | 数据来源 |
|--------|----------|-------------|---------|
| Gas 价格检测 | `gas_price_detector` | USD成本线性插值，极端 → 95分 | alert_data |
| 闪电贷检测 | `flash_loan_detector` | 协议地址+方法签名匹配 | alert_data |
| 地址类型检测 | `address_type_detector` | null to/from 地址判断 | alert_data |
| ERC20 授权检测 | `token_approval_detector` | MAX_UINT256/setApprovalForAll | alert_data |
| 代币异常检测 | `token_anomaly_detector` | 大额转账 + 新代币活动 | alert_data |
| 地址关系图谱 | `address_graph_detector` | 已知黑名单/交易所地址匹配 | alert_data |
| 地址年龄检测 | `address_age_detector` | 区块差/时间差估算年龄 | Moralis API |
| ARKM 标签检测 | `arkm_label_detector` | 实体类型黑名单判断 | ARKM API |

### 1.2 行为检测层（detectors/trace/）

| 行为检测器 | 功能 |
|-----------|------|
| `FlashLoanBehavior` | 调用链级闪电贷模式识别 |
| `TokenFlowBehavior` | Token 流转追踪（发现 in/out 不匹配） |

---

## 二、业界四阶段攻击检测框架（Forta 参考体系）

Forta Network 的 Attack Detector 2.0 将链上攻击分为 **四个阶段**，是目前业界最主流的检测框架：

```
阶段1: 资金筹集 (Funding)
  ↓
阶段2: 准备 (Preparation)  
  ↓
阶段3: 利用/攻击 (Exploitation)
  ↓
阶段4: 后利用/洗钱 (Post-Exploitation)
```

> **对本项目的指导意义**: 当前项目检测器主要覆盖**阶段3（利用）**，阶段1、2、4的检测器空白较多，是扩展方向。

---

## 三、各攻击类型业界主流检测方法

### 3.1 闪电贷攻击（Flash Loan Attack）⚡

**业界主流方法：**

1. **调用树模式匹配**（已实现）
   - 检测同一交易内的 borrow → use → repay 结构
   - 匹配已知闪电贷协议地址（Aave/dYdX/Uniswap V3/Balancer）
   - 方法签名特征：`flashLoan`, `flash`, `flashLoanSimple`, `flashSwap`

2. **借还资金量分析**（增强方向）
   - 计算借款 USD 与还款 USD 的差额（=利润）
   - 若利润异常高（如 > $100K），提升风险分
   - 分析 token flow 的借还匹配度

3. **调用深度分析**
   - 闪电贷攻击通常调用深度 > 5，且包含跨协议跳转
   - 检测 delegatecall 滥用

4. **价格影响结合检测**
   - 闪电贷攻击常伴随大额 DEX swap（价格滑点 > 10%）
   - 结合 UniswapV2Swap/V3Swap 事件检测资产流向

**已有基础**: `nodes/detectors/flash_loan.py` + `detectors/trace/behaviors/flash_loan.py`  
**增强方向**: 利润计算、调用深度分析、借还匹配验证

---

### 3.2 价格操纵攻击（Price Manipulation / Oracle Attack）📉

**业界主流方法：**

1. **DEX 价格滑点检测**
   - 监控 Uniswap V2/V3 Swap 事件中的 `amountIn/amountOut` 比率
   - 单笔交易占流动性比例 > 5% 即为可疑
   - 交易前后代币价格变动 > 20% 触发警报

2. **Oracle 异常检测**
   - 检测 Chainlink/Tellor 价格更新事件中的异常偏差
   - Price feed 在极短时间内大幅偏离
   - 同一区块内多次价格更新

3. **套利路径检测**（Arbitrage Detection）
   - 同一交易内对同一代币对在多个 DEX 的买卖操作
   - 利用 call tree 分析资金路由路径
   - 典型特征：A→B→C→A 的代币流转环路

**推荐实现**: 基于调用树分析 DEX Swap 事件的 PriceManipulationDetector

**关键事件签名**:
```
UniswapV2Swap: 0xd78ad95f
UniswapV3Swap: 0xc42079f9
PancakeSwap: 0xd78ad95f (same as V2)
CurveTokenExchange: 0x8b3e96f2
```

---

### 3.3 重入攻击（Reentrancy Attack）🔄

**业界主流方法：**

1. **调用链重入模式检测**
   - 检测 call tree 中同一合约地址出现在非线性路径（A→B→A）
   - `trace_address` 路径分析：子调用中出现父调用的合约地址
   - 检测 `receive()`/`fallback()` 函数中的状态修改

2. **CEI 模式违反检测**（Check-Effects-Interactions）
   - 若合约先执行 transfer/call 再更新状态变量，为高风险模式
   - 依赖静态分析（需要合约字节码）

3. **Gas 限制分析**
   - 重入攻击通常伴随高 gas 消耗（需要执行多轮回调）
   - 检测 `call{gas: ...}` 的显式 gas 传递

4. **事件异常检测（运行时）**
   - 单交易内同一合约的相同事件触发超过阈值次数
   - 如 ERC20 Transfer 在同一交易内从同一合约发出 > 5 次

**推荐实现**: 基于 `detectors/trace/` 调用树分析的 `ReentrancyBehavior`

---

### 3.4 三明治攻击（Sandwich Attack / MEV）🥪

**业界主流方法：**

1. **区块内交易顺序分析**
   - 检测同一区块内，目标交易前后各有一笔来自同一地址的交易
   - 前置交易：买入目标代币（拉高价格）
   - 后置交易：卖出目标代币（获利）

2. **Gas 价格异常分析**
   - 夹击交易的 gas price 通常比被夹交易高/低微小幅度
   - 使用 Flashbots 捆绑的三明治攻击 gas price = 0

3. **MEV 捆绑检测**
   - 检测 `eth_sendBundle` 提交的捆绑交易
   - 分析 block builder（如 Flashbots/BloXroute）的特殊字段

4. **利润分析**
   - 计算夹击交易对的净利润（ETH/USD）
   - 利润来源地址集中度分析

**数据需求**: 需要区块内多笔交易的上下文（当前架构单笔交易，是扩展瓶颈）

---

### 3.5 权限/治理攻击（Governance / Access Control Attack）🔐

**业界主流方法：**

1. **权限变更事件监控**
   - `OwnershipTransferred(address,address)` 事件
   - `RoleGranted/Revoked(bytes32,address,address)` 事件（OpenZeppelin AccessControl）
   - `AdminChanged`, `BeaconUpgraded`, `Upgraded` 事件（代理合约升级）

2. **快照投票操纵检测**
   - 治理提案通过速度异常快（如在1个区块内通过）
   - 大额代币在投票前集中购买（闪电贷治理攻击）
   - 提案内容包含敏感操作（transfer/approve 大额资产）

3. **Timelock 绕过检测**
   - 检测 Timelock 的 `execute()` 被提前调用
   - 监控 `TimelockController.CallScheduled/CallExecuted` 事件

**关键事件签名**:
```
OwnershipTransferred: 0x8be0079c
RoleGranted: 0x2f878811
AdminChanged: 0x7e644d79
Upgraded: 0xbc7cd75a
```

---

### 3.6 混币器/洗钱检测（Mixer / Money Laundering）🌪

**业界主流方法：**

1. **Tornado Cash 交互检测**（已有基础）
   - 检测与 Tornado Cash 合约地址直接交互
   - 识别 `deposit(bytes32,uint256)`/`withdraw()` 方法调用
   - 分析资金路径中是否途经混币合约

2. **多跳资金追踪**
   - N度关系检测：从可疑地址出发，追踪 N 跳内是否触达混币合约
   - 典型路径：Exploit → 地址1 → 地址2 → Tornado Cash
   - 当前 ARKM 标签可识别一定程度的资金流路径

3. **链间桥接洗钱**
   - 跨链桥（Wormhole/LayerZero/Stargate）大额转出行为
   - 攻击后快速将资产转移至其他链的模式检测

4. **CEX 充值检测**
   - 攻击资金流入已知交易所热钱包地址
   - 结合 ARKM/Etherscan 标签库识别交易所地址

**推荐实现**: MixerInteractionDetector，基于地址关系图谱扩展

---

### 3.7 合约漏洞利用检测（Exploit Detection）💥

**业界主流方法：**

1. **合约部署 + 即时攻击模式**
   - 新合约创建后立即（同一区块或数区块内）执行大额操作
   - 创建合约携带 ETH（`value > 0` 的合约创建）
   - 非验证合约（unverified bytecode）执行关键函数

2. **大额铸造检测**
   - 单交易内 ERC20 `mint` 事件的铸造量异常大
   - 铸造后立即在 DEX 卖出（砸盘模式）

3. **余额异常变化检测**
   - 单笔交易导致协议合约 ETH/Token 余额减少 > X%
   - 使用 `eth_getBalance` 比较交易前后状态差

4. **授权耗尽攻击**（Approval Exploit）
   - 利用历史 Approve 的 allowance 大额转走资金
   - `transferFrom(victim, attacker, maxUint256)` 模式

**已有基础**: `token_approval_detector` 已检测授权，可增强耗尽场景

---

### 3.8 NFT/ERC1155 攻击检测（NFT Attacks）🎨

**业界主流方法：**

1. **批量铸造/抢购检测**
   - 单地址在极短时间内大量铸造 NFT（机器人行为）
   - `Transfer(0x0 → address)` 在同一交易内出现 > 20 次

2. **价格操纵（NFT Wash Trading）**
   - 同一地址买卖同一 NFT 多次（自买自卖刷量）
   - NFT 价格在短期内异常飙升

3. **Royalty 绕过攻击**
   - 检测使用非标准合约绕过版税支付

---

## 九、攻击事件分析驱动检测器开发（BlockSec 全量事件库）

> **整理日期**: 2026-05-07  
> **数据来源**: `blocksec_incidents.json`（由 `scripts/crawl_blocksec_incidents.py` 全量抓取）  
> **样本规模**: 269 incidents / 974 transactions / 952 usable tx hashes

### 9.1 样本选择方法

本轮不是从单个攻击事件反推检测器，而是先对 BlockSec 安全事件库做全量抓取，再按 root cause 聚类，选取高损失、特征明确、跨协议可泛化的代表样本。

本轮优先样本：

| Root Cause | 项目 | Loss | Chain | 代表 tx |
|-----------|------|------|-------|---------|
| Business Logic Flaw | Euler Finance | $200.00M | Ethereum | `0x3097830e9921e4063d334acb82f6a79374f76f0b1a8f857e89b89bc58df1f311` |
| Access Control Issue | Cork | $11.98M | Ethereum | `0xfd89cdd0be468a564dd525b222b728386d7c6780cf7b2f90d2b54493be09f64d` |
| Compromised Private Key | Bybit | $1.50B | Ethereum | `0xb61413c495fdad6114a7aa863a00b2e3c28945979a10885b12b30316ea9f072c` |
| Vulnerable Price Dependency | UwU Lend | $23.00M | Ethereum | `0x9235e0662e230bdfa94f56f4932fd09a95fea17e4b9b44a4f40a59449e216110` |
| Reentrancy | Curve | $60.00M | Ethereum | `0x006763dff653ecddfd3681181a29e7e6d6c2aaa7bafb27fe1376f3f7ce367c1e` |

这些样本的意义不在于“复刻攻击细节”，而在于抽取**不依赖协议私有函数签名**、尽量只依赖 logs / trace / transfer / address role 的通用检测信号。

### 9.2 数据集层面的攻击面分布

按 incident 数量看，当前 BlockSec 事件库中最值得优先投入的类别为：

1. **Business Logic Flaw**
2. **Access Control Issue**
3. **Compromised Private Key**
4. **Vulnerable / Flawed Price Dependency**
5. **Reentrancy**

这五类同时满足：
- 样本数量多；
- 单次损失高；
- 已有检测器基础存在增强空间；
- 能沉淀为跨协议通用能力。

### 9.3 与现有检测器的映射关系

| 攻击类别 | 现有可复用检测器 | 当前优势 | 当前缺口 |
|---------|------------------|----------|----------|
| Business Logic Flaw | `fund_drain_detector`, `economic_anomaly_detector`, `strategy_drain_detector` | 已支持 transfer / swap / mint / burn / ROI / 净获利分析 | 缺少“低投入→多步套利→单交易受害方净流失”联合评分 |
| Access Control Issue | `privileged_address_detector`, `proxy_upgrade_detector` | 已支持特权地址、异常 selector、升级/权限事件 | 缺少“权限变更 + 资金外流 + 新管理员/未知 owner”组合检测 |
| Compromised Private Key | `privileged_address_detector`, `fund_drain_detector`, `gas_price_detector` | 已支持特权调用、大额外流、gas 异常 | 缺少“特权地址主动发起 + 多资产快速清仓 + 外部接收方”联合检测 |
| Vulnerable Price Dependency | `price_manipulation_detector`, `oracle_manipulation_detector` | 已支持 swap 价格偏移、swap→drain、预言机时序 | 缺少“价格偏移后立即借贷/清算/提款”的闭环检测 |
| Reentrancy | `reentrancy_detector`, `fund_drain_detector` | 已支持重复日志频次和外流分析 | 当前 `reentrancy_detector` 过于粗糙，缺少重复受益人、递归式资产释放、trace 级重入路径 |

### 9.4 建议的检测器增强方向

> **P0 实施状态（2026-05-07）**
> 已完成首批落地：
> - `fund_drain_detector`：加入最大受害方外流结构化证据、多资产外流、外部接收方聚合信号；
> - `privileged_address_detector`：加入特权地址主动大额提取信号，并将未知 selector 收敛为必须与特权身份或资金外流联动才计分；
> - `price_manipulation_detector`：加入同池连续 swap 压力，以及“价格偏移后紧随资金回收”的闭环信号。
> 
> 对应新增结构化输出字段：
> - `fund_drain_detector.detection.outflow_signals`
> - `privileged_address_detector.detection.outflow_breakdown`
> - `price_manipulation_detector.detection.repeated_swap_pressure`
> - `price_manipulation_detector.detection.price_deviation_with_drain`

#### A. Business Logic Flaw

代表样本：Euler Finance  
核心通用信号：
- 攻击者初始资本极低或可忽略；
- 同一交易内出现多段 swap / mint / burn / borrow / withdraw 风格资产流转；
- 攻击者或关联地址净收益极高；
- 协议/受害地址净流失显著；
- 不一定依赖 upgrade / admin / known privileged path。

建议增强：
1. 在 `fund_drain_detector` 中加入**最大受害方净流失**分析，而不只看最大获利方。  
2. 在 `economic_anomaly_detector` 中加入**低成本进入 + 高 ROI + mint/burn/swap 组合**的叠加评分。  
3. 在 `strategy_drain_detector` 中沉淀“赎回/销毁后紧随大额底层资产外流”的泛化规则。  
4. 新增一个通用标签：`BUSINESS_LOGIC_EXTRACTION_PATTERN`，用于 combiner 汇总。

**本轮落地结果（已完成）**:
- `fund_drain_detector` 已补充最大亏损地址的 `outflow_signals` 输出，显式给出 `victim_address`、`loss_tokens`、`top_external_receivers`。
- 已新增 `MULTI_ASSET_DRAIN` 与 `RECEIVER_CLUSTER` 两类信号，用于表达多资产清仓与接收方聚合模式。
- 当前 `fund_drain_detector` 已可作为后续 `strategy_drain` / `reentrancy` 联动的结构化资金外流底座。

优先改动文件：
- [nodes/detectors/fund_drain.py](nodes/detectors/fund_drain.py)
- [nodes/detectors/economic_anomaly.py](nodes/detectors/economic_anomaly.py)
- [nodes/detectors/strategy_drain.py](nodes/detectors/strategy_drain.py)

#### B. Access Control Issue

代表样本：Cork  
核心通用信号：
- 调用者具备异常高权限；
- calldata selector 不属于常见公开 DeFi 函数；
- 同交易伴随 `OwnershipTransferred` / `RoleGranted` / `AdminChanged` / `Upgraded` 等事件；
- 紧接出现协议资产流向未知外部地址。

建议增强：
1. 在 `privileged_address_detector` 中把**异常 selector + 大额外流**联动加权。  
2. 在 `proxy_upgrade_detector` 中把**权限事件后紧随资产转移**视为高风险复合信号。  
3. 为 `privileged_address_detector` 增加 `known_protocol_addresses` 与 `sensitive_role_addresses` 的组合配置。  
4. 新增统一标签：`PRIVILEGED_DRAIN_AFTER_CONTROL_CHANGE`。

**本轮落地结果（已完成）**:
- `privileged_address_detector` 已将孤立未知 selector 降为弱信号，只有与特权身份、控制路径或大额外流联动时才真正计分。
- 已增加 `PRIVILEGED_LARGE_WITHDRAW` 专项信号，覆盖特权地址主动发起的大额对外提取。
- 已输出 `outflow_breakdown`，区分 `external_targets` 与 `protocol_targets`，便于后续和升级/权限事件做组合判断。

优先改动文件：
- [nodes/detectors/privileged_address.py](nodes/detectors/privileged_address.py)
- [nodes/detectors/proxy_upgrade.py](nodes/detectors/proxy_upgrade.py)
- [nodes/detectors/fund_drain.py](nodes/detectors/fund_drain.py)

#### C. Compromised Private Key

代表样本：Bybit  
核心通用信号：
- 交易由特权地址主动发起；
- 交易本身零投入或低投入；
- 协议金库/热钱包/多签相关地址出现大额多资产外流；
- 接收方为外部地址，而非协议内部资金归集地址；
- gas 使用/费用往往显著偏高，体现紧急转移。

建议增强：
1. 在 `privileged_address_detector` 中新增**特权地址主动发起大额提取**专项评分。  
2. 在 `fund_drain_detector` 中增强**多资产同时清仓**、**外部地址接收集中度**分析。  
3. 在 `gas_price_detector` 中把高 gas 仅作为辅助分，而不是主判断。  
4. 补充统一标签：`PRIVILEGED_WALLET_DRAIN_PATTERN`。

**本轮落地结果（已完成）**:
- `privileged_address_detector` 已落地 `PRIVILEGED_LARGE_WITHDRAW`，覆盖“特权地址主动发起 + 对外大额提取”的核心私钥失陷提款模式。
- `fund_drain_detector` 已落地 `MULTI_ASSET_DRAIN` 与 `RECEIVER_CLUSTER`，可表达金库/热钱包被快速多资产清仓且流向少数外部接收方的模式。
- 当前仍未把 `gas_price_detector` 纳入主判定链路；高 gas 保持为辅助证据，避免把紧急正常操作误判为攻击。

优先改动文件：
- [nodes/detectors/privileged_address.py](nodes/detectors/privileged_address.py)
- [nodes/detectors/fund_drain.py](nodes/detectors/fund_drain.py)
- [nodes/detectors/gas_price.py](nodes/detectors/gas_price.py)

#### D. Vulnerable Price Dependency

代表样本：UwU Lend  
核心通用信号：
- 同一交易内存在显著价格偏移；
- 多次 swap 或多跳路由；
- 价格偏移后立刻触发借贷、清算、提款、抵押品相关操作；
- 利润在短窗口内回收到攻击者地址。

建议增强：
1. 在 `price_manipulation_detector` 中把**同池连续 swap 价格偏移**与**后续 drain**绑定评分。  
2. 在 `oracle_manipulation_detector` 中强化**swap 在前、price query / price-dependent action 在后**的时序约束。  
3. 若 trace 可用，新增“价格操纵后的协议调用深度跃迁”特征。  
4. 统一标签建议：`PRICE_SHIFT_THEN_EXTRACTION`。

**本轮落地结果（已完成）**:
- `price_manipulation_detector` 已新增 `repeated_swap_pressure`，用于识别同池同方向连续 swap 压力，而不只依赖单次价格偏移。
- 已新增 `price_deviation_with_drain`，将显著价格偏移与紧随其后的资金回收链路做结构化绑定。
- 已补充 `PRICE_DEVIATION_WITH_DRAIN`、`REPEATED_SWAP_PRESSURE`、`REPEATED_SWAP_WITH_DRAIN` 等信号，使价格操纵闭环更接近真实利用路径。
- `oracle_manipulation_detector` 的更强时序约束仍属于后续 P1/P2 工作，当前 P0 仍保持纯 log 驱动实现。

优先改动文件：
- [nodes/detectors/price_manipulation.py](nodes/detectors/price_manipulation.py)
- [nodes/detectors/protocol/oracle_manipulation.py](nodes/detectors/protocol/oracle_manipulation.py)
- [nodes/detectors/fund_drain.py](nodes/detectors/fund_drain.py)

#### E. Reentrancy

代表样本：Curve  
核心通用信号：
- 同一合约地址在同交易中高频重复出现在日志/trace 中；
- 同类资产释放动作多次发生；
- 受益地址重复出现，且累计净收益显著；
- 事件序列具有“释放→回调→再次释放”的递归风格。

建议增强：
1. `reentrancy_detector` 不应只统计日志次数，还应引入**重复受益人**和**重复资产外流**分析。  
2. 把 `fund_drain_detector` 的净收益结果与 `reentrancy_detector` 联动，避免仅凭日志频次误报。  
3. 若 trace 可用，在 trace 层增加 A→B→A 型路径检测，作为行为级强信号。  
4. 统一标签建议：`RECURSIVE_ASSET_RELEASE_PATTERN`。

优先改动文件：
- [nodes/detectors/reentrancy.py](nodes/detectors/reentrancy.py)
- [nodes/detectors/fund_drain.py](nodes/detectors/fund_drain.py)
- `detectors/trace/` 下的重入行为检测器（后续补充）

### 9.5 实施优先级

建议按以下顺序实现：

**P0（应先做）**
1. 增强 `fund_drain_detector`：受害方净流失、多资产清仓、外部地址接收集中度  
2. 增强 `privileged_address_detector`：特权发起 + 大额外流 + 异常 selector 联合评分  
3. 增强 `price_manipulation_detector`：价格偏移与后续 drain 绑定  

**P1（紧随其后）**
4. 增强 `proxy_upgrade_detector`：控制权变更后资金外流复合风险  
5. 增强 `economic_anomaly_detector`：低成本高 ROI 闭环  
6. 增强 `reentrancy_detector`：重复受益人与重复释放模式  

**P2（依赖 trace / 更深数据）**
7. 增强 `oracle_manipulation_detector`：swap→price query→利用时序（已完成）  
8. 补行为层重入检测 / 业务逻辑攻击 trace 模式库（重入 trace 已完成，其他业务逻辑 trace 模式待补）

### 9.6 对测试建设的要求

每类增强都至少补三类测试：

1. **阳性样本**：构造与目标模式一致的 logs / transfers / trace。  
2. **阴性样本**：正常大额交易、正常升级、正常多次 swap，不应误报。  
3. **组合样本**：单特征弱、组合特征强，验证评分矩阵按预期叠加。

建议优先新增这些测试文件：
- `tests/nodes/test_detectors/test_fund_drain.py`
- `tests/nodes/test_detectors/test_privileged_address.py`
- `tests/nodes/test_detectors/test_price_manipulation.py`
- `tests/nodes/test_detectors/test_reentrancy.py`

### 9.7 本轮结论

本轮 BlockSec 全量事件库分析的核心结论是：

- 当前项目并不缺“检测器数量”，缺的是**跨 detector 的联合评分能力**；
- `fund_drain`、`privileged_address`、`price_manipulation` 三类检测器最值得先增强；
- `reentrancy_detector` 当前过于依赖简单日志计数，优先级高；
- 最有价值的方向不是继续堆新的单点 detector，而是围绕**资金外流、权限路径、价格偏移、递归释放**建立可复用的组合信号。

---

## 四、链上地址分析方法体系

### 4.1 地址特征提取

| 特征 | 数据来源 | 应用场景 |
|------|---------|---------|
| 首次活跃区块 | Moralis/RPC | 地址年龄检测 |
| 历史交易数 | Moralis/Etherscan | 活跃度评分 |
| 合约 or EOA | eth_getCode | 地址类型检测 |
| 创建时间 | Moralis | 新钱包风险 |
| 关联实体标签 | ARKM/Etherscan labels | 黑名单/白名单 |
| 资金来源链路 | 调用链分析 | 洗钱检测 |
| 持仓分布 | Moralis/Alchemy | 大户风险 |

### 4.2 图分析方法

**图神经网络（GNN）** 是当前学术界前沿方法，将地址关系建模为图：
- 节点 = 地址
- 边 = 交易/调用关系
- 特征 = 交易量、频率、代币种类

当前项目的 `address_graph_detector` 使用静态黑名单，可升级为动态图分析。

**简单可实施的图分析**:
1. N-hop 关联检测：检测地址是否在 N 跳内与已知恶意地址连接
2. 资金集中度分析：检测资金是否汇聚到少数地址
3. 环形交易检测：A→B→C→A 的资金环路

---

## 五、异常评分体系设计参考

### 5.1 多维度评分融合

```
综合风险分 = Σ(检测器i分数 × 权重i)

权重建议:
  - 已知黑名单地址交互: 0.35（最高权重）
  - 闪电贷模式:          0.25
  - 异常资金转移:        0.20
  - 地址年龄:            0.10
  - Gas 异常:            0.10
```

### 5.2 基于 Forta 的异常分数计算

Forta 的异常检测公式（参考）：
```
anomaly_score = Π(各子检测器异常概率)
threshold_critical = 1e-7   → CRITICAL 告警
threshold_low = 1e-4        → LOW 告警
```

本项目当前采用简单的线性评分（0-100），可考虑引入概率融合方法。

### 5.3 时间维度异常检测

- **速率异常**: 同一地址在 1 小时内交易数超过基准的 5 倍
- **时序异常**: 深夜（UTC 00:00-06:00）的大额操作更可疑
- **区块间隔**: 同一攻击者的准备交易和攻击交易间隔 < 10 区块

---

## 六、业界主流工具体系参考

| 工具/平台 | 检测能力 | 本项目参考价值 |
|----------|---------|--------------|
| **Forta Network** | 去中心化实时监控，300+ 检测 Bot | 检测分类体系参考 |
| **BlockSec Phalcon** | 实时交易拦截、调用链分析 | 行为检测方法参考 |
| **OpenZeppelin Defender** | 监控器 + 自动化防御 | Action 触发机制参考 |
| **Etherscan** | 地址标签、合约验证 | 标签数据源 |
| **ARKM (Arkham Intelligence)** | 实体标签数据库 | 已接入 |
| **Chainalysis / TRM Labs** | 合规 AML 检测 | 资金流向分析参考 |
| **Dedaub** | 反编译+漏洞扫描 | 合约静态分析 |
| **Slither/Mythril** | 静态代码分析 | 合约安全审计 |

---

## 七、推荐新增检测器清单

基于以上研究，结合项目现有架构，推荐按优先级开发以下检测器：

### 优先级 P0（高价值 + 可快速实现）

#### 7.1 重入攻击检测器（`reentrancy_detector`）
- **检测逻辑**: 分析 `call_tree`，检测是否存在 A→B→A 的回调路径
- **数据来源**: `detectors/trace/` 调用树（已有基础设施）
- **评分**: 回调深度 > 2 → 70分，回调深度 > 4 → 90分
- **标签**: `reentrancy_pattern`

#### 7.2 DEX 大额兑换检测器（`dex_large_swap_detector`）
- **检测逻辑**: 分析日志中的 Uniswap Swap 事件，计算交易量与流动性比率
- **关键 topic**: `0xd78ad95f` (V2 Swap), `0xc42079f9` (V3 Swap)
- **评分**: 占流动性比 > 5% → 60分，> 20% → 85分
- **标签**: `large_dex_swap`

#### 7.3 混币器交互检测器（`mixer_interaction_detector`）
- **检测逻辑**: 检测日志中是否有 Tornado Cash 等已知混币合约地址
- **数据来源**: alert_data logs（无需额外 API）
- **评分**: 直接交互 → 85分
- **标签**: `mixer_interaction`, `tornado_cash`

### 优先级 P1（中等价值 + 需要调用链数据）

#### 7.4 合约升级检测器（`proxy_upgrade_detector`）
- **检测逻辑**: 检测 Upgraded/AdminChanged/BeaconUpgraded 事件
- **关键 topic**:
  - `0xbc7cd75a` (Upgraded)
  - `0x7e644d79` (AdminChanged)
- **评分**: 非预期时间的升级 → 70分

#### 7.5 治理攻击检测器（`governance_attack_detector`）
- **检测逻辑**: 检测 OwnershipTransferred + 同块大额资产操作
- **关键 topic**:
  - `0x8be0079c` (OwnershipTransferred)
  - `0x2f878811` (RoleGranted)
- **评分**: 所有权转移 + 大额转账同交易 → 90分

#### 7.6 合约克隆/部署攻击检测器（`malicious_deploy_detector`）
- **检测逻辑**: 检测非验证合约创建后立即执行大额操作
- **评分**: 新合约 + 同区块大额操作 → 80分

### 优先级 P2（高价值 + 需要扩展架构）

#### 7.7 三明治攻击检测器（`sandwich_detector`）
- **需要**: 区块内多交易上下文（当前架构仅单笔交易）
- **评分**: 同块前后夹击 + 利润 > $1000 → 85分

#### 7.8 价格操纵检测器（`price_manipulation_detector`）
- **需要**: DEX 价格快照 API 或调用树分析
- **评分**: 价格波动 > 20% → 80分

---

## 八、检测器开发规范（基于现有框架）

### 8.1 新检测器代码模板

```python
"""[检测器名称]检测器"""
from __future__ import annotations
from typing import Any
from pydantic import Field
from nodes.base import NodeRegistry, score_to_severity
from nodes.detectors.base import BaseDetector, DetectorConfigMixin, DetectorInputMixin, DetectorOutputMixin


class XxxOutput(DetectorOutputMixin):
    """检测器输出"""
    pass


class XxxDetector(BaseDetector):
    name: str = "xxx_detector"
    label: str = "XXX检测"
    description: str = "检测[描述]"
    icon: str = "🔍"
    color: str = "#ef4444"

    class ConfigModel(DetectorConfigMixin):
        # 检测器特定配置
        custom_param: int = Field(default=10, description="自定义参数")

    OutputModel = XxxOutput

    async def process(self, input: DetectorInputMixin) -> XxxOutput:
        context = input.context
        # context 包含: tx_hash, chain_id, logs, unique_contracts,
        #               transfer_events, from_address, to_address, 
        #               value, gas_price, gas_used, input_data 等
        
        score = 0.0
        issues: list[str] = []
        
        # === 检测逻辑 ===
        
        threshold = self.config.get("threshold", 50.0)
        labels = issues if score >= threshold else []
        return XxxOutput(
            score=score,
            passed=score >= threshold,
            severity=score_to_severity(score),
            labels=labels,
            detection={"detected_issues": issues},
        )

NodeRegistry.register(XxxDetector)
```

### 8.2 日志特征提取工具函数（推荐封装到工具模块）

常用事件 topic 及其含义：

| Topic Hash | 事件名称 | 合约类型 |
|-----------|---------|---------|
| `0xddf252ad` | Transfer(address,address,uint256) | ERC20 |
| `0x8c5be1e5` | Approval(address,address,uint256) | ERC20 |
| `0xd78ad95f` | Swap(...) | Uniswap V2 |
| `0xc42079f9` | Swap(...) | Uniswap V3 |
| `0x1c411e9a` | Sync(uint112,uint112) | Uniswap V2 Pair |
| `0xe1fffcc4` | Deposit(address,uint256) | WETH |
| `0x7fcf532c` | Withdrawal(address,uint256) | WETH |
| `0x8be0079c` | OwnershipTransferred | Ownable |
| `0xbc7cd75a` | Upgraded(address) | EIP-1967 |
| `0x2f878811` | RoleGranted(bytes32,address,address) | AccessControl |

### 8.3 AlertData 中可直接使用的字段

```python
# context 字典包含（AlertData.model_dump()的结果）:
context = {
    "tx_hash": "0x...",
    "chain_id": 1,
    "chain_name": "ethereum",
    "block_number": 1234567,
    "logs": [
        {
            "address": "0x合约地址",
            "topics": ["0x事件签名", "0x参数1", "0x参数2"],
            "data": "0x数据",
            "blockNumber": 1234567,
            "transactionHash": "0x...",
            "logIndex": 0,
        }
    ],
    "log_count": 5,
    "unique_contracts": ["0x地址1", "0x地址2"],
    "unique_contract_count": 2,
    "unique_topics": ["0x事件签名1", ...],
    "transfer_events": [
        {
            "token_address": "0xtoken",
            "from_address": "from",
            "to_address": "to",
            "value_raw": 1000000
        }
    ],
    "transfer_event_count": 1,
}
```

### 8.4 注册检测器到系统

新增检测器后，需在 `nodes/__init__.py` 的 `init_registry()` 中注册：

```python
# nodes/__init__.py
def init_registry() -> None:
    ...
    from nodes.detectors import (
        gas_price, address_type, flash_loan, token_approval,
        token_anomaly, address_graph, address_age, arkm_label,
        xxx_detector,  # ← 新增
    )
```

---

## 九、数据来源与 API 扩展

### 9.1 当前已接入数据源

| 数据源 | Provider名称 | 提供字段 |
|-------|-------------|---------|
| 日志数据 | 内置（无需Provider） | logs, transfer_events |
| Moralis | `moralis_address` | address_create_time, first_block_number |
| ARKM | `arkm_label` | entity_type, entity_id, entity_name |

### 9.2 推荐扩展的 ContextProvider

| Provider | 用途 | 扩展难度 |
|---------|------|---------|
| **DEX 价格快照** | 获取 Uniswap/Curve 池子实时价格 | 中 |
| **Etherscan 标签** | 地址标签数据（交易所/项目） | 低 |
| **合约验证状态** | 检测非验证合约 | 低 |
| **Flashbots 捆绑** | MEV 捆绑交易识别 | 高 |
| **区块 Builder 信息** | 三明治攻击捆绑检测 | 高 |

### 9.3 新增 ContextProvider 模板

```python
# nodes/context/providers/xxx_provider.py
from nodes.context.provider import ContextProvider
from typing import Any

class XxxProvider(ContextProvider):
    name = "xxx"
    provides = ["field1", "field2"]

    def extract_addresses(self, context: dict) -> list[str]:
        return [context.get("from_address", "")]

    async def fetch(self, context: dict[str, Any]) -> dict[str, Any]:
        address = context.get("from_address", "")
        # 调用 API ...
        return {
            "field1": value1,
            "field2": value2,
        }
```

---

## 十、攻击事件分析驱动检测器开发

> 通过对真实攻击交易的深度分析，提炼通用检测特征，驱动检测器扩展开发。

### 10.1 已分析攻击案例

| 案例 | 攻击类型 | 链 | 损失 | 分析报告 |
|------|----------|-----|------|----------|
| DBXen (2026-03-11) | Burn-to-Earn 操纵 | Ethereum | ~$152K | [DBXen攻击分析](攻击事件分析驱动检测器开发/DBXEN/DBXen攻击分析-通用检测特征.md) |
| BCE Token (2026-03-23) | 闪电贷 + 代币铸造漏洞 | BSC | ~$800K | [BCE攻击分析](攻击事件分析驱动检测器开发/BCE/BCE攻击分析-通用检测特征.md) |
| USR/Resolv (2026-03-22) | 未授权铸造 + 协议逻辑漏洞 | Ethereum | ~$67.4M | [USR攻击分析](攻击事件分析驱动检测器开发/USR/USR攻击分析-通用检测特征.md) |
| Cyrus Finance (2026-03-22) | 闪电贷 + 现货价格预言机操纵 | BSC | ~$524K | [Cyrus攻击分析](攻击事件分析驱动检测器开发/CyrusFinance/CyrusFinance攻击分析-通用检测特征.md) |
| **Infini (2026-02-24)** | **私钥泄露 / 管理员权限滥用** | **Ethereum** | **~$49.5M** | **[Infini攻击分析](攻击事件分析驱动检测器开发/Infini/Infini攻击分析-通用检测特征.md)** |

### 10.2 分析驱动的检测器成果

| 检测器 | 来源案例 | 状态 |
|--------|----------|------|
| `EconomicAnomalyDetector` | DBXen | ✅ 已实现 |
| `FundDrainDetector` 增强 | DBXen | ✅ 已实现 |
| `IndirectionLayerDetector` | DBXen | ✅ 已实现 |
| `LiquidityImpactDetector` | BCE | 🔲 待开发 |
| `FlashLoanTraceDetector` 增强 | BCE | 🔲 待开发 |
| `EconomicAnomalyDetector` 增强（零投入+代理铸造） | USR | ✅ 已实现 |
| `FundDrainDetector` 增强（ERC-20净收益） | USR | 🔲 待开发 |
| `EconomicAnomalyDetector` 增强（Swap-Reverse Pattern） | Cyrus | ✅ 已实现 |
| `PriceManipulationDetector` (新建) | Cyrus | ✅ 已实现 |
| `PrivilegedAddressMonitor` (待新建) | Infini | 🔲 待开发 |
| `IndirectionLayerDetector` 增强（策略级联提取） | Infini | 🔲 待开发 |
| `EconomicAnomalyDetector` 增强（策略份额销毁） | Infini | 🔲 待开发 |

---

## 十一、参考资料

1. **Forta Network Attack Detector Bot**: https://docs.forta.network/en/latest/attack-detector-bot/
2. **NethermindEth Forta Agents**: https://github.com/NethermindEth/Forta-Agents
3. **BlockSec Phalcon**: https://docs.blocksec.com/phalcon/phalcon-security
4. **MEV 检测研究 (2024)**: "Remeasuring the Arbitrage and Sandwich Attacks of MEV" - arXiv:2405.17944
5. **GNN-based MEV Detection**: "Mecon: A GNN-based graph classification framework for MEV" - ScienceDirect 2025
6. **Tornado Cash 检测研究**: "Clustering Deposit and Withdrawal Activity in Tornado Cash" - arXiv:2510.09433
7. **DeFi 安全综述 (2025)**: "Comprehensive review of smart contract and DeFi security" - ScienceDirect

---

*本文档基于项目当前代码结构（2026-04-17）和业界最新研究成果整理，后续检测器开发应以本文档为参考基础。*
