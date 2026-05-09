"""地址年龄检测器

检测新建地址的交易行为。地址年龄数据通过 MoralisAddressProviderNode 节点预先填充。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import Field

from nodes.base import NodeRegistry, score_to_severity
from nodes.detectors.base import BaseDetector, DetectorConfigMixin, DetectorOutputMixin
from nodes.models import TransactionContext


def _get_reference_time(tx_context: TransactionContext) -> datetime:
    """
    获取参考时间（用于回测）。

    优先级:
      1. tx_context.timestamp / tx_timestamp — 交易发生时间
      2. datetime.now() — 实时检测回退到系统当前时间
    """
    ts_val = tx_context.timestamp or tx_context.extra.get("tx_timestamp")
    if not ts_val:
        return datetime.now(timezone.utc)
    try:
        if isinstance(ts_val, (int, float)):
            return datetime.fromtimestamp(ts_val, tz=timezone.utc)
        s = str(ts_val).strip()
        if s.isdigit():
            return datetime.fromtimestamp(int(s), tz=timezone.utc)
        ct = datetime.fromisoformat(s)
        if ct.tzinfo is None:
            ct = ct.replace(tzinfo=timezone.utc)
        return ct
    except (ValueError, TypeError, OSError):
        return datetime.now(timezone.utc)


def _estimate_age_by_blocks(tx_context: TransactionContext | dict[str, Any]) -> int | None:
    """
    基于区块差估算地址年龄（天数）。

    计算: (tx_block_number - first_block_number) * block_time(秒) / 86400

    Returns:
        年龄天数(int)，如果无法估算返回 None
    """
    if isinstance(tx_context, dict):
        raw = tx_context
        first_block_raw = raw.get("first_block_number")
        tx_block_raw = raw.get("block_number")
        chain_id_raw = raw.get("chain_id", 1)
    else:
        first_block_raw = tx_context.extra.get("first_block_number")
        tx_block_raw = tx_context.block_number
        chain_id_raw = tx_context.chain_id or 1

    if first_block_raw is None or tx_block_raw is None:
        return None
    try:
        first_block = int(first_block_raw)
        tx_block = int(tx_block_raw)
    except (ValueError, TypeError):
        return None

    if tx_block <= first_block:
        return None

    try:
        chain_id = int(chain_id_raw or 1)
    except (ValueError, TypeError):
        chain_id = 1

    from nodes.context.providers.moralis_address import get_block_time
    block_sec = get_block_time(chain_id)

    age_seconds = (tx_block - first_block) * block_sec
    age_days = max(0, int(age_seconds / 86400))
    return age_days


class AddressAgeOutput(DetectorOutputMixin):
    """地址年龄检测器输出"""
    pass


class AddressAgeDetector(BaseDetector):
    """
    地址年龄检测器 — 检测新建地址的交易行为。

    地址年龄数据通过 MoralisAddressProviderNode 节点预先填充到 tx_context.extra:
      - address_create_time: 地址创建时间 ISO8601 格式
      - address_age_days: 地址创建距今天数
      - first_block_number: 首次交易所在区块号

    评分:
    - 地址创建 < 1 天 → 90
    - 地址创建 < 阈值天数 → 70
    - 地址创建 < 2x阈值 → 40
    - 无数据 → 0
    """

    name: str = "address_age_detector"
    label: str = "地址年龄检测"
    description: str = "[数据需求: 仅交易基础字段] 检测交易涉及的新建地址风险：通过 MoralisAddressProviderNode 预先填充地址年龄数据，<1 天给 90 分，< 阈值天数给 70 分"
    icon: str = "\U0001f4c5"
    color: str = "#14b8a6"

    # ── Pydantic 配置模型 (继承 DetectorConfigMixin，包含共享的 threshold) ──
    class ConfigModel(DetectorConfigMixin):
        """地址年龄检测器配置 — Pydantic 自动校验 + JSON Schema 生成"""
        new_address_threshold_days: int = Field(default=3, ge=0, description="新建地址阈值（天）")

    # ── Pydantic 输出模型 ──
    OutputModel: type = AddressAgeOutput

    async def process(self, tx_context: TransactionContext) -> AddressAgeOutput:
        address = tx_context.extra.get("exploiter_address") or tx_context.from_address or ""
        if not address:
            return AddressAgeOutput(
                score=0.0, passed=True, severity="UNKNOWN", labels=[], detection={"error": "no address available"}
            )

        create_time_str = tx_context.extra.get("address_create_time")
        age_days = _estimate_age_by_blocks(tx_context)

        if age_days is not None and age_days >= 0:
            score, details = self._score_by_age(age_days)
            details["age_method"] = "block_estimate"
        elif create_time_str:
            ref_time = _get_reference_time(tx_context)
            try:
                ct = datetime.fromisoformat(str(create_time_str))
                if ct.tzinfo is None:
                    ct = ct.replace(tzinfo=timezone.utc)
                days = (ref_time - ct).days
                score, details = self._score_by_age(days)
                details["age_method"] = "time_delta"
            except Exception:
                return AddressAgeOutput(
                    score=0.0, passed=True, severity="UNKNOWN", labels=[],
                    detection={"error": "invalid create_time format", "address": address}
                )
        else:
            return AddressAgeOutput(
                score=0.0, passed=True, severity="UNKNOWN", labels=[],
                detection={"address": address, "reason": "no age data (MoralisAddressProviderNode not connected or unavailable)"}
            )

        details["address"] = address
        threshold = self.config.get("threshold", 50.0)
        return AddressAgeOutput(
            score=score,
            passed=score >= threshold,
            severity=score_to_severity(score),
            labels=details.get("labels", []),
            detection=details,
        )

    def _score_by_age(self, age_days: int) -> tuple[float, dict[str, Any]]:
        days_threshold = self.config.get("new_address_threshold_days", 3)
        scoring_threshold = self.config.get("threshold", 50.0)
        issues: list[str] = []

        if age_days < 1:
            score = 90
            issues.append("VERY_NEW_ADDRESS")
        elif age_days < days_threshold:
            score = 70
            issues.append("NEW_ADDRESS")
        elif age_days < days_threshold * 2:
            score = 40
            issues.append("RECENTLY_CREATED_ADDRESS")
        else:
            score = 10
            issues = []

        labels = issues if score >= scoring_threshold else []
        return score, {
            "age_days": age_days,
            "threshold_days": days_threshold,
            "detected_issues": issues,
            "labels": labels,
        }


NodeRegistry.register(AddressAgeDetector)
