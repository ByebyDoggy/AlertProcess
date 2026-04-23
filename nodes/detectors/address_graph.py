"""地址关系图谱检测器 — 迁移到新节点架构"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from nodes.base import NodeRegistry, score_to_severity
from nodes.detectors.base import BaseDetector, DetectorConfigMixin, DetectorOutputMixin
from nodes.models import TransactionContext

KNOWN_EXCHANGE_ADDRESSES: dict[int, dict[str, str]] = {
    1: {
        "0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be": "Binance",
        "0x28c6c06298d514db089934071355e5743bf21d60": "Binance Hot",
        "0x9696f03e6f8ead66a066d010c4ec4a437b41374f": "Kraken",
    },
    56: {"0x0000000000000000000000000000000000000001": "BSC Validator"},
}

KNOWN_EXPLOITER_ADDRESSES: dict[str, str] = {
    "0xab7535b4a1b3c2d2c7e7c7c7c7c7c7c7c7c7c7": "Known Exploiter",
}


class AddressGraphOutput(DetectorOutputMixin):
    """地址关系图谱检测器输出"""
    pass


class AddressGraphDetector(BaseDetector):
    """
    地址关系图谱检测器 — 分析地址关系和资金流模式。

    评分:
    - 已知攻击者交互 → 95
    - 交易所交互 → 40
    - 可疑关系 → 50
    """

    name: str = "address_graph_detector"
    label: str = "地址关系图谱"

    # ── Pydantic 配置模型 (继承 DetectorConfigMixin，包含共享的 threshold) ──
    class ConfigModel(DetectorConfigMixin):
        threshold: float = Field(default=40.0, ge=0, le=100, description="passed 阈值")
        centralization_threshold: int = Field(default=5, ge=0, description="中心化阈值（关联交易所数）")

    description: str = "基于已知地址数据库分析交易双方关系：与已知攻击者地址交互给 95 分、交易所地址交互 40 分。用于追踪资金流向和识别洗钱路径"
    icon: str = "\U0001f517"
    color: str = "#6366f1"

    # ── Pydantic 输出模型 ──
    OutputModel: type = AddressGraphOutput

    def _check_exchange(self, address: str, chain_id: int) -> tuple[bool, str | None]:
        if not address:
            return False, None
        exchanges = KNOWN_EXCHANGE_ADDRESSES.get(chain_id, {})
        name = exchanges.get(address.lower())
        return name is not None, name

    def _check_exploiter(self, address: str) -> tuple[bool, str | None]:
        if not address:
            return False, None
        name = KNOWN_EXPLOITER_ADDRESSES.get(address.lower())
        return name is not None, name

    async def process(self, tx_context: TransactionContext) -> AddressGraphOutput:
        from_addr = tx_context.from_address or ""
        to_addr = tx_context.to_address or ""
        chain_id = tx_context.chain_id or 1

        issues: list[str] = []
        score = 0.0

        exch_from, exch_name_from = self._check_exchange(from_addr, chain_id)
        exch_to, exch_name_to = self._check_exchange(to_addr, chain_id)
        expl_from, expl_name_from = self._check_exploiter(from_addr)
        expl_to, expl_name_to = self._check_exploiter(to_addr)

        if expl_from:
            issues.append(f"EXPLOITER_ORIGIN:{expl_name_from}")
            score = max(score, 95)
        if expl_to:
            issues.append(f"EXPLOITER_DESTINATION:{expl_name_to}")
            score = max(score, 95)
        if exch_from:
            issues.append(f"EXCHANGE_ORIGIN:{exch_name_from}")
            score = max(score, 40)
        if exch_to:
            issues.append(f"EXCHANGE_DESTINATION:{exch_name_to}")
            score = max(score, 40)

        labels = issues if score >= self.config.get("threshold", 40) else []
        threshold = self.config.get("threshold", 40.0)
        return AddressGraphOutput(
            score=score,
            passed=score >= threshold,
            severity=score_to_severity(score),
            labels=labels,
            detection={
                "from_address": from_addr,
                "to_address": to_addr,
                "chain_id": chain_id,
                "exchange_from": exch_name_from,
                "exchange_to": exch_name_to,
                "exploiter_from": expl_name_from,
                "exploiter_to": expl_name_to,
                "detected_issues": issues,
                "labels": labels,
            },
        )


NodeRegistry.register(AddressGraphDetector)
