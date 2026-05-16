# JUDAO Token Contract Active LP Drain Detector 设计

## 背景

JUDAO Token 攻击交易 `0x956e38b8ddb40ba080c8042c685ae52ee5c1b096f1d7f0c4a6c59be3eb4265bd` 展现出“闪电贷 + LP 作为 top loss + token 合约自身主动参与资金流/调用流 + sender 获得稳定币/原生币利润”的业务逻辑漏洞模式。

该事件不应做成 JUDAO 专用检测器，也不应重复实现已有闪电贷、价格操纵或通用经济异常能力。新增检测器只覆盖一个窄职责信号：token 合约自身作为 active participant 参与 LP drain。

## 目标

实现标准检测器 `token_contract_active_lp_drain`，用于识别 DEX LP 发生高额净损失时，被交易 token 合约自身同时满足资金流和调用流活跃参与，并且 sender 或相关获利地址获得稳定币/原生币利润的模式。

检测器应通过 JUDAO 离线 fixture 命中 CRITICAL，并通过正常 fee-on-transfer / 项目方加池或回购类 fixture 证明不会因 token 合约与 LP 有普通资金往返而误报。

## 复用边界

复用已有能力：

- `FlashLoanTraceDetector`：负责识别 flash loan 借款、回调和回调后利用动作。
- `EconomicAnomalyDetector`：负责识别 ERC20 Transfer、Swap、burn/mint、ROI 等通用经济异常。
- `PriceManipulationDetector`：负责识别 swap 后 drain、LP 操作和价格偏移。
- Top profit/loss 与 fund-flow provider：负责给出 `top_profit_address`、`top_loss_address` 和 normalized transfers。

新增检测器不重复实现：

- flash loan 协议签名库；
- 通用 swap / reserve 价格偏移计算；
- 全量 LP drain 检测；
- 任意 tokenomics 税费逻辑识别。

新增检测器只判断：

> 在 LP 为主要受损方的交易中，LP 相关 token 合约是否从被动资产变成主动资金流/调用流参与者，并与 sender 利润同时出现。

## 文件规划

新增：

- `nodes/detectors/token_contract_active_lp_drain.py`
- `tests/fixtures/judao_token_active_lp_drain.py`
- `tests/nodes/test_detectors/test_token_contract_active_lp_drain.py`
- `tests/engine/test_judao_token_active_lp_drain_replay.py`

修改：

- `nodes/detectors/__init__.py`
- `docs/JUDAO_TOKEN_DETECTOR_STRATEGY.md`，实现完成后追加落地状态。

## 输入数据

检测器从 `TransactionContext.extra` 读取：

- `transfers`：normalized fund-flow / Transfer 摘要。
  - `token`
  - `from`
  - `to`
  - `amount_raw` 或 `amount`
- `trace_calls`：normalized trace 摘要。
  - `caller`
  - `callee`
  - `selector`
  - `operation`
- `top_profit_address`
- `top_loss_address`
- `token_prices`
- `token_decimals`
- 可选：
  - `address_labels`
  - `stablecoins`
  - `wrapped_native_tokens`
  - `flash_loan_present`
  - `temporary_contract_count`

fixture 使用 `DetectorInputMixin.from_dict(...)` 构造输入，确保非标准字段进入 `TransactionContext.extra`。

## 检测逻辑

### 1. 识别 LP 候选

默认将 `top_loss_address` 作为 LP 候选，但必须满足至少一个 LP 证据：

- address label 包含 `lp`、`pair`、`cake-lp`；
- trace 中该地址被调用 `getReserves` selector `0x0902f1ac`；
- trace 中该地址被调用 Pair `swap` selector `0x022c0d9f`；
- transfers 中该地址同时出现多个 token 的大额出入。

若无法证明 top loss 是 LP，则不触发。

### 2. 识别 LP 相关 token contract 候选

从所有涉及 LP 的 transfers 中提取非稳定币、非 wrapped native token 的 token 地址，作为 token contract 候选。

默认 stable / wrapped native 集合包括：

- BSC USDT：`0x55d398326f99059ff775485246999027b3197955`
- BSC WBNB：`0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c`
- native placeholder：`0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee`

也允许 fixture 通过 `stablecoins` / `wrapped_native_tokens` 扩展。

### 3. 计算 LP 净损失与 sender 利润

按 token 聚合目标地址的净流入 / 净流出：

- 对 LP：流入为正，流出为负；净负值转为 `lp_loss_raw_by_token`。
- 对 sender：流入为正，流出为负；正值转为 `sender_profit_raw_by_token`。

使用 `token_prices` 和 `token_decimals` 估算 USD。

触发阈值：

- `min_lp_loss_usd = 100_000`
- `critical_lp_loss_usd = 1_000_000`
- `min_sender_profit_usd = 10_000`

### 4. 判断 token contract active participation

候选 token contract 满足以下条件时视为 active：

资金流活跃：

- token contract 是 LP 大额转账接收方；或
- token contract 是 LP 大额转账发送方；或
- token contract 向非 LP 地址发送稳定币 / wrapped native；或
- token contract 是 `top_profit_address`。

调用流活跃：

- trace 中 token contract 作为 `caller` 调用 Router、LP 或 ERC20 token；或
- trace 中 token contract 作为 `caller` 调用任意合约次数达到 `min_token_contract_call_count`。

MVP 判定：

```text
LP confirmed
AND lp_loss_usd >= min_lp_loss_usd
AND sender_profit_usd >= min_sender_profit_usd
AND candidate token exists
AND (
  token == top_profit_address
  OR (active_in_fund_flow AND active_as_caller)
)
```

### 5. 加权信号

以下只加权，不作为硬触发：

- `flash_loan_present = true` 或 trace 中出现 flash loan selector `0xe0232b42`。
- `temporary_contract_count >= 1` 或 trace 中出现 `CREATE`。
- LP 被多次 `getReserves` / `balanceOf` 查询。
- Pair `swap` 次数 >= 2。

## 评分

| 信号 | 分值 |
| --- | ---: |
| top loss 被确认是 DEX LP | +20 |
| LP 净损失 >= 100k USD | +25 |
| LP 净损失 >= 1M USD | +20 |
| token contract 是 top profit | +20 |
| token contract 参与 LP 相关资金流 | +15 |
| token contract 作为 caller 参与调用流 | +15 |
| sender 稳定币/原生币利润 >= 10k USD | +15 |
| 闪电贷存在 | +10 |
| 临时合约存在 | +10 |

分数上限 100。

严重级别使用现有 `score_to_severity`。

## 输出

命中时输出：

- `passed = True`
- `severity = CRITICAL/HIGH/SUSPICIOUS`
- `labels`：
  - `token_contract_active_lp_drain`
  - `lp_top_loss`
  - `token_contract_top_profit`，仅 token == top_profit 时添加
  - `business_logic_anomaly`
  - `flash_loan_amplified`，仅 flash loan 存在时添加
  - `temporary_contract_execution`，仅临时合约存在时添加

`detection.evidence` 包含：

- `token_contract`
- `lp_address`
- `sender_profit_address`
- `top_profit_address`
- `lp_loss_usd`
- `sender_profit_usd`
- `lp_loss_raw_by_token`
- `sender_profit_raw_by_token`
- `token_contract_fund_flow_count`
- `token_contract_call_count`
- `pair_swap_count`
- `reserve_read_count`
- `flash_loan_present`
- `temporary_contract_count`

未命中时输出低分、空 labels 和 reason。

## 测试策略

严格 TDD：

1. 写 JUDAO fixture 和直接 detector 测试，先确认缺少 detector 时 `ModuleNotFoundError` 或 registry 失败。
2. 实现最小 detector，使 JUDAO fixture 输出 CRITICAL。
3. 写正常 fee-on-transfer / 项目方加池 fixture，确认不会因 token 合约与 LP 普通资金往返触发。
4. 写规则链回放测试，使用 `AlertTrigger -> token_contract_active_lp_drain` 最小链，断言输出、severity、labels 和 evidence。
5. 聚焦运行新增 detector 和 replay tests。

## 非目标

- 不联网拉取 Phalcon 数据。
- 不解析完整 raw trace，只使用离线 normalized fixture。
- 不替代 `FlashLoanTraceDetector`、`EconomicAnomalyDetector` 或 `PriceManipulationDetector`。
- 不对所有 fee-on-transfer token 做语义分类。
- 不把 JUDAO 地址写入 production detector。
