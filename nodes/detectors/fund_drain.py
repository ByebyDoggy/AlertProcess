"""资金外流检测器

检测大额 ETH/ERC-20 转出。

支持:
  1. 独立检测：检查当前交易的资金流出
  2. 关联检测：从 tx_context.extra 读取 Combiner 注入的关联地址（如 upgraded_contracts），
     若资金转出方匹配关联地址，则提高评分

关联地址的来源由上游 Combiner 节点决定（可能来自 MemoryNode、Provider 等），
本检测器不直接依赖任何记忆系统。
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field

from nodes.base import NodeRegistry, score_to_severity
from nodes.detectors.base import BaseDetector, DetectorConfigMixin, DetectorOutputMixin
from nodes.models import TransactionContext


class FundDrainOutput(DetectorOutputMixin):
    """资金外流检测器输出"""
    pass


logger = logging.getLogger(__name__)

# ERC-20 Transfer 事件 Topic
ERC20_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


def _hex_to_int(val: Any) -> int:
    if isinstance(val, int):
        return val
    if isinstance(val, str) and val.startswith("0x"):
        try:
            return int(val, 16)
        except ValueError:
            return 0
    return 0


def _extract_topic0(log: dict) -> str:
    topics = log.get("topics", [])
    if not topics:
        return ""
    t = topics[0]
    return (t if isinstance(t, str) else t.hex() if isinstance(t, bytes) else "").lower()


def _extract_address_from_topic(topic: str) -> str:
    h = topic.lstrip("0x").lower()
    return "0x" + h[-40:] if len(h) >= 40 else ""


class FundDrainDetector(BaseDetector):
    """
    资金外流检测器 — 检测大额 ETH/ERC-20 转出。

    支持:
      1. 独立检测：检查当前交易的资金流出
      2. 关联检测：从 tx_context.extra 读取由 Combiner 注入的关联地址列表，
         若资金转出方匹配关联地址（如被升级的合约），则提高评分至 CRITICAL

    关联检测配置:
      - correlation_fields: extra 中要匹配的地址列表字段名（默认 ["upgraded_contracts"]）
        数据来源由上游 Combiner 节点注入，本检测器不直接依赖 MemoryStore
    """

    name: str = "fund_drain_detector"
    label: str = "资金外流检测"
    description: str = (
        "检测大额 ETH/ERC-20 资金转出。"
        "配合 Combiner 节点注入的关联地址（如代理升级合约列表），"
        "实现跨交易关联检测：关联地址 + 大额转出 → 95 分。"
        "独立使用时，大额转出 → 60 分。"
    )
    icon: str = "\U0001f4b8"
    color: str = "#ef4444"

    # ── Pydantic 配置模型 (继承 DetectorConfigMixin，包含共享的 threshold) ──
    class ConfigModel(DetectorConfigMixin):
        eth_large_threshold: float = Field(default=10, ge=0, description="ETH 大额转出阈值（ETH 数量）")
        eth_medium_threshold: float = Field(default=1, ge=0, description="ETH 中额转出阈值（ETH 数量）")
        check_erc20_transfers: bool = Field(default=True, description="是否检查 ERC-20 Transfer 事件")
        erc20_large_threshold: float = Field(default=10000, ge=0, description="ERC-20 大额转出阈值（token 数量）")
        correlation_fields: list[str] = Field(
            default=["upgraded_contracts"],
            description="关联检测：从 extra 中读取的地址列表字段名（由 Combiner 注入）",
        )
        watch_addresses: list[str] = Field(default=[], description="监控的地址列表（空=自动提取）")

    # ── Pydantic 输出模型 ──
    OutputModel: type = FundDrainOutput

    def _get_watch_addresses(self, tx_context: TransactionContext) -> set[str]:
        """获取监控地址集合"""
        explicit = self.config.get("watch_addresses", [])
        if explicit:
            return {a.lower() for a in explicit if isinstance(a, str)}

        # 自动从 tx_context 提取
        addrs = set()
        for key in ("exploiter_address", "from_address", "attacked_address", "to_address"):
            val = tx_context.extra.get(key) or (getattr(tx_context, key, None) if hasattr(tx_context, key) else None)
            if isinstance(val, str) and val.startswith("0x"):
                addrs.add(val.lower())
        return addrs

    def _get_correlated_addresses(self, tx_context: TransactionContext) -> set[str]:
        """
        从 tx_context.extra 中读取关联地址集合。

        关联地址由上游 Combiner 节点注入（来自 MemoryNode 或其他数据源）。
        本检测器不直接依赖 MemoryStore，完全解耦。
        """
        correlation_fields: list[str] = self.config.get("correlation_fields", ["upgraded_contracts"])
        addrs: set[str] = set()

        for field_name in correlation_fields:
            value = tx_context.extra.get(field_name, [])
            if isinstance(value, str):
                value = [value]
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item.startswith("0x"):
                        addrs.add(item.lower())

        return addrs

    async def process(self, tx_context: TransactionContext) -> FundDrainOutput:
        tx_value = _hex_to_int(tx_context.extra.get("value_wei") or tx_context.value or 0)
        from_addr = (tx_context.from_address or "").lower()
        to_addr = (tx_context.to_address or "").lower()
        logs: list[dict] = tx_context.logs or []
        chain_id = tx_context.chain_id or 1

        watch_addrs = self._get_watch_addresses(tx_context)
        eth_large = self.config.get("eth_large_threshold", 10)
        eth_medium = self.config.get("eth_medium_threshold", 1)
        eth_large_wei = int(eth_large * 10**18)
        eth_medium_wei = int(eth_medium * 10**18)
        erc20_large = self.config.get("erc20_large_threshold", 10000)

        drain_events: list[dict] = []
        max_severity = "none"

        # ── 检查 ETH 原生转出 ──
        if tx_value > 0 and from_addr in watch_addrs:
            severity = "large" if tx_value >= eth_large_wei else (
                "medium" if tx_value >= eth_medium_wei else "small"
            )
            drain_events.append({
                "type": "eth_transfer",
                "from": from_addr,
                "to": to_addr,
                "value_eth": tx_value / 10**18,
                "severity": severity,
            })
            if severity == "large" or (severity == "medium" and max_severity != "large"):
                max_severity = severity
            elif severity == "small" and max_severity == "none":
                max_severity = severity

        # ── 检查 ERC-20 Transfer ──
        if self.config.get("check_erc20_transfers", True) and logs:
            for log in logs:
                topic0 = _extract_topic0(log)
                if topic0 != ERC20_TRANSFER_TOPIC.lower():
                    continue

                topics = log.get("topics", [])
                token_from = _extract_address_from_topic(topics[1]) if len(topics) > 1 else ""
                token_to = _extract_address_from_topic(topics[2]) if len(topics) > 2 else ""

                if token_from in watch_addrs:
                    data = log.get("data", "0x")
                    amount = _hex_to_int(data) if data else 0
                    erc20_large_wei = int(erc20_large * 10**18)
                    severity = "large" if amount >= erc20_large_wei else (
                        "medium" if amount >= erc20_large_wei // 10 else "small"
                    )
                    drain_events.append({
                        "type": "erc20_transfer",
                        "token_contract": (log.get("address") or "").lower(),
                        "from": token_from,
                        "to": token_to,
                        "amount": amount,
                        "severity": severity,
                    })
                    # 更新最大严重度
                    severity_rank = {"none": 0, "small": 1, "medium": 2, "large": 3}
                    if severity_rank.get(severity, 0) > severity_rank.get(max_severity, 0):
                        max_severity = severity

        if not drain_events:
            return FundDrainOutput(
                score=0.0, passed=True, severity="UNKNOWN", labels=[],
                detection={"reason": "no significant fund drain detected"},
            )

        # ── 关联检测（从 extra 读取，来源是 Combiner 合并注入） ──
        correlation_found = False
        correlated_events: list[dict] = []
        correlated_addrs = self._get_correlated_addresses(tx_context)

        if correlated_addrs:
            # 检查是否有转出地址匹配关联地址列表
            for drain in drain_events:
                drain_from = drain.get("from", "").lower()
                if drain_from in correlated_addrs:
                    correlation_found = True
                    correlated_events.append({
                        "drain": drain,
                        "matched_address": drain_from,
                        "correlation_source": "extra",
                    })

        # ── 评分 ──
        issues: list[str] = []
        score = 0.0

        if correlation_found and max_severity == "large":
            score = 95.0
            issues.append("CORRELATED_DRAIN_LARGE")
        elif correlation_found and max_severity == "medium":
            score = 80.0
            issues.append("CORRELATED_DRAIN_MEDIUM")
        elif correlation_found and max_severity == "small":
            score = 65.0
            issues.append("CORRELATED_DRAIN_SMALL")
        elif max_severity == "large":
            score = 60.0
            issues.append("LARGE_DRAIN_NO_CORRELATION")
        elif max_severity == "medium":
            score = 40.0
            issues.append("MEDIUM_DRAIN_NO_CORRELATION")
        else:
            score = 20.0
            issues.append("SMALL_DRAIN")

        for drain in drain_events:
            issues.append(
                f"DRAIN:{drain['type']} "
                f"from={drain.get('from', '?')[:10]}... "
                f"severity={drain['severity']}"
            )

        labels = issues if score >= self.config.get("threshold", 50) else []

        return FundDrainOutput(
            score=score,
            passed=score >= self.config.get("threshold", 50),
            severity=score_to_severity(score),
            labels=labels,
            detection={
                "detected_issues": issues,
                "labels": labels,
                "drain_events": drain_events,
                "max_severity": max_severity,
                "correlation_found": correlation_found,
                "correlated_events": correlated_events,
                "correlated_address_count": len(correlated_addrs),
                "drain_count": len(drain_events),
            },
        )


NodeRegistry.register(FundDrainDetector)
