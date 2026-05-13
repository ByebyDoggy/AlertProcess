# ScriptContext API 完整参考

## 概述

`ScriptContext` 是 ScriptNode 中用户脚本的核心 API，提供安全、稳定、易用的交易数据访问和工具函数。

## 基础用法

```python
# 脚本入口
# ctx: ScriptContext 实例
# inputs: 上游节点输出字典

# 访问交易数据
transfers = ctx.get_transfers()
swaps = ctx.get_swaps()
calls = ctx.get_trace_calls()

# 使用工具函数
roi = ctx.calculate_roi(inflow=1000, outflow=500)
price_impact = ctx.calculate_price_impact(1000000, 1000000, 10000)

# 设置输出
result = True
score = 80
labels = ["flash_loan", "high_risk"]
```

---

## 数据访问 API

### get_trace_calls(min_depth=0)

获取标准化 ETH 调用栈。

**参数**:
- `min_depth` (int): 最小调用深度，0 表示顶层调用

**返回**: `list[dict]`

每个调用包含：
- `depth` (int): 调用深度
- `from_addr` (str): 调用方地址
- `to_addr` (str): 被调用方地址
- `function_selector` (str): 函数选择器（如 "0xa9059cbb"）
- `call_type` (str): 调用类型（call/delegatecall/staticcall）
- `value` (str): 转账金额（Wei）
- `gas` (str): Gas 限制
- `input_data` (str): 完整输入数据
- `trace_address` (list): 调用路径

**示例**:
```python
# 获取所有调用
all_calls = ctx.get_trace_calls()

# 只获取深度 >= 1 的调用（排除顶层）
nested_calls = ctx.get_trace_calls(min_depth=1)

# 检查是否有 delegatecall
has_delegatecall = any(c["call_type"] == "delegatecall" for c in all_calls)
```

---

### get_event_logs(event_signature=None)

获取事件日志。

**参数**:
- `event_signature` (str, optional): 事件签名或 topic0
  - 可以是事件签名文本：`"Transfer(address,address,uint256)"`
  - 可以是 topic0 哈希：`"0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"`
  - 为 None 时返回所有日志

**返回**: `list[dict]`

**示例**:
```python
# 获取所有日志
all_logs = ctx.get_event_logs()

# 获取 Transfer 事件
transfers = ctx.get_event_logs("Transfer(address,address,uint256)")

# 使用 topic0
transfers = ctx.get_event_logs("0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef")
```

---

### get_transfers(token_address=None)

获取代币转账记录（优先使用 LogParserProvider 的 parsed_transfers）。

**参数**:
- `token_address` (str, optional): 代币地址过滤

**返回**: `list[dict]`

每个转账包含：
- `token_address` (str): 代币地址
- `from_address` (str): 发送方
- `to_address` (str): 接收方
- `amount` (float): 转账金额
- `value_usd` (float, optional): USD 价值

**示例**:
```python
# 获取所有转账
all_transfers = ctx.get_transfers()

# 获取特定代币转账
usdt_transfers = ctx.get_transfers("0xdac17f958d2ee523a2206206994597c13d831ec7")

# 计算总转账金额
total_amount = sum(t["amount"] for t in all_transfers)
```

---

### get_swaps()

获取 Swap 事件（优先使用 LogParserProvider 的 parsed_swaps）。

**返回**: `list[dict]`

每个 Swap 包含：
- `token_in` (str): 输入代币地址
- `token_out` (str): 输出代币地址
- `amount_in` (float): 输入金额
- `amount_out` (float): 输出金额
- `sender` (str): 发送方
- `recipient` (str): 接收方

**示例**:
```python
swaps = ctx.get_swaps()

# 检查是否有大额 Swap
large_swaps = [s for s in swaps if s["amount_in"] > 1000000]

# 计算总交易量
total_volume = sum(s["amount_in"] for s in swaps)
```

---

### get_approvals()

获取 Approval 事件（优先使用 LogParserProvider 的 parsed_approvals）。

**返回**: `list[dict]`

每个 Approval 包含：
- `token_address` (str): 代币地址
- `owner` (str): 所有者
- `spender` (str): 被授权方
- `amount` (float): 授权金额

**示例**:
```python
approvals = ctx.get_approvals()

# 检查无限授权
unlimited_approvals = [
    a for a in approvals 
    if a["amount"] > 2**255
]

# 检查高风险授权
risky_spenders = ["0xmalicious1", "0xmalicious2"]
risky_approvals = [
    a for a in approvals 
    if a["spender"].lower() in risky_spenders
]
```

---

### get_balance_changes(address=None, token_address=None)

获取余额变化（基于转账记录计算，支持缓存）。

**参数**:
- `address` (str, optional): 地址过滤
- `token_address` (str, optional): 代币地址过滤

**返回**: `dict[str, dict[str, float]]`

格式：
```python
{
    "token_address": {
        "address": balance_change  # 正数表示增加，负数表示减少
    }
}
```

**示例**:
```python
# 获取所有余额变化
all_changes = ctx.get_balance_changes()

# 获取特定地址的余额变化
alice_changes = ctx.get_balance_changes(address="0xalice")

# 获取特定代币的余额变化
usdt_changes = ctx.get_balance_changes(token_address="0xusdt")

# 检查是否有地址余额大幅增加
for token, addr_changes in all_changes.items():
    for addr, change in addr_changes.items():
        if change > 1000000:
            result = True
            score = 90
            labels = ["large_balance_increase"]
```

---

### get_token_price(token_address)

从 Provider 注入的 token_prices 中获取代币价格。

**参数**:
- `token_address` (str): 代币地址

**返回**: `float` - USD 价格

**示例**:
```python
eth_price = ctx.get_token_price("0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2")
usdt_price = ctx.get_token_price("0xdac17f958d2ee523a2206206994597c13d831ec7")

# 计算转账的 USD 价值
transfers = ctx.get_transfers()
total_value_usd = 0
for t in transfers:
    price = ctx.get_token_price(t["token_address"])
    total_value_usd += t["amount"] * price
```

---

### get_input_outputs(port=None)

获取上游节点输出。

**参数**:
- `port` (str, optional): 端口名称，为 None 时返回所有输入

**返回**: `list[NodeOutput]`

**示例**:
```python
# 获取所有上游输出
all_inputs = ctx.get_input_outputs()

# 获取特定端口的输出
detector_outputs = ctx.get_input_outputs(port="detector")

# 检查上游是否有告警
has_alert = any(output.passed for output in all_inputs)
```

---

## 工具函数 API

### decode_function_selector(selector)

解码函数选择器（优先使用本地签名表）。

**参数**:
- `selector` (str): 函数选择器（如 "0xa9059cbb"）

**返回**: `str` - 函数签名（如 "transfer(address,uint256)"）

**示例**:
```python
calls = ctx.get_trace_calls()
for call in calls:
    selector = call["function_selector"]
    signature = ctx.decode_function_selector(selector)
    if "withdraw" in signature.lower():
        result = True
        labels = ["withdrawal_detected"]
```

---

### calculate_roi(inflow, outflow)

计算 ROI 百分比。

**参数**:
- `inflow` (float): 流入金额（USD）
- `outflow` (float): 流出金额（USD）

**返回**: `float` - ROI 百分比（如 150.5 表示 150.5%）

**示例**:
```python
# Flash Loan ROI 计算
borrowed = 1000000
repaid = 1005000
profit = repaid - borrowed

roi = ctx.calculate_roi(profit, borrowed)

if roi > 10:
    result = True
    score = 90
    labels = ["high_roi_flash_loan"]
```

---

### calculate_price_impact(reserve_in, reserve_out, amount_in, fee_rate=0.003)

计算 AMM 价格影响（基于恒定乘积公式）。

**参数**:
- `reserve_in` (float): 输入代币储备量
- `reserve_out` (float): 输出代币储备量
- `amount_in` (float): 输入代币数量
- `fee_rate` (float): 手续费率（默认 0.003 即 0.3%）

**返回**: `float` - 价格影响百分比（负数表示价格下跌）

**示例**:
```python
# 检测价格操纵
swaps = ctx.get_swaps()
for swap in swaps:
    # 假设从 extra 中获取储备量
    reserve_in = swap.get("reserve_in", 0)
    reserve_out = swap.get("reserve_out", 0)
    amount_in = swap["amount_in"]
    
    impact = ctx.calculate_price_impact(reserve_in, reserve_out, amount_in)
    
    if abs(impact) > 10:  # 价格影响超过 10%
        result = True
        score = 85
        labels = ["high_price_impact", "potential_manipulation"]
```

---

### match_pattern(pattern, text)

正则匹配工具。

**参数**:
- `pattern` (str): 正则表达式
- `text` (str): 待匹配文本

**返回**: `bool` - 是否匹配

**示例**:
```python
calls = ctx.get_trace_calls()
for call in calls:
    signature = ctx.decode_function_selector(call["function_selector"])
    
    # 匹配危险函数
    if ctx.match_pattern(r"(selfdestruct|delegatecall|suicide)", signature):
        result = True
        score = 95
        labels = ["dangerous_function"]
```

---

### match_sequence(events, pattern)

时序模式匹配（按事件 type/name/function_selector 字段匹配有序序列）。

**参数**:
- `events` (list[dict]): 事件列表
- `pattern` (list[str]): 模式列表（函数选择器或事件名称序列）

**返回**: `list[dict]` - 匹配结果列表

每个匹配包含：
- `start_index` (int): 起始索引
- `end_index` (int): 结束索引
- `events` (list[dict]): 匹配的事件列表

**示例**:
```python
# 检测 Flash Loan 攻击模式
calls = ctx.get_trace_calls()

# 模式：borrow -> swap -> swap -> repay
flash_loan_pattern = [
    "0x5cffe9de",  # borrow
    "0x022c0d9f",  # swap
    "0x022c0d9f",  # swap
    "0x0902f1ac",  # repay
]

matches = ctx.match_sequence(calls, flash_loan_pattern)

if matches:
    result = True
    score = 90
    labels = ["flash_loan_attack_pattern"]
```

---

### detect_reentrancy(target_contract=None)

检测重入模式（同一合约在调用栈中多次出现）。

**参数**:
- `target_contract` (str, optional): 目标合约地址，为 None 时检测所有合约

**返回**: `list[dict]` - 重入模式列表

每个模式包含：
- `contract` (str): 合约地址
- `depths` (list[int]): 出现的调用深度列表
- `call_indices` (list[int]): 调用索引列表
- `pattern` (str): 模式类型（如 "nested_call"）

**示例**:
```python
# 检测重入攻击
reentrancy_patterns = ctx.detect_reentrancy()

if reentrancy_patterns:
    result = True
    score = 95
    labels = ["reentrancy_detected"]
    
    # 检查特定合约
    for pattern in reentrancy_patterns:
        if pattern["contract"] == "0xvictim":
            score = 100
            labels.append("critical_reentrancy")

# 只检测特定合约
victim_reentrancy = ctx.detect_reentrancy(target_contract="0xvictim")
```

---

## 上下文变量

### ctx (dict)

脚本可以使用 `ctx` 字典在脚本内部或跨节点传递数据。

**示例**:
```python
# 在脚本中设置变量
ctx["stage1_done"] = True
ctx["risk_level"] = "high"
ctx["suspicious_addresses"] = ["0xabc", "0xdef"]

# 在后续脚本中读取
if ctx.get("stage1_done"):
    risk_level = ctx.get("risk_level", "low")
    addresses = ctx.get("suspicious_addresses", [])
```

---

## 输出变量

脚本可以设置以下变量来控制节点输出：

### result (bool)

检测结果，`True` 表示通过，`False` 表示不通过。

```python
result = True  # 检测通过
```

### score (int)

风险评分（0-100）。

```python
score = 80  # 高风险
```

### labels (list[str])

标签列表。

```python
labels = ["flash_loan", "high_roi", "suspicious"]
```

### ctx (dict)

上下文变量（可选）。

```python
ctx["custom_data"] = {"key": "value"}
```

---

## 完整示例

### Flash Loan 检测

```python
# 获取转账和 Swap
transfers = ctx.get_transfers()
swaps = ctx.get_swaps()

# 检查是否有大额借贷
large_borrows = [t for t in transfers if t["amount"] > 1000000]

if large_borrows and swaps:
    # 计算 ROI
    total_in = sum(t["amount"] for t in transfers if t["to_address"] == ctx.tx_context.from_address)
    total_out = sum(t["amount"] for t in transfers if t["from_address"] == ctx.tx_context.from_address)
    
    roi = ctx.calculate_roi(total_in, total_out)
    
    if roi > 5:
        result = True
        score = 85
        labels = ["flash_loan", "high_roi"]
        ctx["flash_loan_roi"] = roi
    else:
        result = False
else:
    result = False
```

### 价格操纵检测

```python
swaps = ctx.get_swaps()

for swap in swaps:
    # 假设从 extra 获取储备量
    reserve_in = swap.get("reserve_in", 0)
    reserve_out = swap.get("reserve_out", 0)
    
    if reserve_in > 0 and reserve_out > 0:
        impact = ctx.calculate_price_impact(
            reserve_in, 
            reserve_out, 
            swap["amount_in"]
        )
        
        if abs(impact) > 10:
            result = True
            score = 90
            labels = ["price_manipulation", "high_impact"]
            ctx["price_impact"] = impact
            break
else:
    result = False
```

### 重入攻击检测

```python
# 检测重入模式
reentrancy = ctx.detect_reentrancy()

if reentrancy:
    result = True
    score = 95
    labels = ["reentrancy_attack"]
    
    # 检查是否有多层嵌套
    max_depth = max(max(p["depths"]) for p in reentrancy)
    if max_depth > 3:
        score = 100
        labels.append("deep_reentrancy")
    
    ctx["reentrancy_patterns"] = reentrancy
else:
    result = False
```

### 资金流向分析

```python
# 获取余额变化
balance_changes = ctx.get_balance_changes()

# 找出余额增加最多的地址
max_gain = 0
max_gain_address = None

for token, addr_changes in balance_changes.items():
    for addr, change in addr_changes.items():
        if change > max_gain:
            max_gain = change
            max_gain_address = addr

if max_gain > 100000:
    result = True
    score = 80
    labels = ["large_fund_flow"]
    ctx["beneficiary"] = max_gain_address
    ctx["gain_amount"] = max_gain
else:
    result = False
```

---

## 性能优化建议

1. **使用缓存**: `get_balance_changes()` 使用 `@cached_property` 缓存计算结果
2. **避免重复调用**: 将常用数据存储在变量中
3. **提前退出**: 使用 `if` 条件提前返回，避免不必要的计算
4. **限制循环**: 避免在大数据集上进行嵌套循环

```python
# 好的做法
transfers = ctx.get_transfers()  # 只调用一次
if not transfers:
    result = False
    # 提前退出，避免后续计算

# 不好的做法
for i in range(100):
    transfers = ctx.get_transfers()  # 重复调用
```

---

## 安全限制

ScriptNode 在沙箱中执行，有以下限制：

- ❌ 禁止文件访问（`open`, `read`, `write`）
- ❌ 禁止网络访问（`requests`, `urllib`）
- ❌ 禁止执行外部命令（`os.system`, `subprocess`）
- ❌ 禁止导入危险模块（`os`, `sys`, `subprocess`）
- ✅ 允许导入安全模块（`re`, `json`, `math`, `datetime`）
- ✅ 超时限制（默认 5 秒）
- ✅ 内存限制（默认 100MB）
