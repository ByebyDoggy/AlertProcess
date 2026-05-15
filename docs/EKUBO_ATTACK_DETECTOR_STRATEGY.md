# Ekubo Protocol 攻击事件检测策略分析

## 事件概览

- 交易：`0x770bc9a1f7c32cb63a5002b9ceb5c7994cd3af0fc6b2309cb32d3c46f629daa0`
- 链：Ethereum mainnet
- 区块：`25030409`
- 时间：2026-05-05 17:50:35 UTC（Phalcon 页面显示 UTC+8 为 2026-05-06 01:50:35）
- 攻击者：`0xa911ff351b143634dbc5af3e204ea074583a83e3`（Phalcon 标记为 EkuboProtocol Exploiter）
- 入口合约：`0x61b0dad9628d3e644eb560a5c9b0f960430e3a75`
- Ekubo Core：`0xe0e0e08a6a4b9dc7bd67bcb7aade5cf48157d444`
- 中间调用合约：`0x8ccb1ffd5c2aa6bd926473425dea4c8c15de60fd`
- 主要受损地址：`0x765decf4fa157756e850c1079f60801b9219edd1`
- 受损资产：WBTC `0x2260fac5e5542a773aa44fbcfedf7c193bc2c599`
- 净收益 / 损失：17 WBTC，约 1,377,396.49 USD
- Phalcon 归因：Ekubo Protocol Incident，Root Cause 为 Access Control Issue

## 可观察事实

### 余额变化

本交易最终只形成两个核心净变化：

| 地址 | 资产 | 变化 | USD |
| --- | --- | --- | --- |
| `0xa911ff351b143634dbc5af3e204ea074583a83e3` | WBTC | `+17` | `+1,377,396.49` |
| `0x765decf4fa157756e850c1079f60801b9219edd1` | WBTC | `-17` | `-1,377,396.49` |

资金流显示 WBTC 先从受害地址转入 Ekubo Core，再由 Ekubo Core 转给攻击者：

1. `0x765decf4fa157756e850c1079f60801b9219edd1 -> 0xe0e0e08a6a4b9dc7bd67bcb7aade5cf48157d444`：17 WBTC
2. `0xe0e0e08a6a4b9dc7bd67bcb7aade5cf48157d444 -> 0xa911ff351b143634dbc5af3e204ea074583a83e3`：17 WBTC

### 调用规模与结构

- 内部交易数：1021
- 事件数：170
- trace 节点数：2555
- CALL 数：1023
- gas used：1,735,786
- 顶层交易 `value = 0`
- 顶层 calldata selector：`0x718a549d`
- 入口合约随后调用 `0x8ccb1ffd5c2aa6bd926473425dea4c8c15de60fd` 的 selector `0x00090905`

调用图呈现强烈的批量循环特征，以下调用各出现 85 次：

| 调用 | 次数 |
| --- | ---: |
| `0x00090905 @ 0x8ccb1ffd5c2aa6bd926473425dea4c8c15de60fd` | 85 |
| `lock() @ Ekubo Core` | 85 |
| `locked(uint256) @ 0x8ccb1ffd5c2aa6bd926473425dea4c8c15de60fd` | 85 |
| `forward(address) @ Ekubo Core` | 85 |
| `forwarded(...) @ WBTC` | 85 |
| `withdraw(...) @ Ekubo Core` | 85 |
| `transfer(...) @ WBTC` | 85 |
| `pay(...) @ Ekubo Core` | 85 |
| `payCallback(...) @ 0x8ccb1ffd5c2aa6bd926473425dea4c8c15de60fd` | 85 |
| `transferFrom(...) @ WBTC` | 85 |
| `balanceOf(...) @ WBTC` | 171 |

其中每轮核心动作金额相同：

- `locked(uint256)` 返回 `amount:int128 = 20,000,000`
- `withdraw(WBTC, attacker, 20,000,000)`
- `WBTC.transfer(attacker, 20,000,000)`
- `pay(WBTC)` 返回 `payment:uint128 = 20,000,000`
- `payCallback(..., WBTC)`
- `WBTC.transferFrom(victim, Ekubo Core, 20,000,000)`

WBTC 为 8 位 decimals，因此 `20,000,000` raw amount = `0.2 WBTC`。85 轮合计 `17 WBTC`。

### 单轮行为模板

每个循环基本符合以下模式：

```text
entry contract
  -> helper.0x00090905(...)
    -> EkuboCore.lock()
      -> helper.locked(0) returns amount = 20,000,000
        -> EkuboCore.forward(WBTC) / WBTC.forwarded(...)  // revert，但不影响整轮继续
        -> EkuboCore.withdraw(WBTC, attacker, 20,000,000)
          -> WBTC.transfer(attacker, 20,000,000)
        -> EkuboCore.pay(WBTC)
          -> helper.payCallback(0, WBTC)
            -> WBTC.transferFrom(victim, EkuboCore, 20,000,000)
```

这里最异常的点不是单次 `transferFrom` 本身，而是同一个交易里重复 85 次执行“从第三方 victim 拉入 WBTC，再从 Core 向 attacker 转出同等 WBTC”的闭环。该闭环最终将第三方地址的 17 WBTC 迁移给攻击者。

## 攻击模式抽象

可以抽象为：

> 攻击者通过批量调用受影响协议的 lock/callback 机制，在同一交易内重复构造“协议向攻击者提现”和“回调从受害者扣款”的配对动作。由于访问控制 / 授权路径存在缺陷，攻击者能够让回调从非攻击者地址转出资产，最终形成高额第三方资金损失。

关键特征：

1. 顶层 sender 是最终最大获利地址。
2. 最大亏损地址不是 sender，也不是协议核心合约。
3. 同一个 token 在同一交易内存在大量相同金额的重复 `transfer` / `transferFrom` 对。
4. `transferFrom.from` 固定为第三方受害者，`transferFrom.to` 固定为协议核心合约。
5. `transfer.to` 固定为攻击者。
6. 每轮 `transferFrom` 金额与 `transfer` 金额相等。
7. 交易存在协议 callback 形态：`lock -> locked -> withdraw -> pay -> payCallback -> transferFrom`。
8. 资金最终净流向攻击者，净收益达到高美元价值。

## 检测器开发建议

### 策略一：Callback Drained Third-Party Asset Detector

目标：检测协议回调中从第三方账户扣款并最终流向交易发起者的高风险行为。

输入数据：

- trace call tree
- ERC20 Transfer 事件或 fund flow
- token decimals / USD value
- address label / protocol allowlist
- tx sender、top profit/loss address

核心逻辑：

1. 找出所有 ERC20 `transferFrom(from, to, amount)` 调用。
2. 过滤 `from != tx.sender` 且 `from != top_profit_address` 的记录。
3. 统计同一 token、同一 from、同一 to 在单笔交易内的累计金额。
4. 检查同一交易内是否存在同 token 从 `to` 或协议核心地址转给 `tx.sender/top_profit_address` 的 `transfer`。
5. 如果 `third_party_transferFrom_amount` 与 `profit_transfer_amount` 高度匹配，且 USD value 超过阈值，则告警。

推荐阈值：

- `third_party_transferFrom_count >= 3`：中风险
- `third_party_transferFrom_count >= 10`：高风险
- `usd_value >= 100_000`：高风险
- `usd_value >= 1_000_000`：严重
- `top_profit_address == tx.sender` 且 `top_loss_address != tx.sender`：加权

本事件命中：

- `transferFrom` 次数：85
- 第三方 from：`0x765decf4fa157756e850c1079f60801b9219edd1`
- 协议接收方：`0xe0e0e08a6a4b9dc7bd67bcb7aade5cf48157d444`
- 攻击者接收方：`0xa911ff351b143634dbc5af3e204ea074583a83e3`
- 净损失：约 1.38M USD

### 策略二：Repeated Equal-Amount Callback Loop Detector

目标：检测同一交易中高度重复的 callback/withdraw/payment 模式，尤其适用于批量循环利用型攻击。

特征提取：

- 对 trace call 按 `(callee, selector/name, normalized_args)` 分组计数。
- 对 ERC20 操作按 `(token, method, from/to, amount)` 分组计数。
- 提取重复的调用子序列，例如：
  - `lock -> locked -> withdraw -> transfer -> pay -> payCallback -> transferFrom`
  - `withdraw(token, recipient, amount)` 与 `transferFrom(victim, protocol, amount)` 成对出现

告警条件建议：

```text
repeat_count >= 10
AND unique_amount_count <= 2
AND token_transfer_value_usd >= 100_000
AND third_party_loss_address exists
AND profit_address receives same token in same tx
```

本事件命中：

- 85 轮重复
- 每轮 raw amount 均为 `20,000,000`
- 亏损方和获利方稳定
- 总价值超过 1M USD

### 策略三：Protocol Balance Pass-Through Detector

目标：检测协议核心合约在单笔交易内作为“资金中转站”的异常行为。

模式：

```text
victim -> protocol_core -> attacker
```

检测方法：

1. 从 fund flow 或 Transfer 事件构建 token-specific graph。
2. 查找长度为 2 的资金路径：`A -> P -> B`。
3. 要求：
   - `A != B`
   - `B == tx.sender` 或 `B == top_profit_address`
   - `P` 是已知协议核心合约或交易中高入度/高出度中间节点
   - `A` 是 top_loss_address
   - 两段金额在短路径内高度相等或累计接近
4. 当金额超过协议日常阈值或 USD 阈值时告警。

本事件中的路径：

```text
0x765decf4fa157756e850c1079f60801b9219edd1
  -> 0xe0e0e08a6a4b9dc7bd67bcb7aade5cf48157d444
  -> 0xa911ff351b143634dbc5af3e204ea074583a83e3
```

金额：17 WBTC。

### 策略四：Access-Control Anomaly Heuristic

目标：泛化检测“非授权主体导致第三方资产被转出”的访问控制类异常。

高价值信号：

- `tx.sender` 新地址或低 nonce。本事件 nonce = 1。
- `transferFrom.from` 不是 sender，也不是当前调用栈中已验证的 owner/operator。
- `transferFrom.spender/caller` 是临时 helper 合约或非白名单 callback 合约。
- 同一交易中存在高额第三方损失。
- calldata 中包含大量拼接参数或批处理 payload。
- protocol callback 被反复触发。

建议评分：

| 信号 | 分值 |
| --- | ---: |
| 第三方 `transferFrom` 总额 > 100k USD | +35 |
| 第三方 `transferFrom` 总额 > 1M USD | +55 |
| 同金额重复次数 >= 10 | +20 |
| tx.sender 为最大获利地址 | +15 |
| tx.sender nonce <= 3 | +10 |
| 存在协议 callback / lock / payCallback 结构 | +15 |
| top loss address != tx.sender | +10 |
| helper 合约/未知合约参与 callback | +10 |

建议严重级别：

- `score >= 80`：CRITICAL
- `score >= 60`：HIGH
- `score >= 40`：SUSPICIOUS

本事件评分预计超过 100，应判定为 CRITICAL。

## 推荐规则链设计

### 规则链 A：资金流优先

```text
AlertTrigger
  -> TokenTransferProvider
  -> FundFlowGraphBuilder
  -> TopProfitLossDetector
  -> ThirdPartyTransferFromDetector
  -> ProtocolPassThroughDetector
  -> RiskScoreAggregator
  -> NotifyWebhook / NotifyTelegram
```

适合实时检测，依赖 ERC20 Transfer 和基础 trace 即可。

### 规则链 B：Trace 模式优先

```text
AlertTrigger
  -> EVMTraceProvider
  -> RepeatedCallPatternDetector
  -> CallbackLoopDetector
  -> ThirdPartyTransferFromDetector
  -> RiskScoreAggregator
```

适合识别本事件这类重复 callback exploit，准确率更高，但依赖完整 trace。

### 规则链 C：混合策略

```text
AlertTrigger
  -> TokenTransferProvider
  -> EVMTraceProvider
  -> AddressProfileProvider
  -> ThirdPartyTransferFromDetector
  -> RepeatedEqualAmountLoopDetector
  -> ProtocolPassThroughDetector
  -> AccessControlAnomalyScorer
  -> SeverityRouter
```

建议作为新检测策略落地版本。

## Detector 输入/输出建议

### ThirdPartyTransferFromDetector

输入：

```json
{
  "tx_hash": "string",
  "sender": "address",
  "top_profit_address": "address",
  "top_loss_address": "address",
  "erc20_calls": [
    {
      "method": "transferFrom",
      "token": "address",
      "from": "address",
      "to": "address",
      "amount_raw": "string",
      "amount_decimal": "string",
      "usd_value": "number",
      "caller": "address"
    }
  ],
  "fund_flows": [],
  "trace_calls": []
}
```

输出：

```json
{
  "passed": true,
  "score": 85,
  "severity": "CRITICAL",
  "labels": [
    "third_party_transfer_from",
    "access_control_anomaly",
    "protocol_pass_through",
    "repeated_callback_loop"
  ],
  "evidence": {
    "token": "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",
    "victim": "0x765decf4fa157756e850c1079f60801b9219edd1",
    "profit_address": "0xa911ff351b143634dbc5af3e204ea074583a83e3",
    "protocol_core": "0xe0e0e08a6a4b9dc7bd67bcb7aade5cf48157d444",
    "repeat_count": 85,
    "amount": "17 WBTC",
    "usd_value": 1377396.49
  }
}
```

## 误报控制

可能误报场景：

1. 聚合器、路由器、清算机器人正常代表用户执行 `transferFrom`。
2. 用户主动授权协议合约批量转移资产。
3. 跨链桥、vault、staking 合约中存在正常的 `user -> protocol -> recipient` 流程。
4. DEX swap 中 `transferFrom(user, pool)` 与 `transfer(pool, user)` 正常成对出现。

降低误报的建议：

- 不仅看 `transferFrom`，必须结合 top profit/loss 和净收益。
- 要求 `top_profit_address` 与 `tx.sender` 或新建/低 nonce 地址一致。
- 对主流 router / vault / bridge 做 protocol-specific allowlist 或行为基线。
- 用“重复同金额次数”和“第三方净损失金额”作为强约束。
- 对正常 swap 的双向 token 交换做排除：如果用户损失 token A 同时收到等值 token B，不应判定为攻击。
- 对本事件类攻击，受害者只损失 WBTC，没有获得等价资产，是关键区别。

## 可落地的 MVP 检测逻辑

第一版可以先实现不依赖 ABI 名称的通用规则：

```python
for token in erc20_tokens:
    third_party_out = group transferFrom where from != tx.sender and from != top_profit_address
    profit_in = group transfer where to in {tx.sender, top_profit_address}

    for victim, protocol, amount_sum in third_party_out:
        matched_profit = profit_in[token].amount_to_profit
        if amount_sum.usd >= 100_000 and matched_profit / amount_sum >= 0.8:
            if repeat_count >= 3 or top_loss_address == victim:
                alert(CRITICAL if amount_sum.usd >= 1_000_000 else HIGH)
```

第二版再加入 trace 子序列检测：

```python
pattern = [
    "lock",
    "locked",
    "withdraw",
    "transfer",
    "pay",
    "payCallback",
    "transferFrom",
]

if repeated_subsequence_count(pattern) >= 10:
    score += 20
```

第三版加入协议画像：

- 协议核心地址的历史正常资金流范围。
- caller / callback 合约是否首次交互。
- sender nonce、地址年龄、是否刚部署 helper。
- 与已知协议函数名的组合关系。

## 本事件最小测试样本

建议把该交易作为回归 fixture，至少断言：

- 识别 `top_profit_address = 0xa911ff351b143634dbc5af3e204ea074583a83e3`
- 识别 `top_loss_address = 0x765decf4fa157756e850c1079f60801b9219edd1`
- 识别 WBTC 净流出 17
- 识别 `transferFrom(victim, Ekubo Core, 20,000,000)` 出现 85 次
- 识别 `transfer(attacker, 20,000,000)` 出现 85 次
- 识别重复 callback loop 次数 >= 80
- 输出 severity = CRITICAL

## 落地状态（2026-05-15）

已按资金流优先 MVP 落地标准检测器 `callback_third_party_drain`：

- 检测器文件：`nodes/detectors/callback_third_party_drain.py`
- 离线 fixture：`tests/fixtures/ekubo_callback_drain.py`
- 单元测试：`tests/nodes/test_detectors/test_callback_third_party_drain.py`
- 规则链回放测试：`tests/engine/test_ekubo_callback_drain_replay.py`

实现范围：从 `TransactionContext.extra` 读取 `erc20_calls`、`transfers`、`top_profit_address`、`top_loss_address`、`token_prices`、`token_decimals` 和可选 `trace_calls`，聚合第三方 `transferFrom(victim -> protocol)` 与同 token 的 `protocol -> tx.sender/top_profit` 转账，按金额匹配比例、重复次数、top loss/profit 和 callback loop 次数评分。本 Ekubo fixture 输出 `CRITICAL`，正常 router/swap fixture 不触发。

已通过针对性测试：

```bash
AlertProcessor/.venv/Scripts/python.exe -m pytest AlertProcessor/tests/nodes/test_detectors/test_callback_third_party_drain.py AlertProcessor/tests/engine/test_ekubo_callback_drain_replay.py -q
```

## 结论

这不是单纯的大额转账，而是“访问控制异常 + callback 循环 + 第三方授权扣款 + 协议中转出金”的组合型攻击。最值得开发的通用检测能力是：在单笔交易内关联 `transferFrom(third_party -> protocol)` 与 `transfer(protocol -> tx.sender/top_profit)`，并用重复次数、净损益、地址画像和 callback trace 模式加权评分。该策略可以覆盖本事件，也能泛化到其它利用协议回调或授权路径错误批量搬走第三方资产的攻击。
