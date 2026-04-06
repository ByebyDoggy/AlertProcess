"""
Token 流转分析检测器
====================
分析交易中的 Token 流转模式：
- 大额转账检测
- 异常流转模式
- 多次 swap 检测

参考文档: docs/dev-plan-trace-analysis.md §3.3
"""

import logging
from typing import Optional

from detectors.trace.analyzer import TxTraceAnalyzer, shorten_addr
from detectors.trace.models import (
    CallNode,
    TransactionInfo,
    BehaviorResult,
)
from detectors.trace.behaviors.base_behavior import (
    BaseBehaviorDetector,
    ARBITRAGE_SELECTORS,
)

logger = logging.getLogger(__name__)


class TokenFlowDetector(BaseBehaviorDetector):
    """
    Token 流转与异常行为检测器

    检测内容:
      - 大额 ERC20 转账
      - 多步 DEX swap 操作序列 (可能的套利或 MEV)
      - approve + transferFrom 配对操作
    """

    behavior_name = "token_flow"
    behavior_label = "Token Flow Analysis"

    # 大额转账阈值 (默认 100 ETH 等值)
    LARGE_TRANSFER_THRESHOLD = int(1e20)  # 100 ETH in wei

    async def detect_behaviors(
        self, root: CallNode, tx_info: TransactionInfo
    ) -> list[BehaviorResult]:
        results: list[BehaviorResult] = []

        # 检测 1: 大额转账
        large_transfer_result = self._detect_large_transfers(root, tx_info)
        if large_transfer_result:
            results.append(large_transfer_result)

        # 检测 2: 多步 swap 序列 (套利候选)
        arb_result = self._detect_swap_sequence(root, tx_info)
        if arb_result:
            results.append(arb_result)

        # 检测 3: approve-transferFrom 配对
        approval_result = self._detect_approval_patterns(root)
        if approval_result:
            results.append(approval_result)

        return results

    def _detect_large_transfers(
        self, root: CallNode, tx_info: TransactionInfo
    ) -> Optional[BehaviorResult]:
        """检测超过阈值的大额转账"""
        transfers = self.find_all_transfers(root)
        large_ones: list[dict] = []

        for t in transfers:
            try:
                val = int(str(t.get("value", "0")).replace(",", ""))
            except ValueError:
                val = 0
            if val >= self.LARGE_TRANSFER_THRESHOLD:
                t["amountRaw"] = val
                large_ones.append(t)

        if not large_ones:
            return None

        involved = list(set(
            t.get("from", "") for t in large_ones
        ) | set(
            t.get("to", "") for t in large_ones
        ))

        return self.build_behavior_result(
            behavior_type="large_transfer",
            label="Large Token Transfer(s)",
            description=(
                f"Detected {len(large_ones)} transfer(s) exceeding threshold "
                f"(>={self.LARGE_TRANSFER_THRESHOLD / 1e18:.0f} ETH equiv)"
            ),
            confidence=0.80,
            risk_level="info",
            details={
                "transfers": [
                    {
                        "from": t.get("from", ""),
                        "to": t.get("to", ""),
                        "value": t.get("amountRaw", 0),
                        "token": t.get("tokenAddress", ""),
                    }
                    for t in large_ones
                ],
            },
            involved_addresses=involved,
        )

    def _detect_swap_sequence(
        self, root: CallNode, tx_info: TransactionInfo
    ) -> Optional[BehaviorResult]:
        """检测多步 swap 操作序列 (套利候选)"""
        swap_calls = self.find_nodes_by_selector_pattern(
            root, set(ARBITRAGE_SELECTORS.keys())
        )

        if len(swap_calls) < 2:
            return None

        swap_details: list[dict] = []
        trace_addrs: list[list[int]] = []
        involved: list[str] = []

        for call in swap_calls:
            method = ARBITRAGE_SELECTORS.get(
                call.selector, call.function_signature or "unknown"
            )
            swap_details.append({
                "method": method,
                "to": call.to_address,
                "label": call.label or "",
                "traceAddress": call.trace_address,
                "value": call.value,
            })
            trace_addrs.append(call.trace_address)
            if call.to_address and call.to_address not in involved:
                involved.append(call.to_address)

        return self.build_behavior_result(
            behavior_type="swap_sequence",
            label="Multi-step Swap Sequence",
            description=(
                f"Detected {len(swap_calls)} swap operation(s) in single transaction "
                f"— possible arbitrage or MEV activity"
            ),
            confidence=min(0.92, 0.50 + 0.07 * len(swap_calls)),
            risk_level="low" if len(swap_calls) <= 3 else "medium",
            details={
                "swapCount": len(swap_calls),
                "swaps": swap_details,
            },
            involved_addresses=involved,
            related_trace_addresses=trace_addrs,
        )

    def _detect_approval_patterns(self, root: CallNode) -> Optional[BehaviorResult]:
        """检测 approve + transferFrom 配对模式"""
        approves = self.find_nodes_by_selector(root, "0x095ea7b3")   # approve
        transfer_froms = self.find_nodes_by_selector(root, "0x23b872dd")  # transferFrom

        if not approves and not transfer_froms:
            return None

        return self.build_behavior_result(
            behavior_type="approval_pattern",
            label="ERC20 Approval Pattern",
            description=(
                f"Found {len(approves)} approve(s), {len(transfer_froms)} transferFrom(s)"
            ),
            confidence=0.55,
            risk_level="info",
            details={
                "approveCount": len(approves),
                "transferFromCount": len(transfer_froms),
            },
        )
