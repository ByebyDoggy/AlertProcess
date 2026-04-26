# 检测器节点架构参考

## 目录结构

```
nodes/
├── __init__.py          # NodeRegistry 注册所有节点
├── base.py              # BaseNode 基类
├── models.py            # TransactionContext, DetectorResult 等数据模型
└── detectors/
    ├── __init__.py      # 检测器注册（必须在此导出）
    ├── base.py          # BaseDetector 基类
    ├── economic_anomaly.py
    ├── fund_drain.py
    ├── token_anomaly.py
    └── protocol/
        └── indirection_layer.py

detectors/trace/
├── analyzer.py           # TxTraceAnalyzer 基类
├── models.py             # CallNode, TransactionInfo, BehaviorResult
└── behaviors/
    ├── base_behavior.py  # BaseBehaviorDetector 基类
    ├── flash_loan.py     # FlashLoanBehavior
    └── token_flow.py     # TokenFlowBehavior
```

## 两层检测器体系

### 节点层检测器（nodes/detectors/）

- **基类**: `BaseDetector`（继承自 `BaseNode`）
- **输入**: `TransactionContext`（来自上游节点的 alert_data + receipt + logs）
- **输出**: 双端口 — context（TransactionContext）+ detection（DetectorResult）
- **核心方法**: `async def process(self, tx_context: TransactionContext) -> DetectorOutputMixin`
- **适用场景**: 基于 receipt/logs 的检测，不需要完整的调用链 trace

**数据来源**:
- `tx_context.logs` — 交易事件日志（ERC-20 Transfer, DEX Swap 等）
- `tx_context.receipt` — 交易回执
- `tx_context.alert_data` — 原始告警数据
- `tx_context.internal_transactions` — 内部交易

### 行为层检测器（detectors/trace/behaviors/）

- **基类**: `BaseBehaviorDetector`（继承自 `TxTraceAnalyzer`）
- **输入**: 完整的调用链 trace 数据
- **输出**: `BehaviorResult`
- **核心方法**: `detect_behaviors()`
- **适用场景**: 需要调用链深度分析、函数签名匹配、调用模式识别

## 新建检测器步骤

### 1. 创建节点层检测器

```python
# nodes/detectors/my_detector.py
from nodes.base import NodeRegistry, score_to_severity
from nodes.detectors.base import BaseDetector, DetectorConfigMixin, DetectorOutputMixin
from nodes.models import TransactionContext

class MyDetectorConfig(DetectorConfigMixin):
    """自定义配置"""
    my_threshold: float = Field(default=1000.0, description="自定义阈值")

class MyDetector(BaseDetector):
    # 节点元信息
    name = "my_detector"
    label = "我的检测器"
    description = "检测描述"
    category = NodeCategory.DETECTION
    
    # 配置模型
    ConfigModel = MyDetectorConfig
    
    async def process(self, tx_context: TransactionContext) -> DetectorOutputMixin:
        # 实现检测逻辑
        score = 0.0
        labels = []
        detection = {}
        logs = []
        
        # ... 检测逻辑 ...
        
        return DetectorOutputMixin(
            score=score,
            passed=score >= self.config.get("threshold", 50.0),
            severity=score_to_severity(score),
            labels=labels,
            detection=detection,
            logs=logs,
        )

# 注册节点
NodeRegistry.register(MyDetector)
```

### 2. 在 __init__.py 中注册

```python
# nodes/detectors/__init__.py
from nodes.detectors.my_detector import MyDetector

__all__ = [
    # ... 已有检测器 ...
    "MyDetector",
]
```

### 3. 前端集成（如需在节点面板显示）

在 `frontend/src/api/nodeSchema.js` 中添加节点 schema:

```javascript
{
  name: 'my_detector',
  label: '我的检测器',
  category: 'detection',
  inputs: [...],
  outputs: [...],
  config: [...]
}
```

## 标准事件 Topic 常量

```python
# ERC-20 Transfer(address indexed from, address indexed to, uint256 value)
ERC20_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# Uniswap V2 Swap
UNISWAP_V2_SWAP_TOPIC = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d714"

# Uniswap V3 Swap
UNISWAP_V3_SWAP_TOPIC = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e7b213eb771"

# ERC-20 Approval(address indexed owner, address indexed spender, uint256 value)
ERC20_APPROVAL_TOPIC = "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925"

# 零地址
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
```

## 检测维度与评分设计原则

1. **基础分**: 每个检测维度有独立的基础分
2. **上限**: 每个维度有评分上限（防止单一特征主导总分）
3. **组合加分**: 多个特征组合时额外加分（非线性叠加）
4. **总分上限**: 100 分封顶
5. **阈值**: 通过 `threshold` 配置判断 passed（默认 50 分）

### 评分示例

```
基础分 = ROI_score(roi) + burn_score(amount) + mint_transfer_score(pattern)
加分 = swap_burn_claim_loop? + high_roi_without_flashloan?
总分 = min(100, 基础分 + 加分)
```

## 输出模型字段

```python
class DetectorOutputMixin(BaseModel):
    score: float          # 0-100 风险评分
    passed: bool          # 是否 >= threshold
    severity: str         # UNKNOWN/LOW/MEDIUM/HIGH/CRITICAL
    labels: list[str]     # 命中的检测标签列表
    detection: dict       # 各检测器特有的检测结果数据
    logs: list[str]       # 评分原因日志
```

## 已有检测器列表

| 检测器 | 文件 | 核心检测维度 |
|--------|------|-------------|
| GasPriceDetector | gas_price.py | Gas 价格异常 |
| AddressTypeDetector | address_type.py | 地址类型判断 |
| TokenApprovalDetector | token_approval.py | 异常授权检测 |
| TokenAnomalyDetector | token_anomaly.py | 大额转账 + 新代币 |
| AddressGraphDetector | address_graph.py | 黑名单/交易所地址 |
| AddressAgeDetector | address_age.py | 地址年龄估算 |
| ARKMLabelDetector | arkm_label.py | 实体标签 |
| FundDrainDetector | fund_drain.py | 大额流出 + ROI + 闭环 |
| EconomicAnomalyDetector | economic_anomaly.py | 经济异常全维度 |
| IndirectionLayerDetector | protocol/indirection_layer.py | 调用链深度 + 代理 |
