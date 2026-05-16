"""
协议攻击检测器基类

所有基于 eth_trace 调用栈分析的协议攻击检测器继承此基类。
继承链: BaseNode → BaseDetector → BaseProtocolAttackDetector

核心能力:
  - 从 context.extra.eth_trace 提取标准化调用栈
  - 构建有序 CallStackEntry 列表（含函数签名解码）
  - 函数签名匹配、调用深度计算、调用序列模式匹配
  - 子类只需定义 ATTACK_PATTERNS 和实现 analyze_call_stack() 即可
"""

from __future__ import annotations

import logging
from abc import abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from nodes.base import NodeRegistry, score_to_severity
from nodes.context.require import require
from nodes.detectors.base import BaseDetector, DetectorConfigMixin, DetectorOutputMixin
from nodes.models import TransactionContext
from nodes.providers.eth_trace import EthTraceData, EthTraceEntry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 调用栈标准化模型
# ---------------------------------------------------------------------------

class CallStackEntry(BaseModel):
    """
    标准化调用栈条目 — 从 EthTraceEntry 提取的关键调用信息。

    Attributes:
        depth:       调用深度（trace_address 长度，0=顶层调用）
        from_addr:   调用方地址
        to_addr:     被调用方地址
        function_selector: 函数选择器（input_data 前 4 字节，如 "0x0906f8c8"）
        call_type:   调用类型 (call/delegatecall/staticcall/...)
        value:       转账金额 (wei, hex string)
        gas:         Gas 限制 (hex string)
        input_data:  完整 calldata
        trace_address: 原始层级路径
    """
    depth: int = Field(default=0, description="调用深度")
    from_addr: str = Field(default="", description="调用方地址")
    to_addr: str = Field(default="", description="被调用方地址")
    function_selector: str = Field(default="", description="函数选择器 (4 bytes hex)")
    call_type: str = Field(default="", description="调用类型")
    value: str = Field(default="0x0", description="转账金额")
    gas: str = Field(default="0x0", description="Gas 限制")
    input_data: str = Field(default="0x", description="完整 calldata")
    trace_address: list[int] = Field(default_factory=list, description="原始层级路径")


class AttackPattern(BaseModel):
    """
    攻击模式定义 — 子类通过此模型声明已知的攻击模式。

    Attributes:
        name:        模式名称（如 "aave_flash_loan_attack"）
        description: 模式描述
        function_selectors: 需要匹配的函数选择器列表（任一匹配即可）
        call_sequence: 调用序列（按顺序匹配的函数选择器列表）
        target_contracts: 目标合约地址列表（小写，可选）
        min_depth:   最小调用深度阈值（可选）
        max_depth:   最大调用深度阈值（可选）
        score_weight: 该模式的评分权重（0-100）
    """
    name: str = Field(description="模式名称")
    description: str = Field(default="", description="模式描述")
    function_selectors: list[str] = Field(default_factory=list, description="函数选择器列表")
    call_sequence: list[str] = Field(default_factory=list, description="调用序列")
    target_contracts: list[str] = Field(default_factory=list, description="目标合约地址")
    min_depth: int = Field(default=0, description="最小调用深度")
    max_depth: int = Field(default=0, description="最大调用深度，0=不限制")
    score_weight: float = Field(default=50.0, ge=0, le=100, description="评分权重")


# ---------------------------------------------------------------------------
# 匹配结果模型
# ---------------------------------------------------------------------------

class PatternMatch(BaseModel):
    """模式匹配结果"""
    pattern_name: str = Field(description="匹配的模式名称")
    matched_selectors: list[str] = Field(default_factory=list, description="匹配到的函数选择器")
    matched_contracts: list[str] = Field(default_factory=list, description="匹配到的合约地址")
    sequence_matched: bool = Field(default=False, description="调用序列是否完整匹配")
    partial_match: bool = Field(default=False, description="是否部分匹配")
    score_contribution: float = Field(default=0.0, description="该匹配的评分贡献")


class BehaviorEvidence(BaseModel):
    """通用行为证据，selector_based=False 的证据可作为主触发条件。"""
    kind: str = Field(description="证据类型")
    weight: float = Field(default=0.0, ge=0.0, le=100.0, description="评分权重")
    selector_based: bool = Field(default=False, description="是否来自 selector / 函数名命中")
    description: str = Field(default="", description="证据说明")
    entries: list[dict[str, Any]] = Field(default_factory=list, description="相关调用条目")


# ---------------------------------------------------------------------------
# 协议攻击检测器配置
# ---------------------------------------------------------------------------

class ProtocolAttackConfigMixin(DetectorConfigMixin):
    """协议攻击检测器通用配置"""
    threshold: float = Field(default=50.0, ge=0, le=100, description="0-100，评分达到此值视为 passed")
    min_trace_count: int = Field(default=2, ge=1, description="最小 trace 条目数，低于此值不检测")
    max_call_depth: int = Field(default=20, ge=1, description="最大分析调用深度")


# ---------------------------------------------------------------------------
# BaseProtocolAttackDetector 基类
# ---------------------------------------------------------------------------

@require("eth_trace")
class BaseProtocolAttackDetector(BaseDetector):
    """
    协议攻击检测器基类 — 基于 eth_trace 调用栈分析的通用协议攻击检测框架。

    继承链: BaseNode → BaseDetector → BaseProtocolAttackDetector

    子类必须:
      1. 定义 ATTACK_PATTERNS: list[AttackPattern] — 已知的攻击模式
      2. 实现 analyze_call_stack() — 对调用栈进行具体攻击模式分析

    子类可选:
      - 覆盖 ATTACK_TYPE_LABEL — 攻击类型标签
      - 覆盖 extract_extra_features() — 提取额外的检测特征

    通用能力:
      - _extract_eth_trace(): 从 context 获取标准化 EthTraceData
      - _build_call_stack(): 构建有序 CallStackEntry 列表
      - _match_function_signatures(): 函数签名匹配
      - _find_call_sequence(): 调用序列模式匹配
      - _match_patterns(): 批量模式匹配
    """

    # ── 子类必须覆盖 ──
    ATTACK_PATTERNS: list[AttackPattern] = []
    ATTACK_TYPE_LABEL: str = "protocol_attack"

    # ── Pydantic 配置模型 ──
    class ConfigModel(ProtocolAttackConfigMixin):
        pass

    # ── 内部方法：提取 eth_trace 数据 ──

    def _extract_eth_trace(self, tx_context: TransactionContext) -> EthTraceData | None:
        """
        从 context.extra 中提取标准化的 eth_trace 数据。

        Args:
            tx_context: 交易上下文

        Returns:
            EthTraceData 实例，如果不存在或格式错误则返回 None
        """
        raw = tx_context.get_extra("eth_trace")
        if not raw:
            logger.debug(f"[{self.__class__.__name__}] No eth_trace in context.extra")
            return None

        try:
            if isinstance(raw, dict):
                return EthTraceData.model_validate(raw)
            elif isinstance(raw, EthTraceData):
                return raw
            else:
                logger.warning(f"[{self.__class__.__name__}] Unexpected eth_trace type: {type(raw)}")
                return None
        except Exception as e:
            logger.error(f"[{self.__class__.__name__}] Failed to parse eth_trace: {e}", exc_info=True)
            return None

    # ── 内部方法：构建调用栈 ──

    def _build_call_stack(self, trace_data: EthTraceData) -> list[CallStackEntry]:
        """
        从 EthTraceData 构建有序调用栈列表。

        按 trace_address 排序（深度优先），提取每个调用的关键信息。

        Args:
            trace_data: 标准化的 trace 数据

        Returns:
            按 trace_address 排序的 CallStackEntry 列表
        """
        max_depth = self.config.get("max_call_depth", 20)
        entries: list[CallStackEntry] = []

        for entry in trace_data.traces:
            # 只处理 call 类型
            if entry.trace_type not in ("call", "create"):
                continue

            depth = len(entry.trace_address)
            if depth > max_depth:
                continue

            action = entry.action
            selector = self._extract_selector(action.input_data)

            entries.append(CallStackEntry(
                depth=depth,
                from_addr=action.from_addr.lower() if action.from_addr else "",
                to_addr=action.to_addr.lower() if action.to_addr else "",
                function_selector=selector,
                call_type=action.call_type.lower() if action.call_type else "",
                value=action.value,
                gas=action.gas,
                input_data=action.input_data,
                trace_address=entry.trace_address,
            ))

        # 按 trace_address 排序（深度优先遍历顺序）
        entries.sort(key=lambda e: e.trace_address)
        return entries

    @staticmethod
    def _extract_selector(input_data: str) -> str:
        """
        从 calldata 提取函数选择器（前 4 字节）。

        Args:
            input_data: calldata hex string

        Returns:
            函数选择器（如 "0x0906f8c8"），无效输入返回空字符串
        """
        if not input_data or input_data == "0x" or len(input_data) < 10:
            return ""
        return input_data[:10].lower()

    # ── 内部方法：函数签名匹配 ──

    @staticmethod
    def _match_function_signatures(
        call_stack: list[CallStackEntry],
        selectors: list[str],
    ) -> list[CallStackEntry]:
        """
        在调用栈中查找匹配指定函数选择器的调用条目。

        Args:
            call_stack: 调用栈列表
            selectors: 需要匹配的函数选择器列表（小写）

        Returns:
            匹配到的 CallStackEntry 列表
        """
        selector_set = {s.lower() for s in selectors}
        return [
            entry for entry in call_stack
            if entry.function_selector in selector_set
        ]

    # ── 内部方法：调用序列匹配 ──

    @staticmethod
    def _find_call_sequence(
        call_stack: list[CallStackEntry],
        sequence: list[str],
    ) -> tuple[bool, list[CallStackEntry]]:
        """
        在调用栈中查找是否按顺序出现了指定的函数调用序列。

        不要求连续，只要求相对顺序一致（子序列匹配）。

        Args:
            call_stack: 调用栈列表
            sequence: 期望的函数选择器序列（小写）

        Returns:
            (是否完整匹配, 匹配到的 CallStackEntry 列表)
        """
        if not sequence:
            return True, []

        matched: list[CallStackEntry] = []
        seq_idx = 0
        target = sequence[seq_idx].lower()

        for entry in call_stack:
            if entry.function_selector == target:
                matched.append(entry)
                seq_idx += 1
                if seq_idx >= len(sequence):
                    return True, matched
                target = sequence[seq_idx].lower()

        # 部分匹配
        return False, matched

    # ── 内部方法：批量模式匹配 ──

    def _match_patterns(
        self,
        call_stack: list[CallStackEntry],
        patterns: list[AttackPattern] | None = None,
    ) -> list[PatternMatch]:
        """
        对调用栈执行批量攻击模式匹配。

        对每个模式检查:
          1. 函数选择器匹配
          2. 调用序列匹配
          3. 目标合约匹配
          4. 深度阈值检查

        Args:
            call_stack: 调用栈列表
            patterns: 攻击模式列表，默认使用 self.ATTACK_PATTERNS

        Returns:
            PatternMatch 列表
        """
        patterns = patterns or self.ATTACK_PATTERNS
        results: list[PatternMatch] = []

        for pattern in patterns:
            matched_selectors: list[str] = []
            matched_contracts: list[str] = []
            sequence_matched = False
            score_contribution = 0.0

            # 1. 函数选择器匹配
            if pattern.function_selectors:
                matched_entries = self._match_function_signatures(
                    call_stack, pattern.function_selectors,
                )
                matched_selectors = [e.function_selector for e in matched_entries]
                matched_contracts = [e.to_addr for e in matched_entries]

                if not matched_entries:
                    continue

            # 2. 调用序列匹配
            if pattern.call_sequence:
                sequence_matched, seq_entries = self._find_call_sequence(
                    call_stack, pattern.call_sequence,
                )
                if not sequence_matched and not pattern.function_selectors:
                    # 序列模式未匹配且无独立选择器匹配，跳过
                    continue

            # 3. 目标合约匹配（可选）
            if pattern.target_contracts:
                target_set = {c.lower() for c in pattern.target_contracts}
                contract_matches = [
                    e for e in call_stack
                    if e.to_addr in target_set
                ]
                if not contract_matches and pattern.target_contracts:
                    # 有指定目标合约但未匹配
                    continue
                matched_contracts = [e.to_addr for e in contract_matches]

            # 4. 深度阈值检查
            max_call_depth = max((e.depth for e in call_stack), default=0)
            if pattern.min_depth > 0 and max_call_depth < pattern.min_depth:
                continue
            if pattern.max_depth > 0 and max_call_depth > pattern.max_depth:
                continue

            # 计算评分贡献
            partial_match = not sequence_matched if pattern.call_sequence else False
            if sequence_matched:
                score_contribution = pattern.score_weight
            elif matched_selectors:
                score_contribution = pattern.score_weight * 0.5
            elif matched_contracts:
                score_contribution = pattern.score_weight * 0.3

            results.append(PatternMatch(
                pattern_name=pattern.name,
                matched_selectors=matched_selectors,
                matched_contracts=matched_contracts,
                sequence_matched=sequence_matched,
                partial_match=partial_match,
                score_contribution=score_contribution,
            ))

        return results

    @staticmethod
    def _call_value_int(entry: CallStackEntry) -> int:
        try:
            return int(entry.value, 16) if str(entry.value).startswith("0x") else int(entry.value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _entry_summary(entry: CallStackEntry) -> dict[str, Any]:
        return {
            "depth": entry.depth,
            "from": entry.from_addr,
            "to": entry.to_addr,
            "selector": entry.function_selector,
            "call_type": entry.call_type,
            "value": entry.value,
            "trace_address": entry.trace_address,
        }

    @staticmethod
    def _max_call_depth(call_stack: list[CallStackEntry]) -> int:
        return max((entry.depth for entry in call_stack), default=0)

    @staticmethod
    def _count_unique_contracts(call_stack: list[CallStackEntry]) -> int:
        return len({entry.to_addr for entry in call_stack if entry.to_addr})

    @staticmethod
    def _has_delegatecall(call_stack: list[CallStackEntry]) -> bool:
        return any(entry.call_type == "delegatecall" for entry in call_stack)

    def _find_large_value_calls(
        self,
        call_stack: list[CallStackEntry],
        min_value_wei: int,
    ) -> list[CallStackEntry]:
        return [entry for entry in call_stack if self._call_value_int(entry) >= min_value_wei]

    @staticmethod
    def _cap_selector_only_score(
        score: float,
        evidence: list[BehaviorEvidence],
        cap: float = 45.0,
    ) -> float:
        if evidence and all(item.selector_based for item in evidence):
            return min(score, cap)
        return score

    # ── 子类可选覆盖：提取额外特征 ──

    def extract_extra_features(
        self,
        call_stack: list[CallStackEntry],
        trace_data: EthTraceData,
    ) -> dict[str, Any]:
        """
        提取额外的检测特征（子类可选覆盖）。

        Args:
            call_stack: 标准化调用栈
            trace_data: 原始 trace 数据

        Returns:
            额外特征字典
        """
        return {}

    # ── 子类必须实现：调用栈分析 ──

    @abstractmethod
    async def analyze_call_stack(
        self,
        call_stack: list[CallStackEntry],
        trace_data: EthTraceData,
        tx_context: TransactionContext,
    ) -> DetectorOutputMixin:
        """
        执行具体的协议攻击调用栈分析（子类必须实现）。

        基类已提供:
          - _match_patterns() — 批量模式匹配
          - _match_function_signatures() — 函数签名匹配
          - _find_call_sequence() — 调用序列匹配
          - extract_extra_features() — 额外特征提取

        Args:
            call_stack: 标准化调用栈
            trace_data: 原始 eth_trace 数据
            tx_context: 交易上下文

        Returns:
            DetectorOutputMixin（score, passed, severity, labels, detection）
        """
        ...

    # ── 重写 process() — 编排通用流程 ──

    async def process(self, tx_context: TransactionContext) -> DetectorOutputMixin:
        """
        协议攻击检测通用流程:
        1. 提取 eth_trace 数据
        2. 构建调用栈
        3. 调用子类 analyze_call_stack()

        如果 eth_trace 不存在或 trace 条目数不足，返回低分。
        """
        min_trace_count = self.config.get("min_trace_count", 2)
        threshold = self.config.get("threshold", 50.0)

        # 1. 提取 eth_trace
        trace_data = self._extract_eth_trace(tx_context)
        if trace_data is None:
            return DetectorOutputMixin(
                score=0.0, passed=False, severity="UNKNOWN",
                labels=[], detection={
                    "attack_type": self.ATTACK_TYPE_LABEL,
                    "error": "eth_trace not available in context",
                },
            )

        # 2. trace 条目数不足
        if trace_data.trace_count < min_trace_count:
            return DetectorOutputMixin(
                score=0.0, passed=False, severity="UNKNOWN",
                labels=[], detection={
                    "attack_type": self.ATTACK_TYPE_LABEL,
                    "trace_count": trace_data.trace_count,
                    "reason": f"trace_count {trace_data.trace_count} < min_trace_count {min_trace_count}",
                },
            )

        # 3. 构建调用栈
        call_stack = self._build_call_stack(trace_data)

        # 4. 调用子类分析
        try:
            result = await self.analyze_call_stack(call_stack, trace_data, tx_context)
        except Exception as e:
            logger.error(
                f"[{self.__class__.__name__}] analyze_call_stack() failed: {e}",
                exc_info=True,
            )
            return DetectorOutputMixin(
                score=0.0, passed=False, severity="UNKNOWN",
                labels=[], detection={
                    "attack_type": self.ATTACK_TYPE_LABEL,
                    "error": str(e),
                },
            )

        # 确保 score 在 0-100 范围内
        result.score = max(0.0, min(100.0, result.score))
        result.passed = result.score >= threshold
        result.severity = score_to_severity(result.score)

        return result
