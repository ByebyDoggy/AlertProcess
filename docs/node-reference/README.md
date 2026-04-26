# 节点参考文档

> 本文档由 `scripts/generate_node_docs.py` 从 Pydantic 模型自动生成，新增节点后重新运行脚本即可更新。

## 输入

| 节点 | 名称 | 描述 |
|------|------|------|
| [告警触发器](./alert_trigger.md) | `alert_trigger` | 规则链的入口节点，接收外部告警数据（chain_id、tx_hash、gas_price 等）并传递给下游检测节点。每条 |

## 上下文查询

| 节点 | 名称 | 描述 |
|------|------|------|
| [ARKM 标签查询](./arkm_label_provider.md) | `arkm_label_provider` | 通过 ARKM Intelligence API 获取地址实体标签，注入 entity_type、entity_name |
| [ETH Trace 查询](./eth_trace_provider.md) | `eth_trace_provider` | 通过 RPC 获取交易 trace 调用追踪，注入 eth_trace 标准化数据 |
| [Moralis 地址查询](./moralis_address_provider.md) | `moralis_address_provider` | 通过 Moralis Web3 Data API 查询地址首次活跃时间，注入 address_create_time、a |

## 安全检测

| 节点 | 名称 | 描述 |
|------|------|------|
| [地址年龄检测](./address_age_detector.md) | `address_age_detector` | [数据需求: 仅交易基础字段] 检测交易涉及的新建地址风险：通过 MoralisAddressProviderNode  |
| [地址关系图谱](./address_graph_detector.md) | `address_graph_detector` | [数据需求: 仅交易基础字段] 基于已知地址数据库分析交易双方关系：与已知攻击者地址交互给 95 分、交易所地址交互 4 |
| [地址类型检测](./address_type_detector.md) | `address_type_detector` | [数据需求: 仅交易基础字段] 检测可疑地址类型：null 地址转账（合约创建/销毁）、携带 ETH 的合约创建（85  |
| [ARKM 标签检测](./arkm_label_detector.md) | `arkm_label_detector` | [数据需求: 仅交易基础字段] 通过 ARKM Intelligence 实体标签库检测恶意实体：黑名单类型（如 hac |
| [经济异常检测](./economic_anomaly_detector.md) | `economic_anomaly_detector` | [数据需求: Logs + Trace(辅助)] 检测经济套利类攻击：极高 ROI（投入产出比异常）、Token 销毁信 |
| [闪电贷Trace检测](./flash_loan_trace_detector.md) | `flash_loan_trace_detector` | [数据需求: Trace(必需)] 基于ETH调用栈分析闪电贷攻击：识别借款→操纵→还款完整链路，检测闪电贷回调函数和跨 |
| [资金外流检测](./fund_drain_detector.md) | `fund_drain_detector` | [数据需求: Logs + Trace(辅助)] 全地址盈亏分析：计算交易内所有地址的 USD 净盈亏，识别最大获利者和 |
| [Gas 价格检测](./gas_price_detector.md) | `gas_price_detector` | [数据需求: 仅交易基础字段] 检测交易 Gas 费用是否异常高（如抢 Front-run 或攻击行为）。根据 gas_ |
| [中间合约代理检测](./indirection_layer_detector.md) | `indirection_layer_detector` | [数据需求: Trace(必需)] 检测攻击者通过中间合约代理调用隐藏真实目标：调用链深度异常、delegatecall |
| [预言机操纵检测](./oracle_manipulation_detector.md) | `oracle_manipulation_detector` | [数据需求: Trace(必需)] 基于ETH调用栈分析预言机操纵攻击：检测大额swap操纵价格+预言机查询的时序关联， |
| [价格操纵检测](./price_manipulation_detector.md) | `price_manipulation_detector` | [数据需求: Logs] 检测现货价格操纵类攻击：单区块极端价格偏移(同一池同一交易内价格变化>10%)、大额Swap后 |
| [代理合约升级检测](./proxy_upgrade_detector.md) | `proxy_upgrade_detector` | [数据需求: 仅Logs] 检测 EIP-1967 代理合约升级操作：监控 Upgraded / AdminChange |
| [重入攻击检测](./reentrancy_detector.md) | `reentrancy_detector` | [数据需求: 仅Logs] 检测重入攻击：通过 logs 中合约地址的高频重复出现识别重入模式。同一合约 ≥20 次日志 |
| [代币异常检测](./token_anomaly_detector.md) | `token_anomaly_detector` | [数据需求: 仅交易基础字段] 检测异常代币转账模式：大额 ERC20/ETH 转账（80 分）、新部署代币的早期活动（ |
| [ERC20 授权检测](./token_approval_detector.md) | `token_approval_detector` | [数据需求: 仅交易基础字段] 检测危险的 ERC20 授权操作：无限授权 approve(MAX_UINT256) 给 |

## 动作

| 节点 | 名称 | 描述 |
|------|------|------|
| [添加标签](./add_tag_action.md) | `add_tag_action` | 向告警执行上下文中添加自定义标签（如 phishing、flash_loan），支持去重合并。标签会传递给下游动作节点用 |
| [Telegram 通知](./notify_telegram_action.md) | `notify_telegram_action` | 通过 Telegram Bot API 异步发送告警消息，支持 HTML/Markdown 格式和模板变量替换（{sev |
| [Webhook 通知](./notify_webhook_action.md) | `notify_webhook_action` | 异步发送 HTTP 请求到指定 Webhook URL，支持 POST/PUT/PATCH 方法和自定义 Headers |
| [设置严重级别](./set_severity_action.md) | `set_severity_action` | 设置告警的最终严重级别（CRITICAL/HIGH/MEDIUM/LOW），支持条件触发：always 始终设置、pas |
| [更新数据库](./update_database_action.md) | `update_database_action` | 将规则链执行结果写入数据库表，支持 insert 和 upsert 两种模式。通过字段映射将 context 中的数据映 |

## 脚本

| 节点 | 名称 | 描述 |
|------|------|------|
| [Python 表达式](./script_node.md) | `script_node` | 用 Python 脚本替代逻辑/比较/评分节点。可用变量: inputs(上游输出列表), scores(分数列表),  |

## 存储

| 节点 | 名称 | 描述 |
|------|------|------|
| [外部存储](./external_storage.md) | `external_storage` | 提供实例级隔离的缓存字典。下游检测器连接后可读写同一引用，支持 TTL 自动过期。用于时序攻击检测、跨执行状态关联等场景 |
