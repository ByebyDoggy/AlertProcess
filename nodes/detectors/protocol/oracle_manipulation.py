"""
预言机操纵检测器

基于 eth_trace 调用栈分析，检测预言机操纵攻击模式。
核心思路: 在同一交易中，攻击者先通过大额 swap 操纵流动性池价格，
然后利用被操纵的价格在依赖预言机的协议中进行获利操作。

检测特征:
  - 调用栈中出现大额 swap 操作 + 价格查询的时序关联
  - 同一交易内多次价格查询（可能是在操纵前后分别查询）
  - 调用深度异常（操纵攻击通常涉及多跳路由）
  - 预言机更新与利用的时间窗口极短（同区块）

前置依赖: ETH-Trace Provider (@require("eth_trace"))
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field

from nodes.base import NodeRegistry, score_to_severity
from nodes.detectors.base import DetectorOutputMixin
from nodes.detectors.protocol.base import (
    AttackPattern,
    BaseProtocolAttackDetector,
    CallStackEntry,
    PatternMatch,
)
from nodes.detectors.protocol.signatures import (
    ORACLE_EXPLOIT_SIGNATURES,
    ORACLE_MANIPULATION_SEQUENCE,
    ORACLE_MANIPULATION_SIGNATURES,
    ORACLE_PRICE_UPDATE_SIGNATURES,
    lookup_signature,
)
from nodes.models import TransactionContext
from nodes.providers.eth_trace import EthTraceData

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 攻击模式定义
# ---------------------------------------------------------------------------

ATTACK_PATTERNS: list[AttackPattern] = [
    AttackPattern(
        name="oracle_manipulation_full",
        description="预言机操纵完整攻击: 大额swap操纵价格→依赖预言机的操作",
        call_sequence=ORACLE_MANIPULATION_SEQUENCE,
        score_weight=85.0,
    ),
    AttackPattern(
        name="oracle_price_manipulation_swap",
        description="大额价格操纵 swap 操作",
        function_selectors=list(ORACLE_MANIPULATION_SIGNATURES.keys()),
        min_depth=3,
        score_weight=60.0,
    ),
    AttackPattern(
        name="oracle_price_query_suspicious",
        description="同一交易中多次价格查询，可能用于验证操纵效果",
        function_selectors=list(ORACLE_PRICE_UPDATE_SIGNATURES.keys()),
        score_weight=40.0,
    ),
    AttackPattern(
        name="oracle_price_exploit_action",
        description="价格查询后紧跟借贷/清算/铸币等利用动作",
        function_selectors=list(ORACLE_EXPLOIT_SIGNATURES.keys()),
        score_weight=55.0,
    ),
]


class OracleManipulationDetector(BaseProtocolAttackDetector):
    """
    预言机操纵检测器 — 基于 eth_trace 调用栈的预言机操纵攻击检测。

    检测能力:
    - 大额 swap 操纵价格 + 预言机查询的时序关联
    - 同一交易中多次价格查询
    - 多跳路由（Uniswap V2/V3 路由合约调用链）
    - 预言机更新与利用的极短时间窗口

    评分策略:
    - 完整操纵序列（swap→price_query）: 85+
    - 大额价格操纵 swap + 深度调用: 60+
    - 多次价格查询: 40
    - 调用深度异常深: +10~20
    """

    name: str = "oracle_manipulation_detector"
    label: str = "预言机操纵检测"
    description: str = "[数据需求: Trace(必需)] 基于ETH调用栈分析预言机操纵攻击：检测大额swap操纵价格+预言机查询的时序关联，识别同交易内的价格操纵模式"
    icon: str = "\U0001f4c8"
    color: str = "#9333ea"

    ATTACK_PATTERNS = ATTACK_PATTERNS
    ATTACK_TYPE_LABEL = "oracle_manipulation"

    class ConfigModel(BaseProtocolAttackDetector.ConfigModel):
        price_query_threshold: int = Field(
            default=2,
            ge=1,
            description="同一交易中价格查询次数阈值，超过此值增加评分",
        )
        suspicious_call_depth: int = Field(
            default=5,
            ge=1,
            description="可疑调用深度阈值，超过此值增加评分",
        )
        exploit_window_size: int = Field(
            default=3,
            ge=1,
            description="价格查询后在多少个调用内出现利用动作视为可疑",
        )

    async def analyze_call_stack(
        self,
        call_stack: list[CallStackEntry],
        trace_data: EthTraceData,
        tx_context: TransactionContext,
    ) -> DetectorOutputMixin:
        """
        预言机操纵调用栈分析流程:
        1. 执行模式匹配
        2. 分析价格查询频次
        3. 分析调用深度特征
        4. 检查 swap-价格查询时序关联
        5. 计算综合评分
        """
        # 1. 模式匹配
        matches = self._match_patterns(call_stack)

        # 2. 价格查询频次分析
        price_queries = self._count_price_queries(call_stack)
        price_query_threshold = self.config.get("price_query_threshold", 2)
        frequent_price_queries = price_queries >= price_query_threshold

        # 3. 调用深度分析
        max_depth = max((e.depth for e in call_stack), default=0)
        suspicious_depth = self.config.get("suspicious_call_depth", 5)
        deep_calls = max_depth >= suspicious_depth

        # 4. swap-价格查询时序关联
        swap_before_price = self._check_swap_before_price_query(call_stack)

        # 5. 多跳路由检测
        multi_hop = self._detect_multi_hop_routing(call_stack)

        # 6. 价格查询后的利用动作检测
        exploit_window_size = self.config.get("exploit_window_size", 3)
        exploit_after_price = self._check_price_query_before_exploit(call_stack, exploit_window_size)
        exploit_actions = self._collect_exploit_actions(call_stack)

        # 7. 计算评分
        score = self._calculate_score(
            matches, frequent_price_queries, deep_calls,
            swap_before_price, multi_hop, exploit_after_price, max_depth,
        )

        # 8. 构建结果
        labels = self._build_labels(
            matches, frequent_price_queries, deep_calls,
            swap_before_price, multi_hop, exploit_after_price,
        )
        detection = self._build_detection(
            call_stack, matches, price_queries, max_depth,
            frequent_price_queries, deep_calls, swap_before_price,
            multi_hop, exploit_after_price, exploit_actions, trace_data,
        )

        threshold = self.config.get("threshold", 50.0)
        return DetectorOutputMixin(
            score=score,
            passed=score >= threshold,
            severity=score_to_severity(score),
            labels=labels,
            detection=detection,
        )

    def _count_price_queries(self, call_stack: list[CallStackEntry]) -> int:
        """统计价格查询调用次数"""
        price_selectors = set(ORACLE_PRICE_UPDATE_SIGNATURES.keys())
        return sum(1 for e in call_stack if e.function_selector in price_selectors)

    def _check_swap_before_price_query(self, call_stack: list[CallStackEntry]) -> bool:
        """
        检查是否存在 swap 操作在价格查询之前的情况。

        时序关联: swap 出现在 price_query 之前 → 操纵嫌疑
        """
        swap_selectors = set(ORACLE_MANIPULATION_SIGNATURES.keys())
        price_selectors = set(ORACLE_PRICE_UPDATE_SIGNATURES.keys())

        found_swap = False
        for entry in call_stack:
            if entry.function_selector in swap_selectors:
                found_swap = True
            if found_swap and entry.function_selector in price_selectors:
                return True
        return False

    def _detect_multi_hop_routing(self, call_stack: list[CallStackEntry]) -> bool:
        """
        检测多跳路由 — 同一交易中出现多次 swap 调用。

        多跳路由通常意味着通过多个交易对进行价格操纵。
        """
        swap_selectors = set(ORACLE_MANIPULATION_SIGNATURES.keys())
        swap_count = sum(1 for e in call_stack if e.function_selector in swap_selectors)
        return swap_count >= 2

    def _check_price_query_before_exploit(
        self,
        call_stack: list[CallStackEntry],
        exploit_window_size: int,
    ) -> bool:
        """检查价格查询后是否在短窗口内出现利用动作。"""
        price_selectors = set(ORACLE_PRICE_UPDATE_SIGNATURES.keys())
        exploit_selectors = set(ORACLE_EXPLOIT_SIGNATURES.keys())

        for index, entry in enumerate(call_stack):
            if entry.function_selector not in price_selectors:
                continue
            for later_entry in call_stack[index + 1:index + 1 + exploit_window_size]:
                if later_entry.function_selector in exploit_selectors:
                    return True
        return False

    def _collect_exploit_actions(self, call_stack: list[CallStackEntry]) -> list[dict[str, Any]]:
        """收集调用栈中的利用动作摘要。"""
        exploit_selectors = set(ORACLE_EXPLOIT_SIGNATURES.keys())
        actions = []
        for entry in call_stack:
            if entry.function_selector not in exploit_selectors:
                continue
            actions.append({
                "depth": entry.depth,
                "selector": entry.function_selector,
                "signature": lookup_signature(entry.function_selector) or "",
                "to": entry.to_addr,
            })
        return actions

    def _calculate_score(
        self,
        matches: list[PatternMatch],
        frequent_price_queries: bool,
        deep_calls: bool,
        swap_before_price: bool,
        multi_hop: bool,
        exploit_after_price: bool,
        max_depth: int,
    ) -> float:
        """计算综合评分"""
        if not matches and not swap_before_price and not exploit_after_price:
            # 无模式匹配且无关键时序关联
            if frequent_price_queries:
                return 20.0
            return 0.0

        # 基础评分来自模式匹配
        base_score = max((m.score_contribution for m in matches), default=0.0)

        # 额外加分
        bonuses = 0.0

        # swap→价格查询时序关联（强特征）
        if swap_before_price:
            bonuses += 15.0

        # 价格查询→利用动作闭环（更强特征）
        if exploit_after_price:
            bonuses += 20.0

        # 多次价格查询
        if frequent_price_queries:
            bonuses += 10.0

        # 深度调用
        if deep_calls:
            bonuses += min(10.0, (max_depth - 5) * 2.0)

        # 多跳路由
        if multi_hop:
            bonuses += 10.0

        return min(100.0, base_score + bonuses)

    def _build_labels(
        self,
        matches: list[PatternMatch],
        frequent_price_queries: bool,
        deep_calls: bool,
        swap_before_price: bool,
        multi_hop: bool,
        exploit_after_price: bool,
    ) -> list[str]:
        """构建检测标签"""
        labels = []
        for m in matches:
            if m.sequence_matched:
                labels.append(f"ORACLE_MANIP_SEQ:{m.pattern_name}")
            elif m.matched_selectors:
                for sel in m.matched_selectors[:3]:  # 限制标签数量
                    sig = lookup_signature(sel)
                    labels.append(f"ORACLE_SIG:{sig or sel}")
        if swap_before_price:
            labels.append("ORACLE_SWAP_BEFORE_QUERY")
        if exploit_after_price:
            labels.append("ORACLE_QUERY_BEFORE_EXPLOIT")
        if frequent_price_queries:
            labels.append("ORACLE_FREQUENT_PRICE_QUERY")
        if deep_calls:
            labels.append("ORACLE_DEEP_CALL_STACK")
        if multi_hop:
            labels.append("ORACLE_MULTI_HOP_ROUTING")
        return labels

    def _build_detection(
        self,
        call_stack: list[CallStackEntry],
        matches: list[PatternMatch],
        price_queries: int,
        max_depth: int,
        frequent_price_queries: bool,
        deep_calls: bool,
        swap_before_price: bool,
        multi_hop: bool,
        exploit_after_price: bool,
        exploit_actions: list[dict[str, Any]],
        trace_data: EthTraceData,
    ) -> dict[str, Any]:
        """构建检测结果字典"""
        call_stack_summary = [
            {
                "depth": e.depth,
                "from": e.from_addr[:10] + "..." if e.from_addr else "",
                "to": e.to_addr[:10] + "..." if e.to_addr else "",
                "selector": e.function_selector,
                "signature": lookup_signature(e.function_selector) or "",
                "call_type": e.call_type,
            }
            for e in call_stack[:30]
        ]

        return {
            "attack_type": self.ATTACK_TYPE_LABEL,
            "trace_count": trace_data.trace_count,
            "max_depth": max_depth,
            "has_delegatecall": trace_data.has_delegatecall,
            "call_stack_size": len(call_stack),
            "price_query_count": price_queries,
            "pattern_matches": [m.model_dump() for m in matches],
            "features": {
                "frequent_price_queries": frequent_price_queries,
                "deep_calls": deep_calls,
                "swap_before_price_query": swap_before_price,
                "multi_hop_routing": multi_hop,
                "price_query_before_exploit": exploit_after_price,
            },
            "exploit_actions": exploit_actions,
            "call_stack_summary": call_stack_summary,
        }


NodeRegistry.register(OracleManipulationDetector)
