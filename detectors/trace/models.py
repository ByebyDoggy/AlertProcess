"""
交易调用链数据模型
==================
参考 PoC 输出: scripts/callchain_0xc310a0af.json
参考文档: docs/dev-plan-trace-analysis.md §3.1
"""
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any


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

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "topic0": self.topic0,
            "logIndex": self.log_index,
            "decoded": self.decoded,
            "raw": self.raw,
        }


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
    call_type: str = "call"           # CallType 枚举值字符串
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

    def to_dict(self) -> dict:
        """序列化为可 JSON 化的字典 — camelCase 匹配前端"""
        return {
            "depth": self.depth,
            "traceAddress": self.trace_address,
            "callType": self.call_type,
            "fromAddress": self.from_address,
            "toAddress": self.to_address,
            "input": self.input_data if len(self.input_data) <= 132 else self.input_data[:132] + "...",
            "output": self.output_data if len(self.output_data) <= 132 else self.output_data[:132] + "...",
            "value": hex(self.value) if self.value > 0 else "0x0",
            "gasLimit": self.gas_limit,
            "gasUsed": self.gas_used,
            "error": self.error,
            "createdAddress": self.created_address or None,
            "selector": self.selector,
            "functionSig": self.function_signature,
            "params": [asdict(p) for p in self.params],
            "label": self.label,
            "tokenSymbol": self.token_symbol,
            "events": [e.to_dict() for e in self.events],
            "childrenCount": len(self.children),
            "children": [c.to_dict() for c in self.children],
        }


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

    def to_dict(self) -> dict:
        """camelCase 以匹配前端"""
        return {
            "txHash": self.tx_hash,
            "chainId": self.chain_id,
            "blockNumber": self.block_number,
            "fromAddress": self.from_address,
            "toAddress": self.to_address,
            "value": self.value,
            "gasUsed": self.gas_used,
            "gasLimit": self.gas_limit,
            "gasPrice": self.gas_price,
            "status": self.status,
            "timestamp": self.timestamp,
            "positionInBlock": self.position_in_block,
        }


@dataclass
class ProtocolInfo:
    """识别到的协议信息"""
    name: str                # "PancakeSwap: Smart Router V3"
    category: str            # "DEX" / "Lending" / "Bridge" / "MEV" / "Other"
    address: str
    chain_id: int
    confidence: float = 1.0  # 地址匹配置信度

    def to_dict(self) -> dict:
        """camelCase 以匹配前端"""
        return {
            "name": self.name,
            "category": self.category,
            "address": self.address,
            "chainId": self.chain_id,
            "confidence": self.confidence,
        }


@dataclass
class BehaviorResult:
    """
    行为检测结果 — 所有行为检测器返回此统一结构
    """
    behavior_type: str       # "flash_loan" / "arbitrage" / "sandwich" / "token_transfer"
    label: str               # 显示名称: "闪电贷" / "套利攻击" / "三明治攻击"
    description: str         # 描述文本
    confidence: float        # 0.0 ~ 1.0
    risk_level: str          # "info" / "low" / "medium" / "high" / "critical"

    details: dict = field(default_factory=dict)
    involved_addresses: list[str] = field(default_factory=list)
    involved_protocols: list[ProtocolInfo] = field(default_factory=list)
    related_trace_addresses: list[list[int]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "behaviorType": self.behavior_type,
            "label": self.label,
            "description": self.description,
            "confidence": self.confidence,
            "riskLevel": self.risk_level,
            "details": self.details,
            "involvedAddresses": self.involved_addresses,
            "relatedTraceAddresses": self.related_trace_addresses,
            "involvedProtocols": [p.to_dict() for p in self.involved_protocols],
        }


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

    def to_dict(self) -> dict:
        """camelCase 以匹配前端"""
        return {
            "tokenAddress": self.token_address,
            "tokenSymbol": self.token_symbol,
            "tokenName": self.token_name,
            "decimals": self.decimals,
            "amountRaw": self.amount_raw,
            "amountFormatted": self.amount_formatted,
            "direction": self.direction,
            "fromLabel": self.from_label,
            "toLabel": self.to_label,
        }


@dataclass
class BalanceChangeItem:
    """单个地址的余额变化 — 按 (地址, token) 聚合"""
    address: str                           # 地址
    address_label: str = ""                # 协议标签或地址缩写, 如 "DBXen Exploiter"
    token_address: str = ""                # Token 合约地址, 空字符串表示 ETH
    token_symbol: str = ""                 # "ETH", "WETH", "USDT", etc.
    decimals: int = 18
    amount_raw: int = 0                    # 净变化量 (正=收入, 负=支出)
    amount_formatted: str = ""             # 如 "+13,900.0000" / "-2,305.4277"
    value_usd: float = 0.0                # USD 估值 (可选)

    def to_dict(self) -> dict:
        return {
            "address": self.address,
            "addressLabel": self.address_label,
            "tokenAddress": self.token_address,
            "tokenSymbol": self.token_symbol,
            "decimals": self.decimals,
            "amountRaw": self.amount_raw,
            "amountFormatted": self.amount_formatted,
            "valueUsd": round(self.value_usd, 2) if self.value_usd else None,
        }


@dataclass
class FullAnalysisResult:
    """
    完整分析结果 — POST /detectors/trace/analyze 返回的结构体

    设计原则:
    - 此结果可直接序列化为 JSON 返回给前端
    - 前端拿到此数据即可渲染完整的调用链可视化界面
    """

    meta: dict = field(default_factory=dict)
    tx_info: Optional[TransactionInfo] = None
    root: Optional[CallNode] = None
    behaviors: list[BehaviorResult] = field(default_factory=list)
    protocols: list[ProtocolInfo] = field(default_factory=list)
    token_flows: list[TokenFlowItem] = field(default_factory=list)
    balance_changes: list[BalanceChangeItem] = field(default_factory=list)
    selector_stats: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        """序列化为 API 返回的字典格式"""
        d: dict[str, Any] = {
            "meta": self.meta,
            "txInfo": self.tx_info.to_dict() if isinstance(self.tx_info, TransactionInfo) else {},
            "root": self.root.to_dict() if self.root else None,
            "behaviors": [b.to_dict() for b in self.behaviors],
            "protocols": [p.to_dict() for p in self.protocols],
            "tokenFlows": [f.to_dict() for f in self.token_flows],
            "balanceChanges": [b.to_dict() for b in self.balance_changes],
            "selectorStats": self.selector_stats,
        }
        return d
