"""
检测原语模块

提供可复用的检测原语，包括：
- 日志解析（TransferParser, SwapParser, ApprovalParser）
- 计算器（ROICalculator, PriceImpactCalculator）
- 时序匹配（SequenceMatcher）
"""

from nodes.primitives.log_parser import (
    TransferEvent,
    SwapEvent,
    ApprovalEvent,
    TransferParser,
    SwapParser,
    ApprovalParser,
    TRANSFER_TOPIC,
    APPROVAL_TOPIC,
    SWAP_V2_TOPIC,
    SWAP_V3_TOPIC,
)

__all__ = [
    "TransferEvent",
    "SwapEvent",
    "ApprovalEvent",
    "TransferParser",
    "SwapParser",
    "ApprovalParser",
    "TRANSFER_TOPIC",
    "APPROVAL_TOPIC",
    "SWAP_V2_TOPIC",
    "SWAP_V3_TOPIC",
]
