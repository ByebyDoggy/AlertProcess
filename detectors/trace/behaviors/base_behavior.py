"""
行为检测器基类
==============
定义行为检测器的通用接口和工具方法。
所有具体行为检测器应继承此类 (或直接继承 TxTraceAnalyzer)。

参考文档: docs/dev-plan-trace-analysis.md §3.3
"""

import logging
from typing import Optional

from detectors.trace.analyzer import TxTraceAnalyzer
from detectors.trace.models import (
    CallNode,
    TransactionInfo,
    BehaviorResult,
    ProtocolInfo,
)

logger = logging.getLogger(__name__)

# 闪电贷相关已知 selector
FLASH_SELECTORS: dict[str, str] = {
    "0x8afff657": "flashLoan",
    "0xa5215b6a": "flashLoanSimple",
    "0x4124df37": "flash",          # Uniswap V3
    "0x1ca0cd81": "flash",           # Balancer V2
    "0xd96bfdf5": "executeFlashLoan", # Balancer V1
}

# 套利相关特征
ARBITRAGE_SELECTORS: dict[str, str] = {
    "0x38ed1739": "swapExactTokensForTokens",
    "0x18cbafe5": "swapExactTokensForETH",
    "0x7ff36ab5": "swapExactETHForTokens",
    "0xf305d719": "addLiquidityETH",
    "0xe8e33700": "addLiquidity",
    "0xbaa2abde": "removeLiquidity",
    "0x02751cec": "removeLiquidityETH",
    "0x414bf389": "exactInputSingle",
    "0xdb3e2198": "exactOutputSingle",
}


class BaseBehaviorDetector(TxTraceAnalyzer):
    """
    行为检测器抽象基类

    子类必须重写 detect_behaviors() 方法。
    提供通用的树遍历和节点搜索工具方法。
    """

    behavior_name: str = "base"
    behavior_label: str = "Base Detector"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def find_nodes_by_selector(self, root: CallNode, selector: str) -> list[CallNode]:
        """查找所有匹配指定 selector 的节点"""
        results: list[CallNode] = []
        stack = [root]
        visited: set[int] = set()
        target_sel = selector.lower() if len(selector) >= 10 else selector.lower().ljust(10, "0") if selector.startswith("0x") else "0x" + selector.lower().ljust(8, "0")

        while stack:
            node = stack.pop()
            nid = id(node)
            if nid in visited:
                continue
            visited.add(nid)
            if node.selector == target_sel:
                results.append(node)
            stack.extend(node.children)

        return results

    def find_nodes_by_selector_pattern(
        self, root: CallNode, selectors: set[str]
    ) -> list[CallNode]:
        """查找匹配任意一个 selector 的所有节点"""
        results: list[CallNode] = []
        normalized = {s.lower() for s in selectors}
        stack = [root]
        visited: set[int] = set()

        while stack:
            node = stack.pop()
            nid = id(node)
            if nid in visited:
                continue
            visited.add(nid)
            if node.selector.lower() in normalized:
                results.append(node)
            stack.extend(node.children)

        return results

    def find_nodes_with_label(self, root: CallNode, label_contains: str) -> list[CallNode]:
        """查找标签包含指定字符串的所有节点"""
        results: list[CallNode] = []
        stack = [root]
        visited: set[int] = set()
        keyword = label_contains.lower()

        while stack:
            node = stack.pop()
            nid = id(node)
            if nid in visited:
                continue
            visited.add(nid)
            if node.label and keyword in node.label.lower():
                results.append(node)
            stack.extend(node.children)

        return results

    def find_all_transfers(self, root: CallNode) -> list[dict]:
        """从事件中提取所有 Transfer 记录"""
        transfers: list[dict] = []
        stack = [root]
        visited: set[int] = set()

        while stack:
            node = stack.pop()
            nid = id(node)
            if nid in visited:
                continue
            visited.add(nid)
            for ev in node.events:
                if ev.name == "Transfer":
                    transfers.append({
                        "traceAddress": node.trace_address,
                        "from": ev.decoded.get("from", ""),
                        "to": ev.decoded.get("to", ""),
                        "value": ev.decoded.get("value", "0"),
                        "tokenAddress": ev.raw.get("address", "")
                        if ev.raw else "",
                    })
            stack.extend(node.children)

        return transfers

    def build_behavior_result(
        self,
        behavior_type: str,
        label: str,
        description: str,
        confidence: float,
        risk_level: str,
        details: dict | None = None,
        involved_addresses: list[str] | None = None,
        related_trace_addresses: list[list[int]] | None = None,
    ) -> BehaviorResult:
        """便捷方法: 构建 BehaviorResult"""
        return BehaviorResult(
            behavior_type=behavior_type,
            label=label,
            description=description,
            confidence=max(0.0, min(1.0, confidence)),
            risk_level=risk_level,
            details=details or {},
            involved_addresses=involved_addresses or [],
            related_trace_addresses=related_trace_addresses or [],
        )
