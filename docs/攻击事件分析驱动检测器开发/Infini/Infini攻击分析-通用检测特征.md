# Infini 攻击交易分析 — 通用检测特征提炼

> **交易哈希**:
> - TX-A: `0xacf84c5944f662a4fcf783806993d713a150994932008e72e4e47a58d6665f7f`
> - TX-B: `0xecb31ff694c0e6c5e5b225c261854c0749ecf5d53c698fcda61f2d8e3db8f9fc`
>
> **链**: Ethereum Mainnet | **区块**: 21913141
> **时间**: 2025-02-24 10:15:59 (UTC+8)
> **分析日期**: 2026-04-26
> **分析方法**: 从 2 笔同区块同源攻击交易中提炼**不依赖函数签名**的通用攻击特征，驱动检测器扩展

---

## 一、攻击概述

攻击者利用被盗的 **Infini: dev team** 私钥（`0xc49b5e5b9da66b9126c1a62e9761e6b2147de3e1`），在**同一区块**中连续发起 3 笔交易（Nonce 155、156、157），调用 Infini 协议合约（`0x9a79f4105a4e1a050ba0b42f25351d394fa7e1dc`），通过该合约的权限函数提取 InfiniMorphoStrategy 在 Morpho Blue 市场中的所有 USDC 存款，并将资金全部转给攻击者控制的地址（`0x3ac96134fb0e42a52d33045aee50b89790f05ed0`）。

两笔交易（TX-A 和 TX-B）共提取 **~$49.5M**：TX-A 提取 11,455,666 USDC (~$11.45M)，TX-B 提取 38,060,996 USDC (~$38.06M)。加上第 3 笔交易（Nonce 156），总损失约 **$50M**。

**攻击本质**: 私钥泄露 / 访问控制漏洞（Private Key Compromise / Access Control Breach）。攻击者**不是**通过合约逻辑漏洞攻击，而是直接使用了 Infini 开发团队的管理员权限从策略合约中提取资金。

**攻击类型分类**: 私钥泄露 + 协议管理员权限滥用（Private Key Compromise / Admin Privilege Abuse）

**与 USR/DBXen/BCE 攻击的关键区别**:
- **无合约逻辑漏洞**: 攻击者没有利用任何合约漏洞，使用的是合法权限函数
- **无闪电贷**: 不需要借入资金
- **无 DEX Swap**: 不涉及流动性操纵
- **管理员权限**: 调用的是协议的 privileged 函数，普通用户无法调用
- **检测难度最高**: 调用合法函数，所有操作在代码层面"正常"

---

## 二、资金流向

### TX-A (Nonce 155, Block 21913141, Position 3)

```text
Infini: dev team (compromised, 0xc49b5e...)
    │ 0 wei
    ▼
Infini (Receiver, 0x9a79f4...) [进入点]
    │
    ├─ balanceOf(Infini) — 查询 USDC 余额
    ├─ InfiniMorphoStrategy.underlyingToken() → USDC
    ├─ balanceOf(InfiniMorphoStrategy) — 查询策略中 USDC
    ├─ InfiniMorphoStrategy.redeem(11,455,666)
    │   └─ resolvUSDC.redeem → 销毁 11,301,933 resolvUSDC
    ├─ InfiniMorphoStrategy.withdraw(11,455,666)
    │   └─ USDC.transfer(Exploiter, 11,455,666)  ← ★ 资金转移
    └─ [Receiver] Event
```

**Balance Changes (TX-A)**:

| 地址 | Token | 变化量 | USD 价值 |
|------|-------|--------|----------|
| 0x0000... (零地址) | resolvUSDC | +11,301,933 (销毁) | $0 |
| Infini Exploiter | USDC | **+11,455,666** | **+$11,455,342** |
| InfiniMorphoStrategy | resolvUSDC | -11,301,933 | $0 |
| Morpho Blue | USDC | -11,455,666 | -$11,455,342 |

### TX-B (Nonce 157, Block 21913141, Position 5)

**Balance Changes (TX-B)**:

| 地址 | Token | 变化量 | USD 价值 |
|------|-------|--------|----------|
| 0x0000... (零地址) | USUALUSDC+ | +35,654,943 (销毁) | +$38,058,515 |
| Infini Exploiter | USDC | **+38,060,996** | **+$38,059,919** |
| InfiniMorphoStrategy | USUALUSDC+ | -35,655,254 | -$38,058,847 |
| Morpho Blue | USDC | -38,060,996 | -$38,059,919 |

### 投入产出汇总

| 指标 | TX-A | TX-B | 合计 |
|------|------|------|------|
| 投入 (tx.value) | 0 ETH | 0 ETH | **0 ETH** |
| 闪电贷 | 无 | 无 | **无** |
| 提取 USDC | 11,455,666 | 38,060,996 | **49,516,662 USDC** |
| 攻击者净利润 | ~$11.45M | ~$38.06M | **~$49.5M** |
| **ROI** | ∞ | ∞ | **∞（零投入）** |

---

## 三、通用攻击特征（不依赖函数签名）

以下特征完全从**资金流、事件日志、地址关系**中提取，不依赖任何特定函数签名，适用于跨协议检测。

---

### 特征 A：管理员私钥泄露 — 零投入的高权限调用（Key Compromise / Privileged Access）

**定义**: 交易的 Sender 是协议的管理员/开发者地址（而非普通用户），Sender 调用 Receiver（协议合约）的 privileged 函数，在零投入的情况下提取大量资金。

**本交易表现**:

| 指标 | 值 |
|------|-----|
| Sender 标签 | "Infini: dev team" (开发团队地址) |
| Receiver 标签 | "Infini" (主协议合约) |
| 调用函数 | `0xcfda09ef` (非标准公开函数) |
| tx.value | 0 ETH |
| 提取资金 | 49,516,662 USDC (~$49.5M) |

**关键信号**: Sender 不是 EOA 普通用户，而是协议开发团队的已知地址。该地址通常不应有高频交易行为。开发地址的参数调用 privileged 函数提取协议资金 → 私钥泄露的高概率信号。

**检测方法**:

```text
1. 检查 Sender 地址是否被标记为协议管理员/开发者/团队地址
2. 检查 Receiver 是否是被协议合约
3. 检查调用函数是否为已知的 privileged 函数
4. tx.value == 0 且调用结果是大额资金转出 → 高权限泄露信号
5. Sender 在短时间内发起多笔结构相同的交易 → 批量提取信号
```

**通用性说明**: 私钥泄露是最常见的攻击向量之一（2024-2025 占比超过 30%）。需要**链下标签系统**的支持（监控已知协议管理员地址）。

---

### 特征 B：策略合约份额一次性全部赎回（Bulk Strategy Redemption）

**定义**: 同一交易内，调用策略合约的 redeem/withdraw 函数，一次性提取该策略在底层协议中的全部存款。

**本交易表现**:

| 指标 | TX-A | TX-B |
|------|------|------|
| 策略合约 | InfiniMorphoStrategy | InfiniMorphoStrategy |
| 底层协议 | Morpho Blue (USDC) | Morpho Blue (USDC) |
| 赎回操作 | redeem(11,455,666) + withdraw(11,455,666) | redeem + withdraw |
| 赎回比例 | ~100%（全部余额） | ~100%（全部余额） |
| 份额销毁 | 11,301,933 resolvUSDC → 0x0 | 35,655,254 USUALUSDC+ → 0x0 |

**检测方法**:

```text
1. 检测 Redeem/Withdraw 事件（ERC-4626 标准或策略合约事件）
2. 检测策略份额销毁事件（Transfer(to=0x0)）
3. 计算赎回金额是否接近策略/池子的全部余额
4. 赎回后资金立即转出到外部地址 → 全额清算信号
```

**通用性说明**: 正常用户很少在单笔交易中赎回策略的全部存款。全额赎回通常是协议迁移、清算或攻击。

---

### 特征 C：协议份额代币销毁后资金立即流出（Redeem-Then-Drain 模式）

**定义**: 同一交易内，先出现策略份额代币的销毁（Transfer to 0x0），随后立即出现大额底层资产从同一策略合约流出到外部地址。

**本交易表现**:

```text
TX-A: Transfer(resolvUSDC: 策略 → 0x0, 11,301,933) → USDC.transfer(→ Exploiter, 11,455,666)
TX-B: Transfer(USUALUSDC+: 策略 → 0x0, 35,655,254) → USDC.transfer(→ Exploiter, 38,060,996)
```

**检测方法**:

```text
1. 检测 Transfer(to=0x0) 事件（份额销毁）
2. 识别销毁代币是否为策略份额代币
3. 检测销毁后紧随的大额 ERC-20 Transfer
4. 资金流出目标不是协议金库 → Redeem-Then-Drain 信号
```

---

### 特征 D：同区块多笔结构相同的交易（Same-Block Batch Attack）

**定义**: 同一区块内，相同的 Sender 连续发起多笔交易，每笔交易调用相同的 Receiver 合约，执行相同的操作模式。

**本交易表现**:

| 指标 | 值 |
|------|-----|
| Sender | 相同 (Infini: dev team) |
| Receiver | 相同 (Infini) |
| 调用函数 | 相同 (0xcfda09ef) |
| 区块 | 21913141 (同区块 3 笔) |
| Nonce | 155, 156, 157 (连续) |

**关键异常**: 同一开发地址在**单个区块**内连续发起 3 笔结构完全相同的交易，每笔提取不同策略的全部资金。

**检测方法**:

```text
1. 检测同一 Sender 在相同区块内发起多笔 Receiver 相同的交易
2. 检查调用签名、fund flow 结构是否高度相似
3. 多笔交易累积提取金额 > 阈值 → 批量攻击信号
4. Sender 是管理员地址时信号极强
```

---

### 特征 E：深层策略调用链资金提取（Multi-Layer Strategy Drain）

**定义**: 资金提取路径涉及多层合约调用（Sender → Receiver → Strategy → Vault → Pool），最终全部流向外部地址。

**本交易的调用链**: `Sender(dev) → Infini → InfiniMorphoStrategy → resolvUSDC → Exploiter`

**检测方法**:

```text
1. 检测调用链深度 > 3 层
2. 检测调用链中是否存在策略合约
3. 资金经过"多层提取 → 上层汇聚 → 单地址接收"模式
4. 最终资金方向为"底层 → 上层 → 外部地址"
```

---

### 特征 F：零投入 + 无闪电贷 + 大量稳定币提取（Zero Capital Extraction）

| 指标 | TX-A | TX-B |
|------|------|------|
| tx.value | 0 ETH | 0 ETH |
| 闪电贷 | 无 | 无 |
| 净获得 | +11,455,666 USDC | +38,060,996 USDC |
| ROI | ∞ | ∞ |

**检测方法**:

```text
1. 检查 tx.value == 0
2. 检查交易内无闪电贷事件
3. 检查 USDC 净增加 > 阈值
4. 检查资金流出源是否为协议金库/策略合约
5. 零投入 + 无闪电贷 + 大额 USDC 提取 → 零资本提取信号
```

---

## 四、特征组合与评分矩阵

| 特征组合 | 评分 | 含义 |
|----------|------|------|
| A（管理员调用）单独 | 30 | 管理员调用本身不一定异常 |
| B（批量策略赎回）单独 | 40 | 可能是正常的策略迁移 |
| A + B（管理员 + 批量赎回） | **60** | 可疑 |
| A + B + C（+ 赎回后资金流出） | **75** | 高概率攻击 |
| A + B + C + D（+ 同区块多笔） | **85** | 攻击 |
| A + B + C + D + E（+ 多层策略提取） | **90** | 几乎确定攻击 |
| A + B + C + D + E + F（+ 零投入） | **95** | 确定攻击 |
| F（零投入ROI）单独 | 50 | 资金异常 |

**组合评分说明**: 本攻击的特征组合以**管理员权限滥用**为核心，与 USR/BCE/DBXen 攻击（事件驱动）有本质区别。USR/BCE 类型是 Logs-driven，Infini 类型是 Address + Trace driven。

---

## 五、与现有检测器的覆盖度分析

| 检测器 | 特征覆盖 | 缺口 |
|--------|----------|------|
| `EconomicAnomalyDetector` | 部分覆盖 F（零投入ROI） | **不检测管理员地址标签**，不检测策略赎回 |
| `FundDrainDetector` | 弱覆盖 C（大额资金流出） | **不区分管理员调用** |
| `FlashLoanTraceDetector` | 不覆盖 | 无闪电贷 |
| `ReentrancyDetector` | 不覆盖 | 无重入 |
| `IndirectionLayerDetector` | 部分覆盖 E（多层调用） | **不检测资金级联提取语义** |
| `AddressAgeDetector` | 微弱覆盖 | dev 地址不是新地址 |
| `TokenAnomalyDetector` | 不覆盖 | 只涉及标准 USDC Transfer |

### 核心缺口

1. **管理员/开发者地址监控缺失**: 无法将 Sender 地址标签纳入检测维度
2. **策略赎回→资金流出关联缺失**: 不区分策略份额销毁与普通销毁
3. **同区块多笔同模式交易检测缺失**: 无法检测批量提取攻击
4. **调用链多层资金汇聚检测缺失**: 不检测资金级联提取到单目标地址
5. **已知管理员地址行为基线缺失**: 无法建立历史行为基线对比

---

## 六、检测器扩展建议

### 6.1 新增 `PrivilegedAddressMonitor` （P0）

**定位**: 基于地址标签和交易模式的高权限地址异常行为监控器。

**核心能力**:

| 维度 | 检测方法 | 数据来源 |
|------|----------|----------|
| 已知管理员地址检测 | Sender 在已知管理员/开发者/团队列表 | 标签服务 / 内部维护 |
| 特权函数调用检测 | 调用非标准函数（calldata 签名不在常见函数集） | trace / calldata |
| 异常发送频次 | 同一管理员地址在短时间内多笔交易 | block-level |
| 批量提取检测 | 同一区块多笔 Receiver/函数相同 | block-level |
| 提取目的监控 | 资金最终流向不是协议金库 | trace + logs |

**评分逻辑**: 已知管理员调用(+20) + 每笔提取超阈值(+15) + 非标准函数(+10) + 同区块多笔(+15) + 资金流向外部(+25) + 历史偏差(+20)

### 6.2 增强 `IndirectionLayerDetector` （P0 — 多层策略提取）

| 增强项 | 描述 |
|--------|------|
| 资金级联提取模式 | 检测 "Sender → Receiver → Strategy → Vault → External" 模式 |
| 策略合约识别 | 识别名称含 Strategy/Vault 的合约 |
| 资金汇聚检测 | 检测从多个底层合约提取到同一顶层地址 |

### 6.3 增强 `EconomicAnomalyDetector` （P1 — 策略份额销毁）

| 增强项 | 描述 |
|--------|------|
| 策略份额销毁识别 | 区分策略份额销毁与普通销毁 |
| 赎回→流出关联 | 检测份额销毁后紧接底层资产流出 |
| 全额赎回检测 | 赎回金额是否接近合约全部余额 |

### 6.4 检测器优先级排序

| 优先级 | 检测器 | 理由 |
|--------|--------|------|
| **P0** | 新增 `PrivilegedAddressMonitor` | 覆盖私钥泄露类攻击（最大缺口） |
| **P0** | 增强 `IndirectionLayerDetector` | 覆盖策略级联提取模式 |
| **P1** | 增强 `EconomicAnomalyDetector` | 增强策略赎回检测 |
| **P2** | 跨区块行为基线检测（新增） | 建立管理员地址行为基线 |

---

## 七、与 USR/BCE/DBXen 攻击的对比分析

| 维度 | DBXen | BCE | USR (Resolv) | **Infini** |
|------|-------|-----|-------------|-----------|
| **攻击类型** | Burn-to-Earn | 闪电贷+铸造 | 未授权铸造 | **私钥泄露** |
| **闪电贷** | ❌ | ✅ | ❌ | ❌ |
| **tx.value** | 0.146 ETH | 0 BNB | 0 ETH | **0 ETH** |
| **核心漏洞** | 奖励计算偏差 | 无限铸造 | 无权限验证 | **私钥泄露** |
| **攻击入口** | Uniswap V2 | 闪电贷回调 | 调用 completeSwap | **开发签名** |
| **资金来源** | 自付 | 闪电贷借入 | 零成本铸造 | **协议存款** |
| **利润** | ~$152K | ~$800K | ~$67.4M | **~$49.5M** |
| **检测难度** | 中 | 中 | 易 | **最难** |
| **特征类型** | 事件驱动 | 事件驱动 | 事件驱动 | **地址+权限驱动** |

**关键发现**: Infini 攻击是四种攻击中**检测难度最高**的 — 没有合约漏洞，调用合法函数，所有操作在代码层面"正常"。唯一异常的是**调用的身份不对** — 私钥被泄露的开发团队地址不应该进行批量资金提取。

这揭示了一个重要的检测盲区：**当前系统完全基于交易内容的异常检测，缺乏基于身份的上下文分析（Who is calling?）**。

---

## 八、本交易涉及的关键地址

| 地址 | 标签 | 角色 |
|------|------|------|
| `0xc49b5e5b9da66b9126c1a62e9761e6b2147de3e1` | Infini: dev team | 被盗私钥的 Sender |
| `0x9a79f4105a4e1a050ba0b42f25351d394fa7e1dc` | Infini | 协议主合约（Receiver） |
| `0x3ac96134fb0e42a52d33045aee50b89790f05ed0` | Infini Exploiter: Exploit | 攻击者接收地址 |
| `0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb` | Morpho: Morpho Blue | 底层借贷协议（Top Loser） |
| `0x7fa9f82f5f89dd81b86284938a395e7fc976c253` | InfiniMorphoStrategy (A) | TX-A 的策略合约 |
| `0xe0e83f21d5b6da61c9cf75d3b89fbcacfbfde327` | InfiniMorphoStrategy (B) | TX-B 的策略合约 |
| `0x132e6c9c33a62d7727cd359b1f51e5b566e485eb` | resolvUSDC | TX-A 的策略份额代币 |
| `0xd63070114470f685b75b74d60eec7c1113d33a3d` | USUALUSDC+ | TX-B 的策略份额代币 |
| `0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48` | USDC | 提取的底层资产 |
| `0xd4c848600d8b273776800daf87667562a2272446` | — | TX-B 中 USUALUSDC+ 微量接收者 |

---

## 九、关键调用链索引（Invocation Flow）

### TX-A 调用链

| 步序 | 调用类型 | 合约 | 函数 | 关键数据 |
|------|----------|------|------|----------|
| 0 | CALL | Infini [Receiver] | `0xcfda09ef` | tx.value=0, raw data |
| 1 | STATICCALL | USDC | balanceOf | Infini 合约 USDC 余额 |
| 2 | DELEGATECALL | Circle: Fiat Token V2_2 | balanceOf | 余额=100 |
| 3 | STATICCALL | InfiniMorphoStrategy | underlyingToken | USDC |
| 4 | STATICCALL | USDC | balanceOf | 策略 USDC 余额=0 |
| 5 | CALL | InfiniMorphoStrategy | **redeem**(11,455,666) | 赎回策略份额 |
| 6 | STATICCALL | resolvUSDC | convertToShares | 11,301,933 份额 |
| 7 | STATICCALL | resolvUSDC | balanceOf | 策略持有份额确认 |
| 8 | CALL | resolvUSDC | **redeem** | 执行份额赎回 |
| 9 | CALL | InfiniMorphoStrategy | **withdraw**(11,455,666) | 提取底层资产 |
| 10 | CALL | USDC | **transfer**(→Exploiter) | ★ 资金转移给攻击者 |
| 11 | DELEGATECALL | Circle: Fiat Token V2_2 | transfer | USDC 实际执行 |

---

## 十、总结

本笔攻击暴露了一个**当前检测系统完全未覆盖的攻击类别**：私钥泄露 / 管理员权限滥用（Private Key Compromise）。

### 攻击特征与现有检测器的关系

```text
攻击特征                              现有检测器覆盖
─────────────────────────────────────────────────
管理员地址调用 privileged 函数          ❌ 无管理员地址监控
策略份额一次性全部赎回                  ❌ 无策略赎回检测
赎回后资金立即流出到外部地址            ❌ 无赎回-流出关联
同区块多笔结构相同交易                  ❌ 不支持跨交易分析
多层策略调用链提取                     ⚠️ IndirectionLayer 部分覆盖
零投入 + 无闪电贷 + 大额 USDC 提取     ⚠️ EconomicAnomaly 部分覆盖
```

### 核心发现

1. **私钥泄露攻击的检测需要地址标签系统**: 这是当前系统最大的缺失。与其他攻击类型不同，私钥泄露攻击的"异常信号"不是来自合约交互模式，而是来自**调用者的身份异常**。

2. **策略赎回 → 资金流出 → 外部地址是强信号**: 无论底层协议如何，策略份额赎回后资金流向外部地址（而非协议内）是攻击的通用特征。

3. **同区块多笔交易是批量提取的典型模式**: 攻击者知道钱包权限随时可能被撤销，因此在极短时间内完成所有提取。这种"抢时间"的行为模式是私钥泄露攻击的独特特征。

4. **四种攻击类型需要四种检测策略**:
   - DBXen（Burn-to-Earn）: 闭环检测（Swap → Burn → Claim）
   - BCE（闪电贷+铸造）: 闪电贷 + Swap + 铸造闭环检测
   - USR（未授权铸造）: 零投入 + 铸造 → 立即转出检测
   - **Infini（私钥泄露）: 管理员身份 + 批量策略赎回检测**

### 最小可行扩展路径

1. **第一步**: 新增 `PrivilegedAddressMonitor` 检测器，实现管理员地址列表维护和异常调用检测
2. **第二步**: 增强 `IndirectionLayerDetector`，增加资金级联提取和策略合约识别能力
3. **第三步**: 增强 `EconomicAnomalyDetector`，增加策略份额销毁识别和赎回-流出关联检测

### 补充说明

本 Infini 攻击分析与之前的 **USR (Resolv Labs) 攻击分析是完全独立的两个攻击事件**：
- **USR 攻击**（`docs/攻击事件分析驱动检测器开发/USR/`）: Resolv Labs 协议的 TheCounter.completeSwap 逻辑漏洞，零成本铸造 USR 代币 — 合约逻辑漏洞
- **Infini 攻击**（本文档）: Infini 协议的开发团队私钥泄露，从 Morpho Blue 策略中提取全部存款 — 权限漏洞

两起攻击虽然都涉及 ETH 链上的 DeFi 协议，但攻击者、攻击方式、涉及合约、资金流向模式完全不同，检测特征也不重叠。
