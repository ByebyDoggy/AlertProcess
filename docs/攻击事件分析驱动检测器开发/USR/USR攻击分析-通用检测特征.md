# USR (Resolv) 攻击交易分析 — 通用检测特征提炼

> **交易哈希**:
> - TX1: `0xfe37f25efd67d0a4da4afe48509b258df48757b97810b28ce4c649658dc33743`
> - TX2: `0x7f914328a67f7094eedb0efda7aef74aafdb7f862ad7bc78259564fd453a931d`
> - TX3: `0x41b6b9376d174165cbd54ba576c8f6675ff966f17609a7b80d27d8652db1f18f`
>
> **链**: Ethereum Mainnet | **时间**: 2026-03-22 10:21 ~ 11:41 (UTC+8)
> **分析日期**: 2026-04-26
> **分析方法**: 从3笔同源攻击交易中提炼**不依赖函数签名**的通用攻击特征，驱动检测器扩展

---

## 一、攻击概述

攻击者（Resolv Exploiter, `0x04a288...`）利用 Resolv 协议的 TheCounter 合约的 `completeSwap` 函数逻辑漏洞，在**零投入**的情况下反复调用该函数，每次均触发 USR 代币的 `mint` 操作铸造大量 USR，然后通过 `transfer` 将铸造的 USR（扣除约 0.1% 手续费后）转给自己。同时，每笔交易还将 100,000 USDC 从 TheCounter 转入 Resolve Labs Treasury。

三笔交易共铸造 **80,099,995 USR**（约 $67.5M），攻击者净获 **80,029,895 USR**（约 $67.4M）。加上 TheCounter 流出的 300,000 USDC（约 $300K），总损失约 **$67.7M**。

**攻击本质**: 协议逻辑漏洞 + 未授权铸造（Unauthorized Mint）。TheCounter 合约的 `completeSwap` 函数缺乏调用者身份验证或额度限制，任何人都可以调用该函数触发 USR 的 mint 操作，实现"零成本铸造代币"。

**攻击类型分类**: 未授权铸造 + 协议逻辑漏洞利用（Unauthorized Mint / Protocol Logic Exploit）

**与 BCE/DBXen 攻击的关键区别**:
- **无闪电贷**: 攻击者不需要大量资金操纵市场
- **无 DEX Swap**: 不涉及流动性操纵或价格操纵
- **零交互成本**: 纯粹的函数调用漏洞，不需要任何资金投入
- **协议内部函数**: 攻击调用的是协议自身的 `mint` 函数，而非外部 DEX

---

## 二、资金流向

### TX3（最早，区块 24710031，10:21:35）

```
攻击者 EOA (0x15cad41e...)
    │ 0 wei
    ▼
TheCounter (0xa27a69ae...) [Receiver]
    │
    ├─[1] completeSwap(_id=30, _targetAmount=50,000,000)
    │
    ├─[2] USDC.transfer(Treasury, 100,000)       ← TheCounter → Treasury
    │
    ├─[3] USR.mint(TheCounter, 50,000,000)       ← ★ 铸造 5000万 USR
    │
    ├─[4] USR.transfer(Exploiter, 49,950,000)    ← TheCounter → 攻击者（扣 0.1% 手续费）
    │
    └─[5] Event: SwapRequestCompleted(swappedAmount=49,950,000, takenFee=50,000,000)
```

### TX2（中间，区块 24710383，11:32:47）

```
攻击者 EOA (0x15cad41e...)
    │ 0 wei
    ▼
TheCounter (0xa27a69ae...) [Receiver]
    │
    ├─[1] completeSwap(_id=32, _targetAmount=99,995.213)
    │
    ├─[2] USDC.transfer(Treasury, 100,000)       ← TheCounter → Treasury
    │
    ├─[3] USR.mint(TheCounter, 99,995.213)       ← ★ 铸造约 10万 USR
    │
    ├─[4] USR.transfer(Exploiter, 99,895.218)    ← TheCounter → 攻击者
    │
    └─[5] Event: SwapRequestCompleted(swappedAmount=99,895.218, takenFee=99,995.213)
```

### TX1（最后，区块 24710428，11:41:47）

```
攻击者 EOA (0x15cad41e...)
    │ 0 wei
    ▼
TheCounter (0xa27a69ae...) [Receiver]
    │
    ├─[1] completeSwap(_id=33, _targetAmount=30,000,000)
    │
    ├─[2] USDC.transfer(Treasury, 100,000)       ← TheCounter → Treasury
    │
    ├─[3] USR.mint(TheCounter, 30,000,000)       ← ★ 铸造 3000万 USR
    │
    ├─[4] USR.transfer(Exploiter, 29,970,000)    ← TheCounter → 攻击者（扣 0.1% 手续费）
    │
    └─[5] Event: SwapRequestCompleted(swappedAmount=29,970,000, takenFee=30,000,000)
```

### 汇总投入产出

| 指标 | TX3 | TX2 | TX1 | 合计 |
|------|-----|-----|-----|------|
| 投入 (tx.value) | 0 ETH | 0 ETH | 0 ETH | **0 ETH** |
| USR 铸造量 | 50,000,000 | 99,995.213 | 30,000,000 | **80,099,995** |
| USR 转出量 | 49,950,000 | 99,895.218 | 29,970,000 | **80,029,895** |
| 手续费 (takenFee) | 50,000 | 99.995 | 30,000 | 50,100 |
| USDC → Treasury | 100,000 | 100,000 | 100,000 | 300,000 |
| **攻击者净利润** | ~$42.3M | ~$84K | ~$25.3M | **~$67.4M** |
| **ROI** | ∞ | ∞ | ∞ | **∞（零投入）** |

---

## 三、通用攻击特征（不依赖函数签名）

以下特征完全从**资金流、事件日志、地址关系**中提取，不依赖任何特定函数签名，适用于跨协议检测。

---

### 特征 A：零投入获取大量代币（Infinite ROI）

**定义**: 交易的 tx.value 为 0，攻击者在交易结束后净获得大量 ERC-20 代币，且无闪电贷借入。

**本交易表现**:

| 指标 | TX3 | TX2 | TX1 |
|------|-----|-----|-----|
| tx.value | 0 ETH | 0 ETH | 0 ETH |
| 闪电贷 | 无 | 无 | 无 |
| 净获得 | +49,950,000 USR | +99,895 USR | +29,970,000 USR |
| ROI | ∞ | ∞ | ∞ |

**关键区分**: 与 BCE 攻击的零投入不同，本攻击**不使用闪电贷**，是纯粹的零成本铸造。这使得该信号更加强烈 — 闪电贷至少需要还款逻辑，而零成本铸造直接违反经济常识。

**检测方法**:

```
1. 检查 tx.value == 0
2. 检查交易内无闪电贷借入（无已知闪电贷协议交互）
3. 检查攻击者 ERC-20 余额净增加 > 阈值
4. tx.value == 0 且无闪电贷且余额大增 → 零投入异常信号（最强信号）
```

**通用性说明**: 任何允许零成本获取大量代币的交易都是攻击，这是最通用的攻击信号。

---

### 特征 B：异常代币铸造（Mint Anomaly）

**定义**: 交易中存在从零地址（0x0000...）向合约铸造大量代币的 Transfer 事件。

**本交易表现**:

| 交易 | Transfer(from=0x0, to=TheCounter) | 金额 |
|------|--------------------------------------|------|
| TX3 | USR mint | 50,000,000 |
| TX2 | USR mint | 99,995.213 |
| TX1 | USR mint | 30,000,000 |

**检测方法**:

```
1. 检测 Transfer(from=0x0) 事件（ERC-20 标准铸造事件）
2. 铸造金额 > 历史正常铸造量的 N 倍 → 异常铸造信号
3. 铸造接收者非标准金库地址 → 可疑信号
```

**通用性说明**: 代币铸造漏洞是 DeFi 攻击中最常见的类型之一。任何允许无权限铸造或铸造量计算错误的合约都会呈现此模式。

---

### 特征 C：铸造后立即转出（Mint-Then-Transfer 模式）

**定义**: 同一交易内，先出现从零地址铸造代币（`Transfer(from=0x0, to=X)`），然后 X 立即将大部分代币转出到第三方地址。

**本交易表现**:

```
Transfer(from=0x0, to=TheCounter, amount=50,000,000 USR)       ← 铸造
Transfer(from=TheCounter, to=Exploiter, amount=49,950,000 USR)  ← 立即转出（99.9%）
```

**关键异常**:

- 铸造后立即转出比例极高（99.9%），仅留下约 0.1% 作为手续费
- 转出地址不是协议的金库或管理员，而是 EOA（攻击者）
- 铸造和转出在同一交易内完成

**检测方法**:

```
1. 找到 Transfer(from=0x0, to=X) 铸造事件
2. 检查同一交易内 Transfer(from=X, to=Y) 转出事件
3. 计算 转出量 / 铸造量 = 转出比例
4. 转出比例 > 阈值（如 90%）且转出地址非协议标准地址 → Mint-Then-Transfer 信号
```

**通用性说明**: 这是"铸造后套现"的通用模式。在正常场景中，铸造代币通常用于协议内部结算，不会立即大比例转出到外部地址。

---

### 特征 D：协议代币 mint 后的 Swap 完成事件（Mint-SwapComplete 闭环）

**定义**: 同一交易内出现完整的"mint 铸造代币 → transfer 转出代币 → SwapRequestCompleted 事件"闭环。

**本交易的闭环**:

```
USR.mint(TheCounter, amount) → USR.transfer(Exploiter, amount - fee) → SwapRequestCompleted(swappedAmount, takenFee)
```

**检测方法（纯 logs 可做）**:

1. 检测 `Transfer(from=0x0)` 铸造事件
2. 检测紧随的 `Transfer(from=mint接收者)` 转出事件
3. 检测协议自定义的完成事件（如 `SwapRequestCompleted`）
4. 三个信号在同一交易内按时间顺序出现 → 闭环完成

**通用性说明**: 这是协议级 Swap/兑换机制的通用模式。任何允许用户通过单次调用触发"铸造 → 转出 → 确认"的协议，如果缺少权限验证，都会呈现此模式。

---

### 特征 E：同源多笔攻击（Repeated Attack Pattern）

**定义**: 同一攻击者在短时间内（同一区块或相邻区块）发起多笔结构完全相同的交易，每笔都执行相同的攻击逻辑。

**本交易表现**:

| 指标 | 值 |
|------|-----|
| 攻击者 | 同一 EOA（`0x15cad41e...`） |
| Receiver | 同一合约（TheCounter） |
| 调用函数 | 相同（`completeSwap`） |
| 时间跨度 | ~1小时20分钟（3个区块） |
| 交易数量 | 3 笔 |

**检测方法**:

```
1. 检测同一 Sender 在短时间内（如 24 小时）多次调用同一 Receiver 的同一函数
2. 每笔交易结构高度相似（相同的调用模式、相同的资金流向）
3. 多笔交易累积效应远超正常操作 → 同源攻击信号
```

**通用性说明**: 攻击者通常会反复利用同一漏洞多次获利。单笔交易可能金额较小或看似正常，但多笔相同模式的交易组合是强烈的攻击信号。此特征需要跨交易上下文分析。

---

### 特征 F：协议合约作为代理铸造者（Proxy Mint Pattern）

**定义**: 代币的 mint 操作不是由代币合约自身发起，而是由另一个协议合约（代理）触发，且该代理合约将铸造的代币转给调用者而非协议金库。

**本交易表现**:

```
攻击者 EOA → TheCounter(Receiver).completeSwap()
  → USR.mint(_account=TheCounter, _amount=50M)  ← TheCounter 触发铸造，接收者是 TheCounter
  → USR.transfer(to=Exploiter, value=49.95M)     ← TheCounter 将铸造的 USR 转给攻击者
```

**关键异常**:

- TheCounter 是 USR 的代理铸造者：它调用 USR.mint()，但自身不是 USR 代币合约
- 铸造接收者（TheCounter）立即将代币转给第三方（攻击者），而非保留在协议内
- TheCounter 的 USR 余额变化：铸造大量 → 转出大量 → 净余额几乎不变

**检测方法**:

```
1. 检测 Transfer(from=0x0, to=X) 事件中 X 不是零地址
2. 检测同一交易内 Transfer(from=X, to=Y) 中 Y 不是协议已知金库地址
3. 计算 X 的余额净变化 = 铸造量 - 转出量
4. 余额净变化 ≈ 0（即几乎所有铸造量都被转出）→ 代理铸造后清空信号
```

**通用性说明**: 许多 DeFi 协议使用代理合约来管理代币铸造（如 Curve 的 minter、Aave 的 lending pool）。当代理合约的权限控制不当时，攻击者可以利用代理合约铸造代币并转出。

---

## 四、特征组合与评分矩阵

| 特征组合 | 评分 | 含义 |
|----------|------|------|
| A（零投入ROI）单独 | 50 | 资金异常，但原因不明 |
| B（异常铸造）单独 | 35 | 可能有铸造漏洞，但需确认上下文 |
| A + B（零投入 + 异常铸造） | **70** | 零成本获取大量铸造代币 → 高概率攻击 |
| A + B + C（+ 铸造后转出） | **85** | 零成本 + 铸造 + 立即转出 → 攻击 |
| A + B + C + D（+ 闭环） | **90** | 零成本 + 铸造 + 转出 + 闭环 → 几乎确定攻击 |
| A + B + C + D + F（+ 代理铸造） | **93** | 全部命中（含代理铸造模式）→ 确定攻击 |
| E（同源多笔）单独 | 30 | 可能是正常批量操作 |
| A + E（零投入 + 同源多笔） | **65** | 零投入反复操作 → 攻击 |
| C（铸造后转出）单独 | 40 | 可能是正常的 claim 操作 |
| F（代理铸造）单独 | 45 | 代理铸造本身可以是合法的 |

---

## 五、与现有检测器的覆盖度分析

### 现有检测器覆盖情况

| 检测器 | 特征覆盖 | 缺口 |
|--------|----------|------|
| `EconomicAnomalyDetector` | 部分覆盖 B（铸造）、C（铸造转出）、F（ROI） | **不检测代理铸造模式**，不检测零投入+无闪电贷场景，不区分代理铸造与直接铸造 |
| `FundDrainDetector` | 部分覆盖 A（零投入） | **不计算 ERC-20 净收益**（只计算 ETH 流出），不检测铸造-转出关联 |
| `TokenAnomalyDetector` | 极弱覆盖 B（大额转账） | 不检测铸造模式，不检测铸造后转出 |
| `FlashLoanTraceDetector` | 不覆盖 | 本攻击无闪电贷 |
| `ReentrancyDetector` | 不覆盖 | 无重入攻击 |
| `ProxyUpgradeDetector` | 不覆盖 | 无代理升级 |
| `IndirectionLayerDetector` | 微弱覆盖 | 攻击不涉及中间层代理 |

### 核心缺口

1. **零投入 + 无闪电贷 + 大量代币净收益检测**: 当前 `EconomicAnomalyDetector` 的 ROI 计算主要关注 ETH 流出和闪电贷场景，**未覆盖无闪电贷的零成本铸造场景**。这是本次攻击最强烈的信号。

2. **铸造后立即转出比例检测**: 当前 `EconomicAnomalyDetector` 检测 Mint-Then-Transfer 模式，但**不计算转出比例**（转出量/铸造量），无法区分正常的小额转出和异常的大比例转出。

3. **代理铸造者模式检测**: 当前系统没有检测器识别"代理合约铸造代币后立即转给第三方"的模式。这是本次攻击的关键特征 — TheCounter 是 USR 的代理铸造者。

4. **ERC-20 余额净收益计算**: 当前 `FundDrainDetector` 主要计算 ETH 流出，**不计算 ERC-20 代币的余额净收益**。本攻击中攻击者获得的是 USR 代币，不是 ETH。

5. **同源多笔攻击检测**: 当前系统是单交易级别的检测，**无法跨交易分析同源攻击模式**。

---

## 六、检测器扩展建议

### 6.1 增强 `EconomicAnomalyDetector`（P0 — 覆盖最关键的缺口）

**新增能力**:

| 增强项 | 描述 | 实现方式 |
|--------|------|----------|
| **零投入 + 无闪电贷 + 代币净收益** | 检测无闪电贷场景下的零成本代币获取 | tx.value==0 且无闪电贷事件且攻击者 ERC-20 余额净增加 > 阈值 |
| **铸造后转出比例** | 计算 Transfer(from=mint接收者) / Transfer(from=0x0) 的比例 | 转出比例 > 90% → 异常信号 |
| **代理铸造者模式** | 检测非代币合约的地址触发铸造，且铸造后转出给第三方 | 分析 Transfer(from=0x0, to=X) 后紧接 Transfer(from=X, to=Y)，Y 非协议标准地址 |

**评分增强**:

```
当前: 铸造 + 转出 → 15分
增强: 铸造 + 转出(>90%比例) → 25分
增强: 零投入 + 无闪电贷 + 代币净收益(>阈值) → 35分
增强: 代理铸造者模式 → 20分
增强: 零投入 + 铸造 + 转出 + 代理铸造 → 组合加分 +20
```

**关键实现要点**:

- 零投入检测: tx.value == 0 且交易内无闪电贷事件（已知闪电贷协议地址列表）
- 转出比例: `sum(Transfer(from=X, to=Y)) / sum(Transfer(from=0x0, to=X))`，当 Y != X 时计算
- 代理铸造者: 识别 Transfer(from=0x0, to=X) 中的 X 不是零地址，且后续有 Transfer(from=X, to=Y) 且 Y 是 EOA

---

### 6.2 增强 `FundDrainDetector`（P1 — ERC-20 净收益计算）

**新增能力**:

| 增强项 | 描述 | 实现方式 |
|--------|------|----------|
| **ERC-20 余额净收益** | 计算攻击者的 ERC-20 代币余额净增加 | 从 logs 中计算每个地址的 Transfer in/out 差额 |
| **零投入场景覆盖** | 扩展 ROI 计算到 ERC-20 代币 | 用 ERC-20 净收益折算 USD 作为替代 ROI 分母 |

---

### 6.3 检测器优先级排序

| 优先级 | 检测器 | 理由 |
|--------|--------|------|
| P0 | `EconomicAnomalyDetector` 增强（零投入+无闪电贷、铸造转出比例、代理铸造者） | 改动最小，收益最大，可立即覆盖最关键的攻击模式 |
| P1 | `FundDrainDetector` 增强（ERC-20 净收益） | 增强 ERC-20 资金流失检测能力 |
| P2 | 跨交易同源攻击检测（新增） | 需要跨交易上下文，实现复杂度较高 |

---

## 七、本交易涉及的关键地址

| 地址 | 标签 | 角色 |
|------|------|------|
| `0x15cad41e6bdcadc7121ce65080489c92cf6de398` | 攻击者 EOA (Sender) | 交易发起者 |
| `0x04a288a7789dd6ade935361a4fb1ec5db513caed` | Resolv Exploiter | USR 代币接收者 |
| `0xa27a69ae180e202fde5d38189a3f24fe24e55861` | Resolve Labs : TheCounter | [Receiver]，代理铸造者 |
| `0x66a1e37c9b0eaddca17d3662d6c05f4decf3e110` | USR Token | 被铸造的代币合约 |
| `0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48` | USDC | 稳定币 |
| `0xacb7027f271b03b502d65feba617a0d817d62b8e` | Resolve Labs : Treasury (Proxy) | USDC 接收地址 |

---

## 八、关键调用链索引（Invocation Flow）

### 三笔交易统一调用模式

| 步骤 | 操作 | 合约 | 函数 | 关键数据 |
|------|------|------|------|----------|
| 0 | 入口 | TheCounter [Receiver] | completeSwap | tx.value=0, _id=N, _targetAmount=X |
| 1 | USDC 转出 | USDC | transfer(Treasury, 100,000) | TheCounter → Treasury |
| 2 | USDC DELEGATECALL | Circle: Fiat Token V2_2 | transfer(Treasury, 100,000) | 代理执行 |
| 3 | ★ USR 铸造 | USR | mint(TheCounter, X) | from=0x0, amount=_targetAmount |
| 4 | USR mint DELEGATECALL | SimpleToken | mint(TheCounter, X) | 代理执行 |
| 5 | USR 转出 | USR | transfer(Exploiter, X - fee) | TheCounter → 攻击者 |
| 6 | USR transfer DELEGATECALL | SimpleToken | transfer(Exploiter, X - fee) | 代理执行 |
| 7 | 事件 | TheCounter | SwapRequestCompleted | swappedAmount, takenFee |

---

## 九、与 DBXen / BCE 攻击的对比分析

| 维度 | DBXen 攻击 | BCE Token 攻击 | USR (Resolv) 攻击 |
|------|-----------|---------------|-------------------|
| **攻击类型** | Burn-to-Earn 操纵 | 闪电贷 + 代币铸造漏洞 | 未授权铸造 + 协议逻辑漏洞 |
| **是否使用闪电贷** | ❌ 无 | ✅ ListaDAO Moolah | ❌ 无 |
| **tx.value** | 0.146 ETH | 0 BNB | 0 ETH |
| **核心漏洞** | 销毁奖励计算偏差 | BCE 代币无限铸造 | completeSwap 无权限验证 |
| **价格操纵** | 无 | DEX Swap 操纵 | 无 |
| **代币操作** | 销毁 XEN → 获取奖励 | 铸造 BCE → 卖出 | 铸造 USR → 直接转出 |
| **涉及 DEX** | Uniswap V2 | PancakeSwap V3 | ❌ 无 |
| **利润** | ~$152K | ~$800K | ~$67.4M |
| **攻击复杂度** | 中（需构造销毁链） | 高（闪电贷+Swap+铸造） | **极低（直接调用函数）** |
| **通用特征** | 高ROI、销毁-释放闭环 | 闪电贷+Swap+铸造闭环 | **零投入+铸造+立即转出** |

**关键发现**: USR 攻击是三种攻击中**最简单**的 — 不需要闪电贷、不需要 DEX 交互、不需要价格操纵，只需要调用一个缺乏权限验证的函数。这也使其成为**最容易检测**的类型 — 零投入获取大量代币本身就是最强烈的攻击信号。

---

## 十、总结

本攻击暴露了一个**当前检测系统未充分覆盖的攻击类别**：无闪电贷、无 DEX 交互的纯协议逻辑漏洞利用（Unauthorized Mint）。

### 攻击特征与现有检测器的关系

```
攻击特征                              现有检测器覆盖
─────────────────────────────────────────────────────────
零投入 + 无闪电贷 + 大量代币净收益     ❌ 不计算 ERC-20 净收益 + 不区分有无闪电贷
异常代币铸造 (Transfer from=0x0)       ⚠️ EconomicAnomalyDetector 部分覆盖
铸造后立即转出 (Mint-Then-Transfer)    ⚠️ EconomicAnomalyDetector 部分覆盖（无比例检测）
代理铸造者模式                          ❌ 无检测器
铸造-转出-完成事件闭环                   ⚠️ 部分覆盖
同源多笔攻击                            ❌ 不支持跨交易分析
```

### 核心发现

1. **零投入 + 无闪电贷是最强攻击信号**: 当 tx.value=0 且无闪电贷且攻击者获得大量 ERC-20 代币时，几乎必然是攻击。这比有闪电贷的场景信号更强，因为攻击者没有任何资金成本。

2. **铸造后转出比例是关键区分指标**: 正常的协议操作也会触发 mint + transfer，但转出比例通常较低。当转出比例 > 90% 时，说明铸造的代币几乎全部被转走，这是异常的。

3. **代理铸造者模式需要专门检测**: 当前系统将 `Transfer(from=0x0)` 视为铸造，但未区分"谁触发了铸造"以及"铸造后代币流向了哪里"。代理铸造者（如 TheCounter）将铸造代币转给第三方是攻击的关键特征。

### 最小可行扩展路径

1. **第一步**: 在 `EconomicAnomalyDetector` 中增加零投入+无闪电贷+ERC-20净收益检测和铸造后转出比例检测
2. **第二步**: 增加代理铸造者模式检测（Transfer(from=0x0, to=X) + Transfer(from=X, to=Y) 的关联分析）
3. **第三步**: 增强 `FundDrainDetector` 的 ERC-20 净收益计算能力
