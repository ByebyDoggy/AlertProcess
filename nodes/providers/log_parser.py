"""
LogParserProvider 节点

预解析交易日志中的标准事件（Transfer/Swap/Approval），注入到 context.extra 供下游检测器使用。
"""

from __future__ import annotations

from typing import Any

from nodes.base import NodeRegistry
from nodes.providers.base import BaseContextProviderNode
from nodes.models import TransactionContext
from nodes.primitives.log_parser import TransferParser, SwapParser, ApprovalParser


@NodeRegistry.register
class LogParserProviderNode(BaseContextProviderNode):
    """
    日志解析 Provider 节点

    预解析交易日志中的标准事件：
    - Transfer 事件（ERC-20/ERC-721）
    - Swap 事件（Uniswap V2/V3）
    - Approval 事件（ERC-20/ERC-721）

    解析结果注入到 context.extra 中：
    - parsed_transfers: List[dict]
    - parsed_swaps: List[dict]
    - parsed_approvals: List[dict]
    """

    name = "log_parser_provider"
    label = "日志解析器"
    description = "预解析交易日志中的标准事件（Transfer/Swap/Approval）"
    icon = "📋"
    color = "#9C27B0"

    provides = ["parsed_transfers", "parsed_swaps", "parsed_approvals"]

    async def fetch(self, tx_context: TransactionContext) -> dict[str, Any]:
        """解析交易日志，返回标准事件列表"""
        logs = tx_context.logs or []

        # 解析各类事件
        transfers = TransferParser.parse(logs)
        swaps = SwapParser.parse(logs)
        approvals = ApprovalParser.parse(logs)

        # 转换为字典格式
        return {
            "parsed_transfers": [
                {
                    "token_address": t.token_address,
                    "from_address": t.from_address,
                    "to_address": t.to_address,
                    "amount": t.amount,
                    "log_index": t.log_index,
                }
                for t in transfers
            ],
            "parsed_swaps": [
                {
                    "dex_address": s.dex_address,
                    "token_in": s.token_in,
                    "token_out": s.token_out,
                    "amount_in": s.amount_in,
                    "amount_out": s.amount_out,
                    "log_index": s.log_index,
                    "version": s.version,
                }
                for s in swaps
            ],
            "parsed_approvals": [
                {
                    "token_address": a.token_address,
                    "owner": a.owner,
                    "spender": a.spender,
                    "amount": a.amount,
                    "log_index": a.log_index,
                }
                for a in approvals
            ],
        }
