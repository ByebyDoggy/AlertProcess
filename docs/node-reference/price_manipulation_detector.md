# 价格操纵检测

- **节点名称**: `price_manipulation_detector`
- **分类**: 安全检测 (`detection`)
- **基类**: `BaseDetector`
- **模块**: `nodes.detectors.price_manipulation`

## 描述

[数据需求: Logs] 检测现货价格操纵类攻击：单区块极端价格偏移(同一池同一交易内价格变化>10%)、大额Swap后紧接大额代币转出(Swap→Drain)、LP流动性操作后异常资金转出。主要依赖标准DEX Swap事件和ERC-20 Transfer事件，不依赖函数签名，适用于闪电贷价格操纵、预言机操纵等攻击场景

## 输入端口

| Key | 标签 | 数据类型 | 必填 | 多输入 | 说明 |
|-----|------|---------|------|--------|------|
| `input` | 输入 | `context` | &#10003; | - |  |
| `storage_input` | 外部存储 | `context` | - | - |  |

### 输入 输入模型字段

| 字段 | 类型 | 必填 | 说明 | 默认值 |
|------|------|------|------|--------|
| `chain_id` | integer | - | 区块链网络 ID（1=ETH, 56=BSC, 137=MATIC） | `1` |
| `tx_hash` | string | - | 交易的唯一哈希值 | `` |
| `block_number` | integer | - | 交易所在区块号 | `0` |
| `from_address` | string | - | 交易发起者 (from) 地址 | `` |
| `to_address` | string | - | 交易目标 (to) 地址，空=合约创建 | `` |
| `value` | integer | - | 原生代币转账金额（wei 单位） | `0` |
| `gas_price` | integer | - | 单位 Gas 价格（wei） | `0` |
| `gas_used` | integer | - | 交易消耗的 Gas 总量 | `0` |
| `input_data` | string | - | 交易的 calldata / 方法签名+参数 | `` |
| `timestamp` | string | - | 交易发生时间 (ISO8601) | `` |
| `logs` | array | - | 交易产生的 Event Log 列表 | - |
| `extra` | object | - | 扩展上下文字段（Provider 节点注入的数据） | - |

## 输出端口

| Key | 标签 | 数据类型 | 说明 |
|-----|------|---------|------|
| `context` | 上下文 | `context` |  |
| `detection` | 检测结果 | `detection_output` |  |

### 上下文 输出模型字段

| 字段 | 类型 | 必填 | 说明 | 默认值 |
|------|------|------|------|--------|
| `chain_id` | integer | - | 区块链网络 ID（1=ETH, 56=BSC, 137=MATIC） | `1` |
| `tx_hash` | string | - | 交易的唯一哈希值 | `` |
| `block_number` | integer | - | 交易所在区块号 | `0` |
| `from_address` | string | - | 交易发起者 (from) 地址 | `` |
| `to_address` | string | - | 交易目标 (to) 地址，空=合约创建 | `` |
| `value` | integer | - | 原生代币转账金额（wei 单位） | `0` |
| `gas_price` | integer | - | 单位 Gas 价格（wei） | `0` |
| `gas_used` | integer | - | 交易消耗的 Gas 总量 | `0` |
| `input_data` | string | - | 交易的 calldata / 方法签名+参数 | `` |
| `timestamp` | string | - | 交易发生时间 (ISO8601) | `` |
| `logs` | array | - | 交易产生的 Event Log 列表 | - |
| `extra` | object | - | 扩展上下文字段（Provider 节点注入的数据） | - |

### 检测结果 输出模型字段

| 字段 | 类型 | 必填 | 说明 | 默认值 |
|------|------|------|------|--------|
| `score` | number | &#10003; | 0-100 风险评分 | - |
| `passed` | boolean | &#10003; | 评分是否 >= 配置的阈值 | - |
| `severity` | string | &#10003; | UNKNOWN/LOW/MEDIUM/HIGH/CRITICAL | - |
| `labels` | array | - | 命中的检测标签列表 | - |
| `detection` | object | - | 各检测器特有的检测结果数据 | - |
| `logs` | array | - | 评分原因日志，记录各评分步骤的判定依据 | - |

## 配置参数

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `threshold` | number | `50.0` | min: 0, max: 100 | 0-100，评分达到此值视为 passed |
| `min_price_deviation_pct` | number | `10.0` | min: 1.0 | 最小价格偏移百分比阈值，超过此值视为异常 |
| `min_swap_value_eth` | number | `1.0` | min: 0.1 | 最小 Swap 金额阈值(ETH)，低于此值不触发 Swap→Drain 检测 |
