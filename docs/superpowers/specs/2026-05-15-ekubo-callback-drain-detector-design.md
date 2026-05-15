# ThirdPartyCallbackDrainDetector 设计

## 背景

Ekubo Protocol 攻击交易 `0x770bc9a1f7c32cb63a5002b9ceb5c7994cd3af0fc6b2309cb32d3c46f629daa0` 呈现典型的第三方资产扣款 + 协议中转 + 攻击者获利模式。交易中 85 次重复执行 `transferFrom(victim -> protocol)` 与 `transfer(protocol -> attacker)`，累计造成 17 WBTC 损失。

## 目标

实现标准检测器 `callback_third_party_drain`，用于识别同一交易内由第三方地址流入协议、再由协议流向交易发送者或最大获利地址的高风险闭环。检测器应能通过离线 fixture 回放命中 Ekubo 交易，并避免把正常 router/swap 行为误判为攻击。

## 架构

新增文件：

- `nodes/detectors/callback_third_party_drain.py`
- `tests/fixtures/ekubo_callback_drain.py`
- `tests/nodes/test_detectors/test_callback_third_party_drain.py`
- `tests/engine/test_ekubo_callback_drain_replay.py`

检测器继承现有 `BaseDetector`，遵循 detector 节点约定，注册到 `NodeRegistry` 并从 `nodes/detectors/__init__.py` 导出。

## 输入数据

检测器从 `TransactionContext.extra` 读取：

- `erc20_calls`：标准化 ERC20 调用摘要，至少包含 `method`、`token`、`from`、`to`、`amount_raw`、`caller`。
- `transfers`：标准化 fund-flow / Transfer 事件，至少包含 `token`、`from`、`to`、`amount_raw`。
- `top_profit_address`、`top_loss_address`。
- `token_prices`、`token_decimals`。
- `trace_calls`：可选，用于识别 callback loop 名称序列。

fixture 只固化检测所需摘要，不保存完整 2555 条 trace。

## 检测逻辑

1. 聚合所有 `transferFrom`，过滤 `from == tx.sender` 或 `from == top_profit_address` 的正常自有资金流。
2. 按 `(token, victim, protocol)` 统计第三方转出金额和次数。
3. 聚合同 token 下转给 `tx.sender` 或 `top_profit_address` 的 `transfer` / fund-flow。
4. 若第三方转出金额与攻击者获利金额匹配比例达到阈值，则生成候选。
5. 根据金额、重复次数、top loss/profit、callback loop 命中情况计算分数。

默认阈值：

- `min_repeat_count = 3`
- `critical_repeat_count = 10`
- `min_usd_value = 100_000`
- `critical_usd_value = 1_000_000`
- `min_match_ratio = 0.8`

## 输出

命中时输出：

- `passed = True`
- `severity = CRITICAL/HIGH/SUSPICIOUS`
- `labels`：`third_party_transfer_from`、`protocol_pass_through`、`callback_drain`、`access_control_anomaly`
- `detection_details` / `evidence`：victim、profit address、protocol、token、repeat_count、amount、usd_value、matched_ratio、callback_loop_count。

未命中时输出 `passed = False`，保留低分和说明。

## 测试策略

严格 TDD：

1. 先写 Ekubo 单元测试，确认缺少 detector 时失败。
2. 实现最小 detector 使 Ekubo fixture 输出 CRITICAL。
3. 写正常 router/swap 误报测试，确认失败后补充排除逻辑。
4. 写规则链回放测试，使用离线 fixture 构造 `TransactionContext` 并执行 detector 节点，断言命中和证据字段。

## 非目标

- 不联网拉取 Phalcon 数据。
- 不实现完整 Ethereum trace parser。
- 不把所有访问控制漏洞都一次性覆盖。
- 不修改现有 fund_drain detector 的职责。
