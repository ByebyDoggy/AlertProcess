# 链上交易调用链分析模块 — 开发计划

> 基于 PoC 验证 (`scripts/tx_callchain_poc.py`) 的完整落地规划
> 参考目标：BlockSec Phalcon Explorer Invocation Flow
> 参考链接：https://app.blocksec.com/phalcon/explorer/tx/bsc/{hash}

---

## 一、背景与目标

### 1.1 当前状态

- 系统已有**告警规则链引擎**（`rules/chain_engine.py`）、**告警处理管线**、**知识库**
- 已完成 PoC 脚本验证（`scripts/tx_callchain_poc.py`），证明：
  - 可通过 `trace_transaction` RPC 获取 151 条 trace entry
  - 可构建嵌套调用树（max depth=11）
  - 可通过 4-byte selector 解析函数签名
  - 可关联 ERC20 Transfer Events 到对应调用节点
  - 可输出结构化 JSON + BlockSec 风格终端可视化
- 已有 4-byte 签名下载脚本（`scripts/download_4bytes/sync_4bytes.py`），可从 [4byte.directory](https://www.4byte.directory) 同步 40万+ 函数签名

### 1.2 目标

| # | 目标 | 说明 |
|---|------|------|
| 1 | **独立前端页面** | 新增 `/chain-analysis` 页面，输入 txHash 展示完整调用树 |
| 2 | **后端基础类** | 在 `detectors/` 模块下新建交易解析基类，负责 txHash → 结构化调用链 |
| 3 | **行为检测器继承** | 闪电贷检测器等行为分析器继承自该基类 |
| 4 | **本地签名服务** | 集成 4byte 签名数据库，提供 API 供前端查询 selector → 函数名 |
| 5 | **多链支持** | 支持 Ethereum / BSC，可扩展至 Arbitrum / Polygon 等 |

### 1.3 核心交互流程

```
用户在 /chain-analysis 页面输入 txHash
        │
        ▼
   POST /detectors/trace/analyze { tx_hash, chain_id }
        │
        ▼
   ┌──────────────────────────────┐
   │    TxTraceAnalyzer (基类)     │
   │                              │
   │  1. RPC 获取原始 trace        │
   │  2. 构建 CallTree            │
   │  3. 4-byte selector 解析签名  │
   │  4. 协议地址标签识别          │
   │  5. Event 关联到调用节点      │
   └──────────┬───────────────────┘
              │ 继承
        ┌─────┴──────────┐
        │                 │
  FlashLoanDetector  TokenFlowDetector  ...
  (闪电贷检测)       (Token流转分析)
              │
              ▼
   返回 FullAnalysisResult {
        tx_info, call_tree[], behaviors[],
        protocols[], token_flow{}, events[]
   }
```

---

## 二、架构设计

### 2.1 模块定位

```
AlertProcessor/
├── detectors/                    ← 【新增】交易解析与分析器所在模块
│   ├── __init__.py
│   ├── base.py                   ← 所有检测器的抽象基类 (已有)
│   ├── implementations/           ← 现有检测器实现 (已有)
│   │   ├── address_type_detector.py
│   │   └── gas_price_detector.py
│   └── trace/                    ← 【新增】交易调用链子模块
│       ├── __init__.py
│       ├── analyzer.py           ← ★ TxTraceAnalyzer 基类 (核心)
│       ├── models.py             ← 数据模型 (CallNode, CallTree, AnalysisResult)
│       ├── provider.py           ← RPC Provider (多节点容错)
│       ├── signature_db.py       ← 本地 4-byte 签名数据库服务
│       ├── protocol_registry.py  ← 协议地址标签库
│       └── behaviors/            ← 行为检测器 (继承 analyzer)
│           ├── __init__.py
│           ├── base_behavior.py  ← 行为检测基类
│           ├── flash_loan.py     ← 闪电贷检测
│           ├── arbitrage.py      ← DEX套利检测
│           ├── token_flow.py     ← Token流转分析
│           └── sandwich.py       ← 三明治攻击检测
│
├── routers/
│   └── detectors/
│       ├── __init__.py           ← 【新增】路由挂载
│       └── trace_router.py       ← 【新增】API 路由
│
├── data/
│   ├── signatures.db             ← SQLite 本地签名库 (由 sync_4bytes 导入)
│   └── protocol_registry.json    ← 协议地址库
│
├── scripts/
│   └── download_4bytes/          ← 已有, 改造为写入 SQLite
│       ├── sync_4bytes.py
│       └── known_hashes.py       ← 中间产物或直接入库
│
└── frontend/src/
    ├── views/
    │   └── ChainAnalysis.vue     ← 【新增】独立页面
    ├── api/
    │   └── trace.js              ← 【新增】API 封装
    └── components/analysis/      ← 【新增】分析组件
        ├── TraceInput.vue
        ├── CallTreeView.vue
        ├── CallNode.vue
        ├── BehaviorPanel.vue
        ├── SignatureTag.vue
        └── TokenFlowPanel.vue
```

### 2.2 关键设计决策

| 决策点 | 方案 | 理由 |
|--------|------|------|
| **放置位置** | `detectors/trace/` 而非独立的 `trace/` 模块 | 用户明确要求在 detector 模块中开一个子模块，与现有 detector 架构统一 |
| **基类职责** | `TxTraceAnalyzer` 只做"解析"，不做"判断" | 解析是通用能力（任何 txHash 都需要），行为检测是特定场景 |
| **签名存储** | SQLite 而非 Python dict 文件 | 40万+ 条记录需要高效查询，SQLite 支持前缀模糊匹配 |
| **前端页面** | 独立路由 `/chain-analysis` | 与规则链编辑器和知识库并列的顶级功能页 |

---

## 三、后端详细设计

### 3.1 数据模型 (`detectors/trace/models.py`)

```python
"""
交易调用链数据模型
参考 PoC 输出: scripts/callchain_0xc310a0af.json
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CallType(str, Enum):
    CALL = "call"
    DELEGATECALL = "delegatecall"
    STATICCALL = "staticcall"
    CREATE = "create"


@dataclass
class DecodedParam:
    """已解码的单个参数"""
    name: str           # 参数名, 如 "to", "amount", "path"
    type_hint: str = ""  # 类型提示, 如 "address", "uint256", "address[]"
    value: str = ""      # 字符串化的值


@dataclass
class EventRecord:
    """关联到调用节点的 Event"""
    name: str               # 如 "Transfer", "Approval", "Swap"
    topic0: str = ""
    log_index: int = 0
    decoded: dict = field(default_factory=dict)  # 解码后的字段
    raw: Optional[dict] = None                   # 原始 log 数据


@dataclass
class CallNode:
    """
    单个调用帧 — 对应 PoC 中的 CallTreeNode
    
    对应前端渲染的一个行:
      0  +- CALL Sender -> Receiver .functionName(params) (gas=xxx)
         |  -> EVENT Transfer: from=... to=...
    """
    # === 来自原始 trace 的数据 ===
    depth: int = 0
    trace_address: list[int] = field(default_factory=list)
    call_type: str = "call"           # CallType 枚举值
    from_address: str = ""
    to_address: str = ""
    input_data: str = "0x"            # 完整 calldata (hex)
    output_data: str = "0x"           # 返回值 (hex)
    value: int = 0                     # wei
    gas_limit: int = 0
    gas_used: int = 0
    error: Optional[str] = None       # revert 信息
    created_address: str = ""         # 仅 CREATE 类型

    # === 分析后填充的数据 ===
    selector: str = ""                # input_data 前 4 字节, 如 "0xa9059cbb"
    function_signature: Optional[str] = None  # 解析后的签名, 如 "transfer(address,uint256)"
    params: list[DecodedParam] = field(default_factory=list)  # 已解码参数
    label: Optional[str] = None       # 协议标签, 如 "Uniswap V3 Router"
    token_symbol: Optional[str] = None  # 如果 to 是已知 token

    # === 关联数据 ===
    children: list["CallNode"] = field(default_factory=list)
    events: list[EventRecord] = field(default_factory=list)

    @property
    def is_create(self) -> bool:
        return self.call_type == "create"

    @property
    def is_delegatecall(self) -> bool:
        return self.call_type == "delegatecall"

    @property
    def is_staticcall(self) -> bool:
        return self.call_type == "staticcall"

    @property
    def is_reverted(self) -> bool:
        return self.error is not None


@dataclass
class TransactionInfo:
    """交易元信息"""
    tx_hash: str
    chain_id: int
    block_number: int = 0
    from_address: str = ""
    to_address: Optional[str] = None
    value: int = 0                       # wei
    gas_used: int = 0
    gas_limit: int = 0
    gas_price: int = 0
    status: bool = True                  # True=success, False=reverted
    timestamp: Optional[int] = None
    position_in_block: int = 0           # 区块内序号


@dataclass
class ProtocolInfo:
    """识别到的协议信息"""
    name: str                # "PancakeSwap: Smart Router V3"
    category: str            # "DEX" / "Lending" / "Bridge" / "MEV" / "Other"
    address: str
    chain_id: int
    confidence: float = 1.0  # 地址匹配置信度


@dataclass
class BehaviorResult:
    """
    行为检测结果
    
    所有行为检测器 (flash_loan, arbitrage, sandwich, ...)
    都返回此统一结构
    """
    behavior_type: str       # "flash_loan" / "arbitrage" / "sandwich" / "token_transfer"
    label: str               # 显示名称: "闪电贷" / "套利攻击" / "三明治攻击"
    description: str         # 描述文本
    confidence: float        # 0.0 ~ 1.0
    risk_level: str          # "info" / "low" / "medium" / "high" / "critical"
    
    # 详情字典 (各检测器自定义结构)
    details: dict = field(default_factory=dict)
    
    # 关键实体
    involved_addresses: list[str] = field(default_factory=list)
    involved_protocols: list[ProtocolInfo] = field(default_factory=list)
    
    # 关联的 trace 路径 (用于前端高亮)
    related_trace_addresses: list[list[int]] = field(default_factory=list)


@dataclass
class TokenFlowItem:
    """单条 Token 流转记录"""
    token_address: str
    token_symbol: Optional[str] = None
    token_name: Optional[str] = None
    decimals: int = 18
    amount_raw: int = 0
    amount_formatted: str = ""        # 人类可读, 如 "1,000,000 USDC"
    direction: str = ""               # "in" / "out"
    from_label: str = ""              # 协议名或地址缩写
    to_label: str = ""


@dataclass
class FullAnalysisResult:
    """
    完整分析结果 — POST /detectors/trace/analyze 返回的结构体
    
    设计原则:
    - 此结果可直接序列化为 JSON 返回给前端
    - 前端拿到此数据即可渲染完整的调用链可视化界面
    """
    # 元数据
    meta: dict = field(default_factory=dict)   # {"total_nodes": 151, "max_depth": 11, ...}
    
    # 基本信息
    tx_info: TransactionInfo = field(default_factory=TransactionInfo)
    
    # 调用树 (核心数据, 嵌套结构)
    root: Optional[CallNode] = None
    
    # 行为检测结果列表 (可能有多个, 也可能为空)
    behaviors: list[BehaviorResult] = field(default_factory=list)
    
    # 识别到的协议列表
    protocols: list[ProtocolInfo] = field(default_factory=list)
    
    # Token 流转汇总
    token_flows: list[TokenFlowItem] = field(default_factory=list)
    
    # 函数签名统计 (供前端展示 top selectors)
    selector_stats: list[dict] = field(default_factory=list)  
    # [{"selector":"0xa9059cbb","sig":"transfer(address,uint256)","count":12}, ...]
```

### 3.2 核心基类: TxTraceAnalyzer (`detectors/trace/analyzer.py`)

这是整个模块的核心。**所有行为检测器都继承此类**。

```python
"""
交易调用链分析器 — 基类

职责:
  1. 通过 RPC 获取原始 trace 数据
  2. 将 flat trace 列表构建为嵌套 CallTree
  3. 通过 4-byte selector 解析函数签名 (查询本地签名库)
  4. 通过 to 地址匹配协议标签
  5. 将 receipt logs 中的 Events 关联到对应的 CallNode
  
使用方式:
  - 直接实例化: analyzer = TxTraceAnalyzer()
  - 继承扩展: class FlashLoanDetector(TxTraceAnalyzer): ...
"""

class TxTraceAnalyzer:
    """交易 Hash 解析基类"""

    # 默认支持的链配置
    CHAIN_CONFIG: dict[int, dict] = {
        1: {"name": "Ethereum", "rpc_urls": [...]},
        56: {"name": "BSC", "rpc_urls": [...]},
        137: {"name": "Polygon", "rpc_urls": [...]},
        42161: {"name": "Arbitrum One", "rpc_urls": [...]},
        10: {"name": "Optimism", "rpc_urls": [...]},
        43114: {"name": "Avalanche C-Chain", "rpc_urls": [...]},
    }

    def __init__(self,
                 signature_db_path: str = "data/signatures.db",
                 protocol_registry_path: str = "data/protocol_registry.json"):
        """
        Args:
            signature_db_path: 本地 4-byte 签名数据库路径 (SQLite)
            protocol_registry_path: 协议地址标签库路径 (JSON)
        """
        self._signature_db = SignatureDB(signature_db_path)
        self._protocol_registry = ProtocolRegistry(protocol_registry_path)
        self._rpc_client = MultiRpcClient()

    # ================================================================
    # 公开接口 — 子类可重写
    # ================================================================

    async def analyze(self, tx_hash: str, chain_id: int = 1) -> FullAnalysisResult:
        """
        完整分析流程 (模板方法模式)
        
        步骤:
        1. get_raw_trace()      — 获取原始 trace
        2. build_call_tree()    — 构建调用树
        3. resolve_signatures() — 解析所有节点的函数签名
        4. identify_protocols() — 识别协议标签
        5. link_events()        — 关联 Events 到节点
        6. extract_token_flow() — 提取 Token 流转
        7. detect_behaviors()   — 运行行为检测 (子类实现)
        8. assemble_result()    — 组装最终结果
        
        Returns:
            FullAnalysisResult
        """
        
        # 1-6 是通用步骤 (本基类实现)
        # 7 由子类的 detect_behaviors() 实现 (默认返回空列表)

    async def get_raw_trace(self, tx_hash: str, chain_id: int) -> list[dict]:
        """获取原始 trace_transaction 结果"""
        
    def build_call_tree(self, raw_traces: list[dict]) -> CallNode:
        """将 flat trace 按 traceAddress 构建为嵌套树 (迭代式, 防递归溢出)"""

    def resolve_signatures(self, root: CallNode) -> None:
        """遍历所有 CallNode, 通过本地签名库解析 selector → function_signature"""

    def identify_protocols(self, root: CallNode, chain_id: int) -> list[ProtocolInfo]:
        """通过 to 地址匹配协议注册表, 返回识别到的协议列表"""

    def link_events(self, root: CallNode, receipt_logs: list[dict]) -> None:
        """将 receipt logs 中的 Events 匹配到对应的 CallNode"""

    def extract_token_flows(self, root: CallNode) -> list[TokenFlowItem]:
        """从调用树和 Events 中提取 Token 流转记录"""

    # ================================================================
    # 可被子类覆盖的钩子
    # ================================================================

    async def detect_behaviors(self, root: CallNode, 
                                tx_info: TransactionInfo) -> list[BehaviorResult]:
        """
        行为检测钩子 — 默认返回空列表
        
        子类 (FlashLoanDetector 等) 重写此方法添加具体检测逻辑
        """
        return []

    def pre_analyze(self, tx_hash: str, chain_id: int) -> None:
        """分析前钩子 — 可用于预热缓存等"""
        
    def post_analyze(self, result: FullAnalysisResult) -> FullAnalysisResult:
        """分析后钩子 — 可用于补充额外数据"""
        return result
```

### 3.3 闪电贷检测器 — 继承示例 (`detectors/trace/behaviors/flash_loan.py`)

```python
"""
闪电贷检测器 — 继承 TxTraceAnalyzer 基类

检测策略:
  Aave: flashLoan() / flashLoanSimple() 调用
  UniswapV3: flash() 调用
  Balancer: flashLoan() 调用
  dYdX: operate() 内部包含 flash
  
特征模式:
  同一交易内: borrow(借出) → 多个 swap 操作 → repay(还款+手续费)
  借还金额接近 (差额 = 手续费)
"""

class FlashLoanDetector(TxTraceAnalyzer):
    """闪电贷检测器 — 继承自 TxTraceAnalyzer"""

    # 已知的闪电贷相关 selector
    FLASH_SELECTORS = {
        "0x8afff657": "flashLoan",
        "0xa5215b6a": "flashLoanSimple", 
        "0x4124df37": "flash",  # Uniswap V3
        # ... 更多
    }

    async def detect_behaviors(
        self, root: CallNode, tx_info: TransactionInfo
    ) -> list[BehaviorResult]:
        """
        重写父类的行为检测钩子
        先调用父类的通用 analyze(), 再叠加闪电贷专项检测
        """
        results = []
        
        # 策略1: 查找 flashLoan 相关调用
        flash_calls = self._find_flash_calls(root)
        if flash_calls:
            results.append(self._build_flash_result(flash_calls))
        
        # 策略2: 分析借还金额模式
        borrow_repay_pattern = self._analyze_borrow_repay(root)
        if borrow_repay_pattern:
            results.append(borrow_repay_pattern)
            
        # 策略3: 检测 Aave Pool 特征调用链
        aave_pattern = self._detect_aave_pattern(root)
        if aave_pattern:
            results.append(aave_pattern)

        return results

    def _find_flash_calls(self, root: CallNode) -> list[CallNode]:
        """遍历调用树查找所有 flash* 相关调用"""

    def _build_flash_result(self, calls: list[CallNode]) -> BehaviorResult:
        """构建闪电贷检测结果"""

    def _detect_aave_pattern(self, root: CallNode) -> Optional[BehaviorResult]:
        """检测 Aave 闪电贷特征模式"""
```

### 3.4 本地签名数据库服务 (`detectors/trace/signature_db.py`)

```python
"""
4-byte 函数签名本地查询服务

数据来源: https://www.4byte.directory/api/v1/signatures/
导入工具: scripts/download_4bytes/sync_4bytes.py (改造版)

存储: SQLite (signatures.db)
表结构:
  signatures (
    id INTEGER PRIMARY KEY,
    selector TEXT NOT NULL,        -- '0xa9059cbb' (10字符)
    text_signature TEXT NOT NULL,   -- 'transfer(address,uint256)'
    num_results INTEGER DEFAULT 1, -- 该 selector 有多少个候选签名
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  )
  INDEX idx_selector ON signatures(selector);
  
API:
  GET /detectors/trace/signatures?prefix=0xa905
  → {"results": [
      {"selector": "0xa9059cbb", "signature": "transfer(address,uint256)"},
      {"selector": "0xa9059cbb", "signature": "transferFrom(address,...)"},  // collision
    ]}
  
  GET /detectors/trace/signatures/{selector}  
  → {"selector": "0xa9059cbb", "best_match": "transfer(address,uint256)", "alternatives": [...]}
"""

import sqlite3
from pathlib import Path

class SignatureDB:
    """本地 4-byte 签名数据库"""

    def __init__(self, db_path: str = "data/signatures.db"):
        self.db_path = Path(db_path)
        self._ensure_db()

    def lookup(self, selector: str) -> Optional[str]:
        """
        精确查询 selector 对应的最佳签名
        若有多个候选, 返回最常用的 (num_results 最高的)
        
        Args:
            selector: 10字符 hex string, 如 "0xa9059cbb"
        Returns:
            text_signature 或 None
        """

    def prefix_search(self, prefix: str, limit: int = 20) -> list[dict]:
        """
        前缀模糊搜索 — 用于前端自动补全
        
        Args:
            prefix: 3~10字符 hex string, 如 "0xa90"
        Returns:
            [{"selector": ..., "signature": ...}, ...]
        """

    def bulk_lookup(self, selectors: list[str]) -> dict[str, str]:
        """批量查询 — 分析时一次性传入所有需要解析的 selector"""

    def count(self) -> int:
        """返回数据库中总条数"""

    def _ensure_db(self):
        """初始化数据库文件 (若不存在则创建空表)"""
```

### 3.5 改造签名同步脚本 (`scripts/download_4bytes/sync_4bytes.py`)

现有脚本从 4byte.directory 分页拉取签名并写入 `known_hashes.py` (Python dict)。改造要点:

```python
# 改动说明:
# 1. 目标输出从 known_hashes.py 改为 SQLite signatures.db
# 2. 使用批量 INSERT 提升性能 (40万+ 条)
# 3. 支持增量更新 (跳过已有的 selector)
# 4. 记录同步时间戳

def save_to_sqlite(signatures_dict: Dict[int, List[str]], db_path: str = "data/signatures.db"):
    """将签名数据写入 SQLite"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 批量插入 (每批 5000 条)
    batch = []
    for hex_int, sig_list in signatures_dict.items():
        selector = f"{hex_int:#010x}"
        for sig in sig_list:
            batch.append((selector, sig))
        if len(batch) >= 5000:
            cursor.executemany(
                "INSERT OR IGNORE INTO signatures (selector, text_signature, num_results) VALUES (?, ?, ?)",
                [(s, sig, len(sig_list)) for s, sig in batch[:]]  # simplify
            )
            batch.clear()
            conn.commit()
    
    conn.close()
```

### 3.6 RPC Provider (`detectors/trace/provider.py`)

```python
"""
RPC 客户端 — 多节点自动切换

特性:
- 每个 chain 配置多个 RPC URL
- 自动故障切换 (timeout/错误时切换下一个)
- 支持 trace_transaction 和 debug_traceTransaction
- 连接池复用
"""

class MultiRpcClient:
    def __init__(self):
        self._clients: dict[int, list[httpx.AsyncClient]] = {}
        self._chain_indices: dict[int, int] = {}

    async def call(self, chain_id: int, method: str, params: list) -> dict:
        """带自动切换的 RPC 调用"""

    async def get_transaction_trace(self, tx_hash: str, chain_id: int) -> list[dict]:
        """获取 trace_transaction 结果 (优先) 或 debug_traceTransaction (fallback)"""

    async def get_transaction_receipt(self, tx_hash: str, chain_id: int) -> dict:
```

### 3.7 API 路由 (`routers/detectors/trace_router.py`)

```python
"""
交易分析 API 路由

端点:
  POST   /detectors/trace/analyze        — 分析交易调用链
  GET    /detectors/trace/supported-chains — 支持的区块链列表
  GET    /detectors/trace/signatures      — 4-byte 签名查询 (供前端)
  GET    /detectors/trace/signatures/{sel}— 精确查询单个签名
  GET    /detectors/trace/stats           — 签名库统计信息
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from detectors.trace.analyzer import TxTraceAnalyzer
from detectors.trace.signature_db import SignatureDB

trace_router = APIRouter(prefix="/detectors/trace", tags=["trace-analysis"])

# 全局单例 (启动时初始化)
_analyzer = TxTraceAnalyzer()
_sig_db = SignatureDB()


class AnalyzeRequest(BaseModel):
    tx_hash: str           # "0x85ac5d15..."
    chain_id: int = 56     # 默认 BSC
    run_behavior_detect: bool = True  # 是否运行行为检测


@trace_router.post("/analyze")
async def analyze_transaction(req: AnalyzeRequest):
    """
    分析交易的完整调用链
    
    Request:
      { "tx_hash": "0x...", "chain_id": 56, "run_behavior_detect": true }
    
    Response:
      { "meta": {...}, "tx_info": {...}, "root": {...}, "behaviors": [...], ... }
    """
    result = await _analyzer.analyze(req.tx_hash, req.chain_id)
    return result.model_dump()  # 或 jsonable_encoder


@trace_router.get("/supported-chains")
async def get_supported_chains():
    """返回支持的链列表 (供前端下拉选择)"""


@trace_router.get("/signatures")
async def search_signatures(prefix: str = "", limit: int = 20):
    """
    前端调用: 根据 selector 前缀搜索函数签名
    用于: 输入框自动补全 / 未知签名的即时查询
    
    Query: ?prefix=0xa905&limit=20
    """
    if prefix:
        results = _sig_db.prefix_search(prefix, limit)
        return {"results": results, "total": len(results)}
    return {"results": [], "total": _sig_db.count()}


@trace_router.get("/stats")
async def get_signature_stats():
    """签名库统计 (显示在前端页面底部)"""
    return {
        "total_signatures": _sig_db.count(),
        "db_path": str(_sig_db.db_path),
    }
```

---

## 四、前端详细设计

### 4.1 页面定位

作为**独立的顶级页面**, 与现有的规则链编辑器、知识库并列。

```
导航栏:
  [ 规则链编辑 ]  [ 知识库 ]  [ 链上分析 ★新增 ]
```

路由: `/chain-analysis` → `views/ChainAnalysis.vue`

### 4.2 页面布局

```
┌─────────────────────────────────────────────────────────────────────┐
│  Header Nav                                                        │
│  [Rule Chain]  [Knowledge Base]  [Chain Analysis★]                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─ Input Bar ───────────────────────────────────────────────────┐ │
│  │                                                                │ │
│  │  TX Hash  [0x85ac5d15f16d49ae08f90ab0e554ebfcb14571234...]  [📋] │ │
│  │                                                                │ │
│  │  Chain:   [BSC ▼]    Auto-detect: [✓]                         │ │
│  │                                                                │ │
│  │  [🔍 Analyze Transaction]                                      │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌─ Main Content ────────────────────────────────────────────────┐ │
│  │                                                               │ │
│  │  ┌─ Left Panel: Invocation Flow (60%) ───┐ ┌─ Right Panel ──┐ │ │
│  │  │                                        │ │                │ │ │
│  │  │  ☐ Expand  Static Call  Gas Used       │ │ Behaviors      │ │ │
│  │  │  Filter: [________________] 🔍         │ │ ┌────────────┐ │ │ │
│  │  │                                        │ │ │ ⚡ FlashLoan│ │ │ │
│  │  │  [0]  CALL  Sender → Receiver         │ │ │ 95%  HIGH   │ │ │ │
│  │  │  [raw data]  ()                        │ │ │ Borrowed:   │ │ │ │
│  │  │    │                                   │ │ │ 30,000 DAI  │ │ │ │
│  │  │    ├─[1] CALL  LidoDAO:Moalah         │ │ │ Repaid:     │ │ │ │ │
│  │  │    │  .FlashLoan calldata(...)         │ │ │ 30,000 DAI  │ │ │ │
│  │  │    │  (tokens=USDT, assets=...)        │ │ └────────────┘ │ │ │
│  │  │    │                                    │ │                │ │ │
│  │  │    ├─[2] DELEGATECALL Moalah:FlashLoan │ │ Protocols     │ │ │
│  │  │    │                                    │ │ • PancakeSwap │ │ │
│  │  │    │  ├─[2→0] CALL  USDT.approve       │ │ • Smart Router│ │ │
│  │  │    │  │  (spender=PancakeSwap...) [true]│ │ • WBNB        │ │ │
│  │  │    │  │  → EVENT USDT.Approve (...)    │ │                │ │ │
│  │  │    │  │                                  │ │ Token Flow    │ │ │
│  │  │    │  ├─[2→1] CALL PancakeSwap:Router  │ │ IN:  8,942..  │ │ │
│  │  │    │  │  .exactInputSingle(...)         │ │ OUT: 8,042..  │ │ │
│  │  │    │  │  → EVENT PancakeSwap.Swap(..)  │ │ NET: +877..   │ │ │
│  │  │    │  │                                  │ │                │ │ │
│  │  │    │  └─[2→2] CALL  PancakeV3Pool.help  │ │ [Save to KB]  │ │ │
│  │  │    │     .getPool()                      │ │                │ │ │
│  │  │    │                                      │ │                │ │ │
│  │  │    ├─[3] CALL  WBNB.withdraw             │ │                │ │ │
│  │  │    │  (wad=189,803,280...) [fallback]     │ │                │ │ │
│  │  │    │  → EVENT WBNB.Withdrawal (...)      │ │                │ │ │
│  │  │    │                                      │ │                │ │ │
│  │  │    └─[4] CALL  USDT.transfer             │ │                │ │ │
│  │  │       (recipient=Sender, amount=...)      │ │                │ │ │
│  │  │       → EVENT USDT.Transfer (...)        │ │                │ │ │
│  │  │                                        │ │                │ │ │
│  │  └────────────────────────────────────────┘ └────────────────┘ │ │
│  │                                                               │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.3 核心组件

#### TraceInput.vue — 顶部输入栏

```
功能:
- txHash 输入框: 支持 66字符校验, 粘贴自动 trim
- chain 下拉选择: 从 GET /supported-chains 动态加载
- Analyze 按钮: loading 态 + 错误态
- 快捷入口: 可粘贴区块浏览器 URL 自动提取 hash
```

#### CallTreeView.vue — 调用树容器

```
功能:
- 接收 FullAnalysisResult.root 作为 prop
- 递归渲染 CallNode 树 (虚拟滚动, 大量节点时性能优化)
- 工具栏: Expand All / Collapse All / Filter by type(CALL/STATIC...)
- 搜索框: 按 function name / address / selector 过滤高亮
- 点击节点: 右侧面板显示详情 (input/output/raw data)

样式参考 BlockSec Phalcon:
- 缩进线连接父子节点
- 类型颜色编码: CALL=蓝, DELEGATECALL=黄, STATICCALL=青, CREATE=绿
- REVERT 的节点标红 + 显示 error message
- Event 用绿色箭头标记, 缩进在所属 CALL 下方
```

#### CallNode.vue — 单个调用节点

```
Props:
  node: CallNode        — 节点数据
  depth: number         — 渲染深度 (控制缩进)
  isLast: boolean       — 是否同级最后一个 (控制连线样式)
  isExpanded: boolean   — 是否展开子节点

渲染内容:
  [depth] [type-icon] FromLabel → ToLabel .functionSignature(params) (gas=N) [value?]
  ↳ return output_data (如果有)
  → EVENT EventName: decoded_params (有关联 event 时)

交互:
  点击展开/折叠
  hover 高亮
  右键复制地址/跳转 explorer
```

#### BehaviorPanel.vue — 行为检测面板

```
功能:
- 接收 FullAnalysisResult.behaviors 作为数据源
- 每个 BehaviorResult 渲染为一个卡片:
  - 图标 (闪电贷⚡/套利🔄/三明治🥪/转账💸)
  - 名称 + 置信度进度条
  - Risk Level 彩色标签
  - 折叠的详情区域 (details 字典的内容)
  - 涉及的协议和地址 (可点击跳转 explorer)
- 无行为时显示 "No suspicious patterns detected"
```

#### SignatureTag.vue — 函数签名标签

```
功能:
- 显示解析后的函数签名, 如 ".swapExactTokensForTokens(...)"
- 若未解析到签名:
  - 显示原始 selector (如 "[0xab9c4b5d]")
  - 点击时弹出查询: 调 GET /signatures?prefix=0xab9c
  - 展示候选签名列表供用户选择
  - 选择后更新显示 (可选: 写入反馈到签名库)
- 已知签名用正常字体, 未知签名用灰色斜体
- hover 显示完整的参数解码结果 tooltip
```

#### TokenFlowPanel.vue — Token 流转摘要

```
功能:
- 接收 FullAnalysisResult.token_flows
- 分 IN / OUT 两列展示
- 汇总每个 Token 的净流入流出
- 数量格式化 (如 1,234.56 USDT)
- 颜色: 绿色=净流入, 红色=净流出
```

### 4.4 API 封装 (`frontend/src/api/trace.js`)

```javascript
import { fetchJson } from './index'

const TRACE_BASE = '/detectors/trace'

export const traceApi = {
  /** 分析交易 */
  analyze: (txHash, chainId = 56) =>
    post(`${TRACE_BASE}/analyze`, { tx_hash: txHash, chain_id: chainId }),

  /** 获取支持链列表 */
  supportedChains: () =>
    fetchJson(`${TRACE_BASE}/supported-chains`),

  /** 签名搜索 (前缀模糊) */
  searchSignatures: (prefix, limit = 20) =>
    fetchJson(`${TRACE_BASE}/signatures?prefix=${prefix}&limit=${limit}`),

  /** 精确查询单个签名 */
  getSignature: (selector) =>
    fetchJson(`${TRACE_BASE}/signatures/${selector}`),

  /** 签名库统计 */
  stats: () =>
    fetchJson(`${TRACE_BASE}/stats`),
}
```

### 4.5 Store (`frontend/src/stores/traceAnalysis.js`)

```javascript
import { defineStore } from 'pinia'
import { traceApi } from '@/api/trace'

export const useTraceStore = defineStore('traceAnalysis', {
  state: () => ({
    // 输入
    txHash: '',
    chainId: 56,

    // 分析结果
    analysisResult: null,        // FullAnalysisResult
    isLoading: false,
    error: null,

    // UI 状态
    expandedNodes: new Set(),     // 已展开的节点 ID 集
    filterText: '',              // 搜索过滤词
    selectedNodeId: null,        // 当前选中节点

    // 签名查询缓存
    signatureCache: {},          // { selector: signature }
  }),

  actions: {
    async analyzeTransaction(txHash, chainId) { ... },
    toggleNode(nodeId) { ... },
    expandAll() { ... },
    collapseAll() { ... },
    async resolveSignature(selector) { ... },  // 查询未知签名
  },
})
```

### 4.6 路由集成

修改 `frontend/src/router.js`, 新增:

```javascript
{
  path: '/chain-analysis',
  name: 'ChainAnalysis',
  component: () => import('./views/ChainAnalysis.vue'),
  meta: { title: 'Chain Analysis' }
}
```

修改 `main.py` SPA fallback, 将 `trace` 加入白名单:

```python
if full_path.startswith(("alert", "rule-chain")):
    # 改为只排除 API 路径
    pass
```

### 4.7 Vite 代理配置 (`frontend/vite.config.js`)

```javascript
'/detectors': {
  target: 'http://localhost:8000',
  changeOrigin: true,
},
```

---

## 五、数据流详述

### 5.1 前端 → 后端 → 前端 完整数据流

```
用户操作: 粘贴 txHash + 点 "Analyze"
  │
  ▼
[前端] traceApi.analyze("0x85ac...", 56)
  │ POST /detectors/trace/analyze
  │ Body: { tx_hash, chain_id, run_behavior_detect: true }
  │
  ▼
[后端] trace_router.analyze_transaction()
  │ 创建 TxTraceAnalyzer 实例 (复用全局单例)
  │
  ▼
[TxTraceAnalyzer.analyze()]  ← 模板方法
  │
  ├── Step 1: provider.get_transaction_trace(tx_hash, chain_id)
  │   → JSON-RPC trace_transaction → 151 条 raw trace entries
  │
  ├── Step 2: build_call_tree(raw_traces)
  │   → 按 traceAddress 构建嵌套 CallNode 树 (根 depth=0, 最大 depth=11)
  │
  ├── Step 3: resolve_signatures(root)
  │   → 遍历所有 CallNode, 取 input_data[:10] 作为 selector
  │   → signature_db.bulk_lookup(all_selectors)  ← SQLite 批量查询
  │   → 填充 node.function_signature + node.params
  │
  ├── Step 4: identify_protocols(root, chain_id)
  │   → 遍历所有 CallNode.to_address
  │   → protocol_registry.match(addr, chain_id)
  │   → 填充 node.label
  │
  ├── Step 5: link_events(root, receipt_logs)
  │   → receipt.logs (56 条 ERC20 Transfer/Approval)
  │   → 启发式匹配到最近的 CallNode
  │   → 填充 node.events[]
  │
  ├── Step 6: extract_token_flows(root)
  │   → 从 events + transfer/transferFrom 调用提取
  │   → 计算 IN/OUT/NET
  │
  ├── Step 7: detect_behaviors(root, tx_info)  ← ★ 子类重写点
  │   │
  │   ├── [FlashLoanDetector] 查找 flashLoan/flashLoanSimple 调用
  │   │   → 分析借还金额模式
  │   │   → 构建 BehaviorResult(behavior_type="flash_loan", confidence=0.95)
  │   │
  │   └── [TokenFlowDetector] 分析大额转账
  │       → 构建 BehaviorResult(...)
  │
  ├── Step 8: assemble_result()
  │   → 打包为 FullAnalysisReturn
  │   → 序列化 JSON
  │
  ▼
[HTTP Response] JSON ~50KB (取决于交易复杂度)
  │
  ▼
[前端] store.analysisResult = response.data
  │
  ├── <CallTreeView :root="result.root" />
  │     → 递归渲染 151 个 CallNode + Events
  │
  ├── <BehaviorPanel :behaviors="result.behaviors" />
  │     → 渲染 2 张行为卡片 (FlashLoan + TokenTransfer)
  │
  ├── <TokenFlowPanel :flows="result.token_flows" />
  │     → IN/OUT 摘要
  │
  └── <SignatureTag /> (嵌入每个 CallNode 内)
        → 已解析: 正常显示 ".transfer(address,uint256)"
        → 未解析: 灰色 "[0xab9c4b5d]" + 点击查询
```

### 5.2 签名查询数据流 (按需/延迟)

```
用户点击未知签名 [0xab9c4b5d] 上的 "?" 图标
  │
  ▼
[前端] store.resolveSignature("0xab9c4b5d")
  │ 先检查本地 cache → miss
  │
  ▼
[GET] /detectors/trace/signatures?prefix=0xab9c
  │
  ▼
[SignatureDB.prefix_search("0xab9c")]
  → SQL: SELECT * FROM signatures WHERE selector LIKE '0xab9c%' LIMIT 20
  → 返回 [{selector:"0xab9c4b5d", sig:"execute(uint256,bytes[])"}, ...]
  │
  ▼
[前端] 弹出下拉选择框
  → 用户选择 "execute(uint256,bytes[])"
  → 更新该节点的 function_signature 显示
  → 写入 cache
```

---

## 六、开发阶段

| 阶段 | 内容 | 涉及文件 | 交付物 |
|------|------|----------|--------|
| **P0: 基础骨架** | models + analyzer 基类 + provider + signature_db (空壳) | `detectors/trace/models.py`, `analyzer.py`, `provider.py`, `signature_db.py`, `protocol_registry.py` | 可 import 但无真实逻辑 |
| **P1: 核心解析** | 从 PoC 移植 trace 获取 + 树构建 + 签名解析 + 协议识别 + Event 关联 | 完善 `analyzer.py` 全部方法 | `POST /detectors/trace/analyze` 返回正确结构 |
| **P2: 签名库集成** | 改造 `sync_4bytes.py` → 写入 SQLite + signature_db 查询逻辑 + 签名查询 API | `scripts/download_4bytes/sync_4bytes.py`, `signature_db.py`, `trace_router.py` | `GET /signatures` 可用, 库中有 40w+ 条 |
| **P3: 行为检测** | base_behavior + FlashLoanDetector + TokenFlowDetector | `behaviors/base_behavior.py`, `flash_loan.py`, `token_flow.py` | 分析结果含 behaviors |
| **P4: 前端页面** | ChainAnalysis 主页 + CallTreeView + CallNode + TraceInput + BehaviorPanel | `views/ChainAnalysis.vue`, `components/analysis/*.vue`, `api/trace.js`, `stores/traceAnalysis.js` | 完整可用页面 |
| **P5: 签名交互** | SignatureTag 未知签名查询 + 前端缓存 + 签名统计展示 | `components/analysis/SignatureTag.vue`, `TokenFlowPanel.vue` | 前端可查询未知签名 |
| **P6: 体验优化** | 大型交易虚拟滚动 + 节点筛选/搜索/highlight + 地址标签 + Explorer 跳转 + 保存到知识库 | 各组件增强 | 生产级用户体验 |

---

## 七、PoC 验证结果对照

以下是基于 `scripts/tx_callchain_poc.py` 实际运行结果的验证清单:

| 能力 | PoC 状态 | 落地计划 |
|------|---------|---------|
| trace_transaction RPC 调用 | ✅ 151 条 trace | P1: 移植到 `provider.py` |
| Flat → Tree 转换 | ✅ 嵌套树, max_depth=11 | P1: 移植到 `analyzer.build_call_tree()` |
| 4-byte 签名解析 (本地 30+ 条) | ✅ balanceOf/transfer/transferFrom/approve 等 | P1+P2: 扩展至 40w+ SQLite |
| 参数解码 (address/uint256) | ✅ 基本 decode | P1: 增强 eth-abi 完整解码 |
| 协议地址标签 | ✅ Aave V3 Pool 识别 | P1: 完善 `protocol_registry.json` |
| Event 关联 | ✅ 56/56 events 关联成功 | P1: 优化匹配算法 |
| 结构化 JSON 输出 | ✅ 4665 行完整 JSON | P1: 对齐 `FullAnalysisResult` 模型 |
| 终端可视化 | ✅ BlockSec 风格 | 不需要 (前端替代) |
| 闪电贷检测 | ❌ (PoC 只有 print summary) | P3: `FlashLoanDetector` |
| Token 流转分析 | ⚠️ (PoC 有基本聚合) | P3: `TokenFlowDetector` |
| 多 RPC 容错 | ✅ 3 个 URL 自动切换 | P1: 移植到 `MultiRpcClient` |
| BSC 支持 | ⚠️ (RPC 超时, 代码就绪) | P1: 补充可用 BSC RPC |

---

## 八、注意事项与风险

### 8.1 性能考虑

| 问题 | 影响 | 解决方案 |
|------|------|---------|
| 复杂交易 trace 可能上千条 | 响应慢 | 限制最大深度 (default 20), 前端虚拟滚动 |
| 40w+ 签名库内存占用 | ~100MB RAM | SQLite 按需查询, 不全量加载 |
| RPC 超时 (BSC 公共节点不稳定) | 分析失败 | 多节点切换 + 超时重试 + 缓存最近结果 |
| 前端渲染大量 DOM | 页面卡顿 | 虚拟滚动 + 只渲染可见区域 + 懒展开 |

### 8.2 依赖管理

```
# requirements.txt 新增 (可能)
eth-abi           # 完整的 ABI 编解码 (替代手写 decode_params)
aiosqlite         # 异步 SQLite (如果需要高性能)
# httpx 已有
# web3 可选保留 (PoC 用 web3, 生产环境用原生 httpx 更轻量)
```

### 8.3 安全注意

- `/detectors/trace/analyze` 端点应设置速率限制 (同一 IP 请求间隔 ≥ 2s)
- 签名查询 API 无需认证 (方便前端使用)
- 分析 API 建议: 开发阶段无需认证, 上线后加 optional API Key
- **提交 GitHub 前确保不包含 `.env` 中的 RPC Key / API Key**

---

## 九、附录: 与现有模块的关系

```
                    ┌─────────────────┐
                    │    main.py      │
                    │  (FastAPI App)  │
                    └───────┬─────────┘
                            │
         ┌──────────────────┼──────────────────┐
         │                  │                  │
    routers/alert/   routers/rule_chain/  routers/detectors/
    router.py       router.py           trace_router.py  ← 【新增】
         │                  │                  │
         ▼                  ▼                  ▼
    AlertPipeline    ChainEngine        TxTraceAnalyzer
    (告警接收处理)   (规则链引擎)        (交易调用链分析基类)  ← 【新增】
                                               │
                                    ┌──────────┼──────────┐
                                    ▼          ▼          ▼
                              FlashLoan   Arbitrage   TokenFlow
                              Detector    Detector    Detector
                              (继承基类)   (继承基类)   (继承基类)
```

**集成场景**: 未来可在 `AlertPipeline` 中集成 `TxTraceAnalyzer`，当接收到告警时自动对关联 txHash 进行调用链分析，将分析结果写入 `alert_data` 供规则链使用。
