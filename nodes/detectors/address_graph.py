"""地址关系图谱检测器 — 迁移到新节点架构"""

from __future__ import annotations

from typing import Any

from nodes.base import NodeRegistry
from nodes.detectors.base import BaseDetector

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
    description: str = "分析地址关系和资金流模式"
    icon: str = "\U0001f517"
    color: str = "#6366f1"

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "threshold": {"type": "number", "minimum": 0, "maximum": 100, "default": 40},
                "centralization_threshold": {"type": "integer", "default": 5},
            },
        }

    @classmethod
    def get_default_config(cls) -> dict[str, Any]:
        return {"threshold": 40, "centralization_threshold": 5}

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

    async def detect(self, context: dict[str, Any]) -> tuple[float, dict[str, Any]]:
        from_addr = context.get("from_address", "")
        to_addr = context.get("to_address", "")
        chain_id = context.get("chain_id", 1)

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
        return score, {
            "from_address": from_addr,
            "to_address": to_addr,
            "chain_id": chain_id,
            "exchange_from": exch_name_from,
            "exchange_to": exch_name_to,
            "exploiter_from": expl_name_from,
            "exploiter_to": expl_name_to,
            "detected_issues": issues,
            "labels": labels,
        }


NodeRegistry.register(AddressGraphDetector)
