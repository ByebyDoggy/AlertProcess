"""
ETH Trace Provider 节点

通过 apipool-server 封装的 RPC 客户端获取交易 trace 数据。
注入字段到 extra:
  - eth_trace: 标准化后的 trace 数据 (Pydantic 模型)
    - traces: 调用追踪列表
    - trace_count: trace 条目总数
    - has_delegatecall: 是否包含 delegatecall
    - has_staticcall: 是否包含 staticcall
    - max_depth: 最大调用深度
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from nodes.base import NodeRegistry
from nodes.providers.base import BaseContextProviderNode
from nodes.models import TransactionContext

logger = logging.getLogger(__name__)


# ─── Pydantic Models ───

class TraceAction(BaseModel):
    """Trace action 详情"""
    call_type: str = Field(default="", alias="callType", description="调用类型: call/staticcall/delegatecall/...")
    from_addr: str = Field(default="", alias="from", description="调用方地址")
    to_addr: str = Field(default="", alias="to", description="被调用方地址")
    gas: str = Field(default="0x0", description="Gas 限制")
    input_data: str = Field(default="0x", alias="input", description="调用输入数据")
    value: str = Field(default="0x0", description="转账金额")


class TraceResult(BaseModel):
    """Trace 执行结果"""
    gas_used: str = Field(default="0x0", alias="gasUsed", description="实际消耗 Gas")
    output: str = Field(default="0x", description="调用输出数据")


class EthTraceEntry(BaseModel):
    """单条 trace 记录"""
    action: TraceAction = Field(default_factory=TraceAction, description="调用动作详情")
    result: TraceResult = Field(default_factory=TraceResult, description="执行结果")
    trace_type: str = Field(default="", alias="type", description="trace 类型: call/create/suicide/...")
    trace_address: list[int] = Field(default_factory=list, alias="traceAddress", description="层级路径")
    subtraces: int = Field(default=0, description="子调用数量")
    block_hash: str = Field(default="", alias="blockHash", description="区块哈希")
    block_number: int = Field(default=0, alias="blockNumber", description="区块号")
    transaction_hash: str = Field(default="", alias="transactionHash", description="交易哈希")
    transaction_position: int = Field(default=0, alias="transactionPosition", description="交易在区块中的位置")

    class Config:
        populate_by_name = True


class EthTraceData(BaseModel):
    """ETH Trace 标准化数据结构"""
    traces: list[EthTraceEntry] = Field(default_factory=list, description="trace 条目列表")
    trace_count: int = Field(default=0, description="trace 条目总数")
    has_delegatecall: bool = Field(default=False, description="是否包含 delegatecall")
    has_staticcall: bool = Field(default=False, description="是否包含 staticcall")
    max_depth: int = Field(default=0, description="最大调用深度")

    @classmethod
    def from_raw_traces(cls, raw_traces: list[dict]) -> "EthTraceData":
        """从原始 RPC trace 结果构建标准化数据"""
        entries: list[EthTraceEntry] = []
        has_delegatecall = False
        has_staticcall = False
        max_depth = 0

        for raw in raw_traces:
            entry = EthTraceEntry.model_validate(raw)
            entries.append(entry)

            ct = entry.action.call_type.lower()
            if ct == "delegatecall":
                has_delegatecall = True
            elif ct == "staticcall":
                has_staticcall = True

            depth = len(entry.trace_address)
            if depth > max_depth:
                max_depth = depth

        return cls(
            traces=entries,
            trace_count=len(entries),
            has_delegatecall=has_delegatecall,
            has_staticcall=has_staticcall,
            max_depth=max_depth,
        )


# ─── Provider Node ───

class EthTraceProviderNode(BaseContextProviderNode):
    """
    ETH Trace 查询 Provider 节点。

    通过 apipool-server 封装的 RPC 客户端获取交易 trace 数据，
    注入标准化后的 eth_trace 字段到 extra。

    配置:
      - 依赖 apipool-server 的 RPC 池配置 (APIPOOL_SERVER_URL, APIPOOL_POOL_MAP)
    """

    name: str = "eth_trace_provider"
    label: str = "ETH Trace 查询"
    description: str = "通过 RPC 获取交易 trace 调用追踪，注入 eth_trace 标准化数据"
    icon: str = "\U0001f4ca"
    color: str = "#14b8a6"

    provides = ["eth_trace"]

    async def fetch(self, tx_context: TransactionContext) -> dict[str, Any]:
        """
        获取交易 trace 数据。

        策略:
          1. 从 tx_context 提取 tx_hash 和 chain_id
          2. 调用 MultiRpcClient 获取 trace
          3. 标准化为 Pydantic 模型并返回
        """
        tx_hash = tx_context.tx_hash or ""
        chain_id = tx_context.chain_id or 1

        if not tx_hash or not tx_hash.startswith("0x"):
            logger.debug("[EthTraceProvider] No valid tx_hash in context, skipping")
            return {}

        try:
            from detectors.trace.provider import get_rpc_client
            client = get_rpc_client()
            raw_traces = await client.get_transaction_trace(tx_hash, chain_id)

            if not raw_traces:
                logger.info(f"[EthTraceProvider] No trace data for tx {tx_hash[:16]}... on chain {chain_id}")
                return {"eth_trace": EthTraceData().model_dump()}

            trace_data = EthTraceData.from_raw_traces(raw_traces)
            logger.info(
                f"[EthTraceProvider] Fetched {trace_data.trace_count} traces for tx "
                f"{tx_hash[:16]}... on chain {chain_id} "
                f"(max_depth={trace_data.max_depth}, delegatecall={trace_data.has_delegatecall})"
            )
            return {"eth_trace": trace_data.model_dump(by_alias=True)}

        except Exception as e:
            logger.warning(f"[EthTraceProvider] Failed to fetch trace for tx {tx_hash[:16]}...: {e}")
            return {"_eth_trace_error": str(e)}


NodeRegistry.register(EthTraceProviderNode)
