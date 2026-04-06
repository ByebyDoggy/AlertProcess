"""
闪电贷检测器
============
继承 TxTraceAnalyzer 基类，在通用解析之上叠加闪电贷专项检测。

检测策略:
  Aave:     flashLoan() / flashLoanSimple() 调用
  Balancer: flash() 调用
  UniswapV3: flash() 调用

特征模式:
  同一交易内: borrow(借出) → 多个 swap 操作 → repay(还款+手续费)
  借还金额接近 (差额 = 手续费)

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
from detectors.trace.behaviors.base_behavior import BaseBehaviorDetector, FLASH_SELECTORS

logger = logging.getLogger(__name__)


class FlashLoanDetector(BaseBehaviorDetector):
    """
    闪电贷检测器

    用法:
        detector = FlashLoanDetector()
        result = await detector.analyze(tx_hash, chain_id)
        # result.behaviors 包含闪电贷检测结果
    """

    behavior_name = "flash_loan"
    behavior_label = "Flash Loan Detection"

    # 已知的闪电贷相关 selector (从 base_behavior 导入补充)
    KNOWN_FLASH_SELECTORS = FLASH_SELECTORS

    async def detect_behaviors(
        self, root: CallNode, tx_info: TransactionInfo
    ) -> list[BehaviorResult]:
        """
        重写父类的行为检测钩子
        先调用父类的通用 analyze(), 再叠加闪电贷专项检测
        """
        results: list[BehaviorResult] = []

        # 策略 1: 查找 flash* 相关调用
        flash_calls = self._find_flash_calls(root)
        if flash_calls:
            result = self._build_flash_result_from_calls(flash_calls, root)
            if result:
                results.append(result)

        # 策略 2: 分析借还金额模式 (通过 Transfer events)
        borrow_repay_result = self._analyze_borrow_repay_pattern(root, tx_info)
        if borrow_repay_result:
            results.append(borrow_repay_result)

        # 策略 3: 检测 Aave Pool 特征调用链
        aave_result = self._detect_aave_pattern(root)
        if aave_result:
            results.append(aave_result)

        return results

    def _find_flash_calls(self, root: CallNode) -> list[CallNode]:
        """遍历调用树查找所有 flash* 相关调用"""
        return self.find_nodes_by_selector_pattern(
            root, set(self.KNOWN_FLASH_SELECTORS.keys())
        )

    def _build_flash_result_from_calls(
        self, calls: list[CallNode], root: CallNode
    ) -> Optional[BehaviorResult]:
        """基于找到的 flash* 调用构建检测结果"""
        if not calls:
            return None

        details: dict = {}
        involved_addresses: list[str] = []
        trace_addrs: list[list[int]] = []
        flash_methods: list[str] = []
        tokens: list[str] = []

        for call in calls:
            method_name = self.KNOWN_FLASH_SELECTORS.get(
                call.selector, call.function_signature or "unknown"
            )
            flash_methods.append(method_name)
            trace_addrs.append(call.trace_address)

            # 尝试提取参数中的 token 地址
            for p in call.params:
                if p.type_hint == "address":
                    tokens.append(p.value)
                elif "asset" in p.name.lower() or "token" in p.name.lower():
                    tokens.append(p.value)

            if call.to_address:
                involved_addresses.append(call.to_address)
            if call.from_address:
                involved_addresses.append(call.from_address)

        # 去重
        involved_addresses = list(set(involved_addresses))

        confidence = min(0.95, 0.6 + 0.15 * len(calls))

        description = (
            f"Detected {len(calls)} flash loan operation(s): "
            + ", ".join(flash_methods)
        )

        details.update({
            "flashMethods": flash_methods,
            "callCount": len(calls),
            "tokensInvolved": tokens,
        })

        return self.build_behavior_result(
            behavior_type="flash_loan",
            label="Flash Loan",
            description=description,
            confidence=confidence,
            risk_level="medium",
            details=details,
            involved_addresses=involved_addresses,
            related_trace_addresses=trace_addrs,
        )

    def _analyze_borrow_repay_pattern(
        self, root: CallNode, tx_info: TransactionInfo
    ) -> Optional[BehaviorResult]:
        """
        分析借还金额模式
        如果同一交易中存在大额转入又转出的同种 token，可能是闪电贷
        """
        transfers = self.find_all_transfers(root)
        if len(transfers) < 2:
            return None

        # 按 token 地址分组
        by_token: dict[str, list[dict]] = {}
        for t in transfers:
            addr = t.get("tokenAddress", "").lower()
            by_token.setdefault(addr, []).append(t)

        suspicious_tokens: list[dict] = []

        for token_addr, txs in by_token.items():
            if len(txs) < 2:
                continue

            # 计算 IN/OUT
            total_in = 0
            total_out = 0
            sender_addr = tx_info.from_address.lower() if tx_info else ""
            for t in txs:
                try:
                    val = int(str(t.get("value", "0")).replace(",", ""))
                except ValueError:
                    val = 0
                if t.get("to", "").lower() == sender_addr:
                    total_in += val
                elif t.get("from", "").lower() == sender_addr:
                    total_out += val

            # 借还金额接近 (差额 < 10%)
            if total_in > 0 and total_out > 0:
                diff_pct = abs(total_in - total_out) / max(total_in, total_out)
                if diff_pct < 0.1 and total_in > 1e14:  # > 0.0001 ETH equivalent
                    suspicious_tokens.append({
                        "token": token_addr,
                        "borrowed": total_in,
                        "repaid": total_out,
                        "fee": abs(total_in - total_out),
                        "feePercent": round(diff_pct * 100, 4),
                    })

        if not suspicious_tokens:
            return None

        return self.build_behavior_result(
            behavior_type="flash_loan_pattern",
            label="Flash Loan Pattern (borrow-repay)",
            description=(
                f"Suspicious borrow-repay pattern detected across "
                f"{len(suspicious_tokens)} token(s)"
            ),
            confidence=0.75,
            risk_level="low",
            details={"patterns": suspicious_tokens},
        )

    def _detect_aave_pattern(self, root: CallNode) -> Optional[BehaviorResult]:
        """检测 Aave 闪电贷特征模式: borrow + repay 同一交易"""
        # 查找 Aave 相关调用
        aave_borrows = self.find_nodes_by_selector(root, "0x4a58c4c4")  # borrow
        aave_repays = self.find_nodes_by_selector(root, "0xa15cc3a3")   # repay

        if not aave_borrows and not aave_repays:
            return None

        involved: list[str] = []
        trace_addrs: list[list[int]] = []

        for c in aave_borrows + aave_repays:
            if c.to_address and c.to_address not in involved:
                involved.append(c.to_address)
            if c.trace_address not in trace_addrs:
                trace_addrs.append(c.trace_address)

        return self.build_behavior_result(
            behavior_type="aave_flash_loan",
            label="Aave Flash Loan",
            description=(
                f"Aave operations detected: "
                f"{len(aave_borrows)} borrow(s), {len(aave_repays)} repay(s)"
            ),
            confidence=0.90 if (aave_borrows and aave_repays) else 0.60,
            risk_level="medium" if (aave_borrows and aave_repays) else "low",
            details={
                "borrowCount": len(aave_borrows),
                "repayCount": len(aave_repays),
            },
            involved_addresses=involved,
            related_trace_addresses=trace_addrs,
        )
