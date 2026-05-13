# ScriptNode 最佳实践指南

## 概述

本指南提供 ScriptNode 脚本编写的最佳实践，帮助您编写高效、安全、可维护的检测脚本。

---

## 性能优化

### 1. 避免重复调用 API

**❌ 不好的做法**:
```python
for i in range(10):
    transfers = ctx.get_transfers()  # 每次循环都调用
    if len(transfers) > i:
        result = True
```

**✅ 好的做法**:
```python
transfers = ctx.get_transfers()  # 只调用一次
for i in range(10):
    if len(transfers) > i:
        result = True
```

### 2. 提前退出

**❌ 不好的做法**:
```python
transfers = ctx.get_transfers()
swaps = ctx.get_swaps()
calls = ctx.get_trace_calls()

# 即使没有转账也继续执行
if len(transfers) > 0:
    # 复杂计算...
    pass
```

**✅ 好的做法**:
```python
transfers = ctx.get_transfers()

if not transfers:
    result = False
    # 提前退出，避免后续计算

swaps = ctx.get_swaps()
calls = ctx.get_trace_calls()
# 复杂计算...
```

### 3. 使用缓存

`get_balance_changes()` 使用 `@cached_property` 自动缓存结果：

```python
# 第一次调用会计算
changes1 = ctx.get_balance_changes()

# 第二次调用直接返回缓存结果
changes2 = ctx.get_balance_changes()
```

### 4. 限制循环和嵌套

**❌ 不好的做法**:
```python
transfers = ctx.get_transfers()
swaps = ctx.get_swaps()

for t in transfers:
    for s in swaps:
        for c in ctx.get_trace_calls():  # O(n³) 复杂度
            # 处理...
            pass
```

**✅ 好的做法**:
```python
transfers = ctx.get_transfers()
swaps = ctx.get_swaps()
calls = ctx.get_trace_calls()

# 使用字典索引优化查找
transfer_by_token = {}
for t in transfers:
    token = t["token_address"]
    if token not in transfer_by_token:
        transfer_by_token[token] = []
    transfer_by_token[token].append(t)

# O(n) 复杂度
for s in swaps:
    token = s["token_in"]
    if token in transfer_by_token:
        # 处理...
        pass
```

---

## 安全编码

### 1. 处理缺失数据

**❌ 不好的做法**:
```python
transfers = ctx.get_transfers()
amount = transfers[0]["amount"]  # 可能抛出 IndexError 或 KeyError
```

**✅ 好的做法**:
```python
transfers = ctx.get_transfers()

if transfers:
    amount = transfers[0].get("amount", 0)  # 使用 get() 提供默认值
else:
    result = False
```

### 2. 类型转换

**❌ 不好的做法**:
```python
amount = int(transfer["amount"])  # 可能抛出 ValueError
```

**✅ 好的做法**:
```python
try:
    amount = float(transfer.get("amount", 0))
except (TypeError, ValueError):
    amount = 0.0
```

### 3. 地址比较

**❌ 不好的做法**:
```python
if address == "0xABC":  # 大小写敏感
    pass
```

**✅ 好的做法**:
```python
if address.lower() == "0xabc":  # 统一转小写
    pass
```

---

## 代码组织

### 1. 清晰的结构

```python
# 1. 获取数据
transfers = ctx.get_transfers()
swaps = ctx.get_swaps()

# 2. 提前退出
if not transfers:
    result = False
    score = 0
    # 退出

# 3. 数据处理
large_transfers = [t for t in transfers if t["amount"] > 100000]

# 4. 判断逻辑
if large_transfers:
    result = True
    score = 80
    labels = ["large_transfer"]
else:
    result = False
    score = 10
```

### 2. 使用有意义的变量名

**❌ 不好的做法**:
```python
t = ctx.get_transfers()
s = ctx.get_swaps()
x = sum(i["amount"] for i in t)
```

**✅ 好的做法**:
```python
transfers = ctx.get_transfers()
swaps = ctx.get_swaps()
total_transfer_amount = sum(t["amount"] for t in transfers)
```

### 3. 添加注释（仅在必要时）

```python
# 检查 Flash Loan 模式：大额借贷 + 多次 Swap + 高 ROI
large_borrows = [t for t in transfers if t["amount"] > 1000000]

if large_borrows and len(swaps) >= 2:
    roi = ctx.calculate_roi(total_in, total_out)
    
    # ROI > 5% 被认为是可疑的
    if roi > 5:
        result = True
```

---

## 常见错误

### 1. 忘记设置 result

**❌ 错误**:
```python
transfers = ctx.get_transfers()
score = 80
labels = ["test"]
# 忘记设置 result
```

**✅ 正确**:
```python
transfers = ctx.get_transfers()
result = True  # 必须设置
score = 80
labels = ["test"]
```

### 2. 除零错误

**❌ 错误**:
```python
roi = (inflow - outflow) / outflow  # outflow 可能为 0
```

**✅ 正确**:
```python
if outflow > 0:
    roi = ctx.calculate_roi(inflow, outflow)
else:
    roi = 0.0
```

### 3. 空列表索引

**❌ 错误**:
```python
transfers = ctx.get_transfers()
first_transfer = transfers[0]  # 可能为空
```

**✅ 正确**:
```python
transfers = ctx.get_transfers()
if transfers:
    first_transfer = transfers[0]
else:
    result = False
```

---

## 调试技巧

### 1. 使用 print 输出

```python
transfers = ctx.get_transfers()
print(f"Found {len(transfers)} transfers")  # 输出到调试面板

for t in transfers:
    print(f"Transfer: {t['amount']} from {t['from_address']}")
```

### 2. 记录中间结果到 ctx

```python
# 记录中间计算结果
ctx["debug_transfer_count"] = len(transfers)
ctx["debug_swap_count"] = len(swaps)
ctx["debug_roi"] = roi

result = True
score = 80
```

### 3. 分步验证

```python
# 步骤 1: 检查数据
transfers = ctx.get_transfers()
if not transfers:
    ctx["debug_step"] = "no_transfers"
    result = False

# 步骤 2: 过滤数据
large_transfers = [t for t in transfers if t["amount"] > 100000]
if not large_transfers:
    ctx["debug_step"] = "no_large_transfers"
    result = False

# 步骤 3: 计算指标
ctx["debug_step"] = "calculating_roi"
roi = ctx.calculate_roi(inflow, outflow)
```

---

## 脚本模板

### 基础检测模板

```python
"""
[脚本名称]

检测特征：
1. 特征 1
2. 特征 2
3. 特征 3
"""

# 1. 获取数据
data = ctx.get_xxx()

# 2. 提前退出
if not data:
    result = False
    score = 0
    # 退出

# 3. 数据处理和分析
suspicious_items = [item for item in data if condition]

# 4. 判断和评分
if suspicious_items:
    result = True
    score = 80
    labels = ["label1", "label2"]
    ctx["details"] = suspicious_items
else:
    result = False
    score = 10
```

### 多条件检测模板

```python
"""
多条件检测模板
"""

# 获取数据
transfers = ctx.get_transfers()
swaps = ctx.get_swaps()

# 初始化
result = False
score = 0
labels = []

# 条件 1: 大额转账
if any(t["amount"] > 100000 for t in transfers):
    score += 30
    labels.append("large_transfer")

# 条件 2: 多次 Swap
if len(swaps) > 5:
    score += 30
    labels.append("multiple_swaps")

# 条件 3: 高 ROI
roi = ctx.calculate_roi(inflow, outflow)
if roi > 10:
    score += 40
    labels.append("high_roi")

# 最终判断
if score >= 60:
    result = True
else:
    result = False
```

### 时序模式检测模板

```python
"""
时序模式检测模板
"""

# 获取调用栈
calls = ctx.get_trace_calls()

# 定义模式
pattern = [
    "0x5cffe9de",  # borrow
    "0x022c0d9f",  # swap
    "0x0902f1ac",  # repay
]

# 匹配模式
matches = ctx.match_sequence(calls, pattern)

if matches:
    result = True
    score = 90
    labels = ["pattern_detected"]
    ctx["matches"] = matches
else:
    result = False
    score = 0
```

---

## 性能基准

### 目标性能指标

- **执行时间**: < 1 秒（简单脚本）, < 5 秒（复杂脚本）
- **内存使用**: < 50MB（简单脚本）, < 100MB（复杂脚本）
- **API 调用**: < 10 次（避免过多调用）

### 性能测试

```python
import time

start = time.time()

# 你的脚本逻辑
transfers = ctx.get_transfers()
# ...

execution_time = time.time() - start
ctx["execution_time"] = execution_time

if execution_time > 5.0:
    print(f"Warning: Script took {execution_time:.2f}s")
```

---

## 安全限制

### 允许的操作

- ✅ 读取交易数据（`ctx.get_xxx()`）
- ✅ 使用工具函数（`ctx.calculate_xxx()`, `ctx.match_xxx()`）
- ✅ 导入安全模块（`re`, `json`, `math`, `datetime`）
- ✅ 基础数据处理（列表推导、字典操作）

### 禁止的操作

- ❌ 文件访问（`open`, `read`, `write`）
- ❌ 网络访问（`requests`, `urllib`）
- ❌ 执行外部命令（`os.system`, `subprocess`）
- ❌ 导入危险模块（`os`, `sys`, `subprocess`）
- ❌ 修改全局状态
- ❌ 无限循环（会触发超时）

---

## 测试建议

### 1. 单元测试

为脚本创建单元测试：

```python
# tests/scripts/test_flash_loan_detector.py

import pytest
from engine.script_sandbox import ScriptSandbox
from engine.script_context import ScriptContext
from nodes.models import TransactionContext

def test_flash_loan_detector():
    script = open("examples/scripts/flash_loan_detector.py").read()
    
    tx_context = TransactionContext(
        chain_id="1",
        tx_hash="0xabc",
        block_number=100,
        timestamp=1000000,
        from_address="0xsender",
        to_address="0xcontract",
        value="0",
        logs=[],
        extra={
            "parsed_transfers": [...],
            "parsed_swaps": [...],
        },
    )
    
    ctx = ScriptContext(tx_context)
    sandbox = ScriptSandbox(return_namespace=True)
    
    result = sandbox.execute(script, {"ctx": ctx})
    
    assert result["result"] is True
    assert result["score"] >= 80
    assert "flash_loan" in result["labels"]
```

### 2. 集成测试

在完整规则链中测试脚本：

```python
chain_config = {
    "nodes": [
        {"id": "trigger", "type": "alert_trigger"},
        {
            "id": "script",
            "type": "script_node",
            "config": {
                "language": "python",
                "script": open("examples/scripts/flash_loan_detector.py").read(),
            },
        },
    ],
    "edges": [{"from": "trigger", "to": "script"}],
}

executor = ChainExecutor(chain)
results = await executor.execute(tx_context)

assert results["script"].passed is True
```

---

## 常见问题

### Q: 脚本超时怎么办？

A: 优化脚本性能：
- 减少 API 调用次数
- 避免嵌套循环
- 提前退出
- 限制数据处理量

### Q: 如何调试脚本？

A: 使用以下方法：
- 使用 `print()` 输出调试信息
- 将中间结果存储到 `ctx`
- 在本地环境运行单元测试
- 使用前端调试面板

### Q: 脚本可以访问外部 API 吗？

A: 不可以。ScriptNode 在沙箱中运行，禁止网络访问。所有数据必须通过 `ctx` 获取。

### Q: 如何处理大数据集？

A: 使用以下策略：
- 提前过滤数据
- 使用生成器而非列表
- 限制处理数量
- 使用缓存

```python
# 限制处理数量
transfers = ctx.get_transfers()[:100]  # 只处理前 100 个

# 使用生成器
large_transfers = (t for t in transfers if t["amount"] > 100000)
first_large = next(large_transfers, None)
```

---

## 总结

遵循这些最佳实践可以帮助您：

1. **提高性能**: 减少执行时间和内存使用
2. **增强安全性**: 避免常见错误和安全问题
3. **提升可维护性**: 代码清晰易懂，便于调试
4. **确保可靠性**: 处理边界情况，避免崩溃

记住：**简单、清晰、高效** 是编写优秀检测脚本的关键。
