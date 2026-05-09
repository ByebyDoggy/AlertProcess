"""重入攻击检测器

检测 ERC20 logs 中体现出的重入攻击特征：
  - 同一交易内同一合约地址被调用超过阈值次数（调用风暴）
  - 事件日志中同一合约重复 Transfer / 重复 approval 密集序列
  - Reentrancy 经典特征：合约 A 调用合约 B，B 在 A 完成前再次调用 A
    （本 Detector 通过 logs 信号识别，深层调用树分析在 behaviors 层完成）

评分矩阵:
  - 同一合约 log 出现 ≥ extreme_count 次   → 95
  - 同一合约 log 出现 ≥ high_count 次      → 70
  - 同一合约 log 出现 ≥ medium_count 次    → 40
  - 所有合约单次出现                       → 0
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from pydantic import Field

from nodes.base import NodeRegistry, score_to_severity
from nodes.detectors.base import BaseDetector, DetectorConfigMixin, DetectorOutputMixin
from nodes.models import TransactionContext


ERC20_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


def _extract_topic0(log: dict) -> str:
    topics = log.get("topics", [])
    if not topics:
        return ""
    topic = topics[0]
    return (topic if isinstance(topic, str) else topic.hex() if isinstance(topic, bytes) else "").lower()


def _extract_address_from_topic(topic: str) -> str:
    h = topic.lstrip("0x").lower()
    if len(h) < 40:
        return "0x" + h.zfill(40)
    return "0x" + h[-40:]


def _to_int(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        if value.startswith("0x"):
            try:
                return int(value, 16)
            except ValueError:
                return 0
        try:
            return int(value)
        except (TypeError, ValueError):
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return 0
    return 0


def _extract_transfers_from_logs(logs: list[dict]) -> list[dict[str, Any]]:
    transfers: list[dict[str, Any]] = []
    for log in logs:
        topics = log.get("topics") or []
        if len(topics) < 3 or _extract_topic0(log) != ERC20_TRANSFER_TOPIC:
            continue
        from_addr = _extract_address_from_topic(topics[1])
        to_addr = _extract_address_from_topic(topics[2])
        amount = _to_int(log.get("data", 0))
        if amount <= 0:
            continue
        transfers.append({
            "from": from_addr.lower(),
            "to": to_addr.lower(),
            "value": amount,
            "token": (log.get("address") or "").lower(),
        })
    return transfers


def _extract_transfers(input: TransactionContext) -> list[dict[str, Any]]:
    transfers = input.extra.get("transfers") if isinstance(input.extra, dict) else None
    if isinstance(transfers, list) and transfers:
        return transfers
    return _extract_transfers_from_logs(input.logs or [])


class ReentrancyOutput(DetectorOutputMixin):
    """重入攻击检测器输出"""
    pass


class ReentrancyDetector(BaseDetector):
    """
    重入攻击检测器 — 通过 logs 中合约地址的出现频率识别重入模式。

    核心思路:
      重入攻击的典型特征是在单笔交易中，某一合约地址会被反复触发产生大量相同事件（如
      Transfer / Withdraw），形成事件日志中的「高频重复」信号。

    评分:
    - 某合约地址 log 数 >= extreme_count(默认20) → 95
    - 某合约地址 log 数 >= high_count(默认10)    → 70
    - 某合约地址 log 数 >= medium_count(默认5)   → 40
    - 无重复迹象                                 → 0
    """

    name: str = "reentrancy_detector"
    label: str = "重入攻击检测"

    # ── Pydantic 配置模型 (继承 DetectorConfigMixin，包含共享的 threshold) ──
    class ConfigModel(DetectorConfigMixin):
        threshold: float = Field(default=40.0, ge=0, le=100, description="passed 阈值")
        medium_count: int = Field(default=5, ge=2, description="触发 medium(40分) 的最小 log 数量")
        high_count: int = Field(default=10, ge=3, description="触发 high(70分) 的最小 log 数量")
        extreme_count: int = Field(default=20, ge=5, description="触发 extreme(95分) 的最小 log 数量")
        repeated_beneficiary_min_count: int = Field(default=2, ge=2, description="同一受益地址重复接收外流的最小次数")
        repeated_beneficiary_min_amount: int = Field(default=1, ge=1, description="统计重复受益人时的最小转账金额")
        repeated_asset_min_count: int = Field(default=2, ge=2, description="同一资产重复外流的最小次数")

    description: str = (
        "[数据需求: 仅Logs] "
        "检测重入攻击：通过 logs 中合约地址的高频重复出现识别重入模式。"
        "同一合约 ≥20 次日志给 95 分，≥10 次给 70 分，≥5 次给 40 分。"
        "是识别 DAO-style 重入、ERC777 回调重入等经典漏洞利用的基础检测器。"
    )
    icon: str = "🔄"
    color: str = "#dc2626"

    # ── Pydantic 输出模型 ──
    OutputModel: type = ReentrancyOutput

    async def process(self, input: TransactionContext) -> ReentrancyOutput:
        logs: list[dict] = input.logs

        if not logs:
            return ReentrancyOutput(score=0.0, passed=True, severity="UNKNOWN", labels=[],
                                    detection={"reason": "no logs in context"})

        medium_count = self.config.get("medium_count", 5)
        high_count = self.config.get("high_count", 10)
        extreme_count = self.config.get("extreme_count", 20)
        repeated_beneficiary_min_count = self.config.get("repeated_beneficiary_min_count", 2)
        repeated_beneficiary_min_amount = self.config.get("repeated_beneficiary_min_amount", 1)
        repeated_asset_min_count = self.config.get("repeated_asset_min_count", 2)

        address_counter: Counter[str] = Counter()
        for log in logs:
            addr = (log.get("address") or "").lower()
            if addr:
                address_counter[addr] += 1

        if not address_counter:
            return ReentrancyOutput(score=0.0, passed=True, severity="UNKNOWN", labels=[],
                                    detection={"reason": "no contract addresses in logs"})

        top_addr, top_count = address_counter.most_common(1)[0]
        issues: list[str] = []
        logs_out: list[str] = []
        score = 0.0

        if top_count >= extreme_count:
            issues.append(f"EXTREME_REENTRANCY_SIGNAL:{top_addr}:{top_count}")
            logs_out.append(f"same contract emitted {top_count} logs: {top_addr}")
            score = 95.0
        elif top_count >= high_count:
            issues.append(f"HIGH_REENTRANCY_SIGNAL:{top_addr}:{top_count}")
            logs_out.append(f"same contract emitted {top_count} logs: {top_addr}")
            score = 70.0
        elif top_count >= medium_count:
            issues.append(f"MEDIUM_REENTRANCY_SIGNAL:{top_addr}:{top_count}")
            logs_out.append(f"same contract emitted {top_count} logs: {top_addr}")
            score = 40.0

        repeated_contracts = [
            (addr, cnt) for addr, cnt in address_counter.items()
            if cnt >= medium_count
        ]
        if len(repeated_contracts) > 1 and score < 70:
            issues.append(f"MULTI_CONTRACT_REPEAT:{len(repeated_contracts)}")
            logs_out.append(f"multiple contracts emitted repeated logs: {len(repeated_contracts)}")
            score = max(score, 55.0)

        transfers = _extract_transfers(input)
        beneficiary_counter: Counter[str] = Counter()
        beneficiary_amounts: dict[str, int] = defaultdict(int)
        asset_counter: Counter[str] = Counter()
        asset_amounts: dict[str, int] = defaultdict(int)

        for transfer in transfers:
            from_addr = (transfer.get("from") or "").lower()
            to_addr = (transfer.get("to") or "").lower()
            token = (transfer.get("token") or "").lower()
            amount = _to_int(transfer.get("value", 0))
            if amount < repeated_beneficiary_min_amount or not to_addr or to_addr == ZERO_ADDRESS:
                continue
            if from_addr:
                beneficiary_counter[to_addr] += 1
                beneficiary_amounts[to_addr] += amount
                asset_counter[token] += 1
                asset_amounts[token] += amount

        repeated_beneficiaries = [
            {
                "address": addr,
                "count": cnt,
                "total_amount": beneficiary_amounts[addr],
            }
            for addr, cnt in beneficiary_counter.most_common(5)
            if cnt >= repeated_beneficiary_min_count
        ]
        repeated_assets = [
            {
                "token": token,
                "count": cnt,
                "total_amount": asset_amounts[token],
            }
            for token, cnt in asset_counter.most_common(5)
            if cnt >= repeated_asset_min_count
        ]

        if repeated_beneficiaries:
            top_beneficiary = repeated_beneficiaries[0]
            issues.append(f"REPEATED_BENEFICIARY:{top_beneficiary['address']}:{top_beneficiary['count']}")
            logs_out.append(
                f"same beneficiary received repeated transfers: {top_beneficiary['address']} x{top_beneficiary['count']}"
            )
            score = max(score, 65.0)

        if repeated_assets:
            top_asset = repeated_assets[0]
            issues.append(f"REPEATED_ASSET_RELEASE:{top_asset['token']}:{top_asset['count']}")
            logs_out.append(
                f"same asset released repeatedly: {top_asset['token']} x{top_asset['count']}"
            )
            score = max(score, 60.0)

        if repeated_beneficiaries and repeated_assets:
            issues.append("RECURSIVE_ASSET_RELEASE_PATTERN")
            logs_out.append("repeated beneficiary and repeated asset release observed together")
            score = max(score, 80.0)

        labels = issues if score >= self.config.get("threshold", 40) else []
        threshold = self.config.get("threshold", 40.0)

        return ReentrancyOutput(
            score=score, passed=score >= threshold, severity=score_to_severity(score),
            labels=labels,
            logs=logs_out,
            detection={
                "top_contract": top_addr,
                "top_count": top_count,
                "total_logs": len(logs),
                "unique_contracts": len(address_counter),
                "repeated_contracts": [
                    {"address": addr, "count": cnt}
                    for addr, cnt in address_counter.most_common(5)
                    if cnt >= medium_count
                ],
                "repeated_beneficiaries": repeated_beneficiaries,
                "repeated_assets": repeated_assets,
                "detected_issues": issues,
                "labels": labels,
            },
        )


NodeRegistry.register(ReentrancyDetector)
