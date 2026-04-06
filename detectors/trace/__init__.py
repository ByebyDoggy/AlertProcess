"""
交易调用链分析模块 (detectors/trace)
=====================================
基于 BlockSec Phalcon Explorer 的 Invocation Flow 功能实现。

模块结构:
  - analyzer:      TxTraceAnalyzer 基类 (交易解析核心)
  - models:        数据模型 (CallNode, FullAnalysisResult 等)
  - provider:      多节点 RPC 客户端
  - signature_db:  本地 4-byte 签名数据库
  - protocol_registry: 协议地址标签库
  - behaviors:     行为检测器 (闪电贷/套利等)
"""

from detectors.trace.models import (
    CallType,
    DecodedParam,
    EventRecord,
    CallNode,
    TransactionInfo,
    ProtocolInfo,
    BehaviorResult,
    TokenFlowItem,
    FullAnalysisResult,
)
from detectors.trace.analyzer import TxTraceAnalyzer
from detectors.trace.signature_db import SignatureDB
from detectors.trace.protocol_registry import ProtocolRegistry
from detectors.trace.provider import MultiRpcClient

__all__ = [
    "CallType",
    "DecodedParam",
    "EventRecord",
    "CallNode",
    "TransactionInfo",
    "ProtocolInfo",
    "BehaviorResult",
    "TokenFlowItem",
    "FullAnalysisResult",
    "TxTraceAnalyzer",
    "SignatureDB",
    "ProtocolRegistry",
    "MultiRpcClient",
]
