# JUDAO Token 攻击事件检测策略分析

## 事件概览

- 交易：`0x956e38b8ddb40ba080c8042c685ae52ee5c1b096f1d7f0c4a6c59be3eb4265bd`
- 链：BSC
- 区块：`95070974`
- 时间：2026-04-28 08:00:00 UTC+8
- 交易状态：Success
- Sender / 最终直接获利地址：`0x5384b34c74024d6563b323351a4bbfa18432161b`
- Receiver / 临时入口合约：`0x3b9bc53af5012b12b6886a665bb22382211ae432`
- 临时执行合约：`0x530904b5b5ec86cca0528a682614f57f87e7f079`
- JUDAO Token / top profit address：`0xf55dff7898930a2d28cdbc39d615b1624ac86888`
- JUDAO-USDT Pancake LP / top loss address：`0x5d7b61e91cb59e90f7fae8d0fe2e73976161592f`
- ListaDAO Moolah Proxy：`0x8f73b65b4caaf64fba2af91cc5d4a2a1318e5d8c`
- PancakeSwap Router v2：`0x10ed43c718714eb63d5aa57b78b54704e256024e`
- USDT：`0x55d398326f99059ff775485246999027b3197955`
- WBNB：`0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c`
- Phalcon 归因：JUDAO Token Incident，loss 约 228,000 USD，Root Cause 为 Business Logic Flaw

## 可观察事实

### 余额变化

| 地址 | 资产 | 变化 | USD |
| --- | --- | ---: | ---: |
| `0x5384b34c74024d6563b323351a4bbfa18432161b` | USDT | `+205,259.490762457026328485` | `+205,243.41` |
| `0x5384b34c74024d6563b323351a4bbfa18432161b` | BNB | `+36` | `+22,563.67` |
| `0xf55dff7898930a2d28cdbc39d615b1624ac86888` | JUDAO | `+3,074,911.821714076242045743` | `+1,092,616.41` |
| `0x5d7b61e91cb59e90f7fae8d0fe2e73976161592f` | USDT | `-464,204.862567681013350522` | `-464,168.51` |
| `0x5d7b61e91cb59e90f7fae8d0fe2e73976161592f` | JUDAO | `-6,094,109.212384562419175643` | `-1,742,905.92` |
| `0x8599068597fd27d87514cb90c42300c03a474084` | USDT | `+126,390.017945602680958641` | `+126,380.12` |
| `0x82ea37296171b3f06702b0a6e0671172f79910ba` | USDT | `+54,971.039448662431922027` | `+54,966.73` |
| `0xccdd127594f24bf3a6ec08e5ea793203a8941540` | USDT | `+44,864.746539606315267924` | `+44,861.23` |
| `0xe7b95eaada89a0b2cce3086d5d4d1537d087a6e1` | USDT | `+10,106.292909056116654102` | `+10,105.50` |

本交易中 LP 是最大亏损方，sender 是最终可变现收益接收方，JUDAO token 合约本身被 Phalcon 识别为 top profit address。这说明该事件不是简单的 swap 套利，而是 token 合约业务逻辑参与了 LP 资产迁移。

### 资金流

闪电贷启动：

```text
ListaDAO Moolah Proxy
  -> 0x530904b5b5ec86cca0528a682614f57f87e7f079
  2,295,723.159642210185991283 USDT
```

执行合约向 JUDAO-USDT LP 注入同额 USDT，并触发 LP/JUDAO 转移：

```text
0x530904b5b5ec86cca0528a682614f57f87e7f079
  -> JUDAO-USDT LP
  2,295,723.159642210185991283 USDT

JUDAO-USDT LP
  -> 0x530904b5b5ec86cca0528a682614f57f87e7f079
  5,473,557.853503254662548079 JUDAO

JUDAO-USDT LP
  -> JUDAO Token
  3,019,432.906656452109766422 JUDAO

JUDAO-USDT LP
  -> 0x000000000000000000000000000000000000dead
  3,019,432.906656452109766424 JUDAO
```

后续又出现 JUDAO 回流 LP 与 USDT 被抽出：

```text
JUDAO Token
  -> JUDAO-USDT LP
  389,206.461086932694355629 JUDAO

0x530904b5b5ec86cca0528a682614f57f87e7f079
  -> JUDAO-USDT LP
  5,198,393.287782908758112995 JUDAO

JUDAO-USDT LP
  -> 0x530904b5b5ec86cca0528a682614f57f87e7f079
  2,523,596.497552140965784945 USDT
```

还款与利润分发：

```text
0x530904b5b5ec86cca0528a682614f57f87e7f079
  -> ListaDAO Moolah Proxy
  2,295,723.159642210185991283 USDT

0x530904b5b5ec86cca0528a682614f57f87e7f079
  -> Sender
  205,259.490762457026328485 USDT

0x530904b5b5ec86cca0528a682614f57f87e7f079
  -> PancakeSwap path
  22,613.847147473753465178 USDT -> 36 BNB -> Sender
```

### 调用结构

- 顶层 sender 创建临时入口合约，再创建临时执行合约。
- 执行合约调用 `JUDAO.basePair()`，返回 JUDAO-USDT LP。
- 执行合约对 Pancake Router 和 ListaDAO Moolah 做授权。
- 执行合约调用 ListaDAO Moolah `flashLoan`，借出约 2.29M USDT。
- 回调内多次调用 Pancake Router 与 LP：
  - `swapExactTokensForTokens` / `swapTokensForExactETH`
  - Pair `swap` selector `0x022c0d9f`
  - Pair `getReserves` selector `0x0902f1ac`
  - Token `balanceOf` selector `0x70a08231`
  - ERC20 `transfer` / `transferFrom`
- JUDAO token 合约自身作为 caller 参与 Router/LP 相关调用，并向多个地址分发 USDT。

## 攻击模式抽象

可以抽象为：

> 攻击者通过临时合约发起大额闪电贷，在回调内与 JUDAO-USDT LP 反复交互，触发 JUDAO token 合约的业务逻辑 / 转账副作用，使 LP 同时发生巨额 JUDAO 流失和 USDT 被抽出。最终执行合约还清闪电贷，并把剩余 USDT/BNB 分配给 sender 和相关地址。

关键特征：

1. 闪电贷为交易提供初始大额 USDT。
2. top loss address 是 DEX LP，而不是普通 EOA 或协议金库。
3. 被交易 token 合约本身既是 token 地址，又在资金流和调用流中活跃参与。
4. LP 与 token 合约之间存在大额同 token 往返、burn 地址转移、以及异常 USDT 流出。
5. 顶层交易创建临时执行合约，核心操作发生在临时合约和闪电贷回调内。
6. 最终利润以 USDT/BNB 形式回到 sender 或相关接收地址。

## 检测器开发建议

本事件应尽量复用已有策略，并拆分同质化检测，避免新增一个大而全的 JUDAO 专用检测器。

### 复用策略一：FlashLoanTraceDetector

已有能力：`nodes/detectors/protocol/flash_loan_trace.py`

复用目标：识别闪电贷借款、回调和回调后的利用动作。

本事件命中：

- `ListaDAO Moolah Proxy.flashLoan` / selector `0xe0232b42`
- token = USDT
- amount = `2,295,723.159642210185991283 USDT`
- 闪电贷回调内发生 Router swap、LP swap、token transfer 和还款

该部分不应在新 detector 中重复实现。新策略只消费其输出或复用 trace/fund-flow 中的 flash loan facts。

### 复用策略二：EconomicAnomalyDetector / PriceManipulationDetector

已有能力：

- `nodes/detectors/economic_anomaly.py`
- `nodes/detectors/price_manipulation.py`

复用目标：识别 DEX swap、LP drain、token burn/mint、异常 ROI、Swap -> Drain 等通用经济异常。

本事件命中：

- top loss 是 JUDAO-USDT LP
- LP 在同一交易中出现大额 USDT/JUDAO 出入
- 多次 Pair `swap` 与 `getReserves`
- LP 净损失超过百万美元

如果现有 `price_manipulation` 更偏价格偏移，建议在策略层将本事件归为 `economic_anomaly` 的 LP drain / business-logic side-effect 子类型，而不是把 LP drain 再写一遍。

### 新增策略三：Token Contract Active LP Drain Detector

建议新增一个窄职责检测器：`token_contract_active_lp_drain`

目标：检测“被交易 token 合约自身活跃参与 LP drain”的模式。

这个信号与已有 flash loan、普通价格操纵、普通资金流不同，核心关注点是：token 合约不是被动资产标识，而是主动参与资金迁移或调用流。

输入建议：

- `TransactionContext.extra.transfers` 或 fund flow transfers
- `TransactionContext.extra.trace_calls`
- `TransactionContext.extra.top_profit_address`
- `TransactionContext.extra.top_loss_address`
- `TransactionContext.extra.token_prices`
- `TransactionContext.extra.token_decimals`
- 可选：已有 detector 输出，如 flash loan / economic anomaly labels

核心逻辑：

1. 找出 top loss address 是否是 DEX pair / LP：
   - 可由 label、swap 调用、`getReserves`、Pair `swap` selector `0x022c0d9f` 推断。
2. 从 LP 资金流中识别主要 token：
   - 例如 USDT/JUDAO。
3. 找出 token contract 地址是否满足任一条件：
   - 是 top profit address；
   - 是 LP 大额转账接收方；
   - 是 LP 大额转账发送方；
   - 在 trace 中作为 caller 主动调用 Router/Pair/Token；
   - 向 sender、EOA、中间合约或费用地址分发稳定币。
4. 要求 LP 净损失金额超过阈值，并且 sender 或相关地址最终获得稳定币/原生币利润。
5. 将 flash loan、临时合约、重复 reserve/balance 读取作为加权信号，而不是硬编码为必需条件。

本事件命中：

- top loss = JUDAO-USDT LP
- token contract = `0xf55dff7898930a2d28cdbc39d615b1624ac86888`
- token contract 是 top profit address
- token contract 接收 `3,019,432.906656 JUDAO`
- token contract 向 LP 转回 `389,206.461087 JUDAO`
- token contract 向多个地址分发 USDT
- sender 获得 `205,259.49 USDT + 36 BNB`

### 可选策略四：Temporary Contract Execution Signal

建议仅作为通用加权信号，不与本检测器耦合。

目标：识别单笔交易内由 sender 创建临时合约，并由临时合约执行核心攻击路径。

本事件命中：

- `CREATE 0x3b9bc53af5012b12b6886a665bb22382211ae432`
- `CREATE 0x530904b5b5ec86cca0528a682614f57f87e7f079`
- 临时执行合约完成 flash loan、swap、还款和利润转移

该信号可用于多类攻击：flash loan exploit、callback exploit、价格操纵、业务逻辑漏洞。它不应成为 JUDAO detector 的专属逻辑。

## 推荐规则链设计

### 规则链 A：复用优先的组合检测

```text
AlertTrigger
  -> EVMTraceProvider
  -> TokenTransferProvider / FundFlowProvider
  -> TopProfitLossDetector
  -> FlashLoanTraceDetector
  -> EconomicAnomalyDetector
  -> TokenContractActiveLPDrainDetector
  -> RiskScoreAggregator
```

该规则链适合本事件落地。新增 detector 只负责 token 合约主动参与 LP drain 的窄信号。

### 规则链 B：轻量资金流优先

```text
AlertTrigger
  -> TokenTransferProvider / FundFlowProvider
  -> TopProfitLossDetector
  -> EconomicAnomalyDetector
  -> TokenContractActiveLPDrainDetector
```

适合没有完整 trace 时使用。缺点是难以可靠识别 flash loan 和临时合约，只能依赖 LP/top profit/top loss/资金流特征。

### 规则链 C：Trace 加权版本

```text
AlertTrigger
  -> EVMTraceProvider
  -> FlashLoanTraceDetector
  -> TemporaryContractExecutionDetector
  -> TokenContractActiveLPDrainDetector
  -> RiskScoreAggregator
```

适合复用 trace 信号做加权，但不建议把临时合约逻辑写死到 `token_contract_active_lp_drain` 中。

## Detector 输入/输出建议

### TokenContractActiveLPDrainDetector

输入：

```json
{
  "tx_hash": "string",
  "chain_id": 56,
  "from_address": "sender",
  "transfers": [
    {
      "token": "address",
      "from": "address",
      "to": "address",
      "amount": "decimal|string",
      "amount_raw": "string"
    }
  ],
  "trace_calls": [
    {
      "caller": "address",
      "callee": "address",
      "selector": "0x...",
      "operation": "CALL|STATICCALL|DELEGATECALL|CREATE"
    }
  ],
  "top_profit_address": "address",
  "top_loss_address": "address",
  "token_prices": {},
  "token_decimals": {}
}
```

输出建议：

```json
{
  "passed": true,
  "score": 85,
  "severity": "CRITICAL",
  "labels": [
    "token_contract_active_lp_drain",
    "lp_top_loss",
    "token_contract_top_profit",
    "business_logic_anomaly"
  ],
  "detection": {
    "token_contract": "0xf55dff7898930a2d28cdbc39d615b1624ac86888",
    "lp_address": "0x5d7b61e91cb59e90f7fae8d0fe2e73976161592f",
    "sender_profit_address": "0x5384b34c74024d6563b323351a4bbfa18432161b",
    "lp_loss_usd": 2207074.42,
    "sender_profit_usd": 227807.09,
    "token_contract_net_token_in": "3074911.821714076242045743",
    "stable_profit_to_sender": "205259.490762457026328485",
    "native_profit_to_sender": "36",
    "token_contract_active_as_caller": true,
    "flash_loan_present": true,
    "temporary_contract_count": 2
  }
}
```

## 误报控制

可能误报场景：

1. 税费 / 分红型 token 合约在正常 swap 中自动收税、回流 LP 或分发手续费。
2. 自动做市 / 自动加池逻辑导致 token 合约与 LP 之间有资金往返。
3. 项目方主动执行回购、销毁、加池、迁池操作。
4. Router 聚合交易中 LP 是短时净损，但用户或协议获得等值资产。

降低误报建议：

- 不单独以 token 合约参与转账告警，必须结合 LP 为 top loss。
- 要求 LP 净损失达到高美元阈值，例如 `>= 100,000 USD`。
- 要求 sender 或非协议地址获得稳定币 / 原生币净利润。
- 如果 token 合约只是收税地址，但 LP 没有异常净损，不应告警。
- 如果 LP 损失和用户获得资产价值大致等价，应该交给正常 swap 逻辑过滤。
- 临时合约、flash loan、短时间多次 reserve/balance 读取只加权，不作为唯一触发条件。

## 可落地的 MVP 检测逻辑

```python
lp = top_loss_address
profit = top_profit_address
sender = tx.from_address

if not looks_like_dex_pair(lp, trace_calls, labels):
    return no_alert

lp_loss_usd = estimate_net_loss_usd(lp, transfers, token_prices, token_decimals)
sender_profit_usd = estimate_net_profit_usd(sender, transfers, token_prices, token_decimals)

candidate_token_contracts = set()
for transfer in transfers:
    if transfer.from == lp or transfer.to == lp:
        if transfer.token not in stablecoins_and_wrapped_native:
            candidate_token_contracts.add(transfer.token)

for token in candidate_token_contracts:
    active_as_fund_flow = any(
        transfer.from == token or transfer.to == token
        for transfer in transfers
    )
    active_as_caller = any(
        call.caller == token and call.callee in {router, lp} or call.caller == token
        for call in trace_calls
    )
    token_is_top_profit = token == profit

    if lp_loss_usd >= 100_000 and sender_profit_usd >= 10_000:
        if token_is_top_profit or (active_as_fund_flow and active_as_caller):
            alert()
```

评分建议：

| 信号 | 分值 |
| --- | ---: |
| top loss 是 DEX LP | +20 |
| LP 净损失 >= 100k USD | +25 |
| LP 净损失 >= 1M USD | +20 |
| token contract 是 top profit | +20 |
| token contract 在资金流中收/发 LP 相关资产 | +15 |
| token contract 作为 caller 调用 Router/Pair/Token | +15 |
| sender 获得稳定币或原生币利润 >= 10k USD | +15 |
| 闪电贷存在 | +10 |
| 交易内创建临时执行合约 | +10 |

严重级别：

- `score >= 80`：CRITICAL
- `score >= 60`：HIGH
- `score >= 40`：SUSPICIOUS

## 本事件最小测试样本

建议把该交易固化为离线 fixture，至少包含：

- `tx_hash = 0x956e38b8ddb40ba080c8042c685ae52ee5c1b096f1d7f0c4a6c59be3eb4265bd`
- `chain_id = 56`
- `from_address = 0x5384b34c74024d6563b323351a4bbfa18432161b`
- `top_profit_address = 0xf55dff7898930a2d28cdbc39d615b1624ac86888`
- `top_loss_address = 0x5d7b61e91cb59e90f7fae8d0fe2e73976161592f`
- flash loan transfer：Moolah -> execution contract，`2,295,723.159642210185991283 USDT`
- LP -> execution contract：`5,473,557.853503254662548079 JUDAO`
- LP -> JUDAO token contract：`3,019,432.906656452109766422 JUDAO`
- LP -> dead：`3,019,432.906656452109766424 JUDAO`
- execution contract -> LP：`5,198,393.287782908758112995 JUDAO`
- LP -> execution contract：`2,523,596.497552140965784945 USDT`
- execution contract -> sender：`205,259.490762457026328485 USDT`
- USDT -> BNB swap path leading to sender `+36 BNB`
- trace calls：`CREATE` × 2、flashLoan selector `0xe0232b42`、Pair `swap` `0x022c0d9f`、Pair `getReserves` `0x0902f1ac`、ERC20 `transfer` / `transferFrom`

正常行为 fixture 建议覆盖：

- 普通 fee-on-transfer token swap：token 合约收税但 LP 不是 top loss。
- 项目方加池 / 回购 / 销毁：token 合约与 LP 有资金往返，但 sender 没有稳定币/原生币净利润。
- 普通 flash loan arbitrage：存在闪电贷和 LP swap，但 token 合约不是 top profit，也不主动参与 LP drain。

## 落地状态（2026-05-16）

已落地标准检测器 `token_contract_active_lp_drain`：

- 检测器文件：`nodes/detectors/token_contract_active_lp_drain.py`
- 离线 fixture：`tests/fixtures/judao_token_active_lp_drain.py`
- 单元测试：`tests/nodes/test_detectors/test_token_contract_active_lp_drain.py`
- 规则链回放测试：`tests/engine/test_judao_token_active_lp_drain_replay.py`

实现范围：检测器仅覆盖 token 合约自身在 LP top loss 交易中同时具备 LP 相关资金流/调用流活跃参与、sender 稳定币/原生币获利的窄职责信号；闪电贷、临时合约、reserve/swap 次数仅作为加权 evidence，不重复实现通用闪电贷或 LP drain 检测。

已通过针对性测试：

```bash
AlertProcessor/.venv/Scripts/python.exe -m pytest AlertProcessor/tests/nodes/test_detectors/test_token_contract_active_lp_drain.py AlertProcessor/tests/engine/test_judao_token_active_lp_drain_replay.py -q
```

结果：`4 passed`。

## 结论

本事件应作为“复用已有策略 + 新增窄职责检测器”的案例落地。已有 `FlashLoanTraceDetector` 负责闪电贷信号，已有 `EconomicAnomalyDetector` / `PriceManipulationDetector` 负责 LP/经济异常信号；新增检测器只负责 `token_contract_active_lp_drain`：识别 token 合约自身作为资金流和调用流参与者、并与 LP top loss 和 sender 利润同时出现的业务逻辑漏洞模式。这样能避免重复实现 flash loan / swap / LP drain 通用逻辑，也能把本案最有泛化价值的信号独立沉淀。
