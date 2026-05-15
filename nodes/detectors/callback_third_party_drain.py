from __future__ import annotations

from collections import defaultdict
from typing import Any

from pydantic import Field

from nodes.base import NodeRegistry, score_to_severity
from nodes.detectors.base import BaseDetector, DetectorConfigMixin, DetectorOutputMixin
from nodes.models import TransactionContext


class CallbackThirdPartyDrainOutput(DetectorOutputMixin):
    pass


def _addr(value: Any) -> str:
    return str(value or "").lower()


def _amount(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value, 16) if value.startswith("0x") else int(value)
        except ValueError:
            return 0
    return 0


def _token_value_usd(token: str, raw_amount: int, prices: dict[str, Any], decimals: dict[str, Any]) -> float:
    token_key = _addr(token)
    price = float(prices.get(token_key, prices.get(token, 0.0)) or 0.0)
    token_decimals = int(decimals.get(token_key, decimals.get(token, 18)) or 18)
    return raw_amount / (10 ** token_decimals) * price


def _callback_loop_count(trace_calls: list[dict[str, Any]]) -> int:
    names = [str(call.get("name") or call.get("method") or "").lower() for call in trace_calls]
    if not names:
        return 0

    pattern = ["lock", "locked", "withdraw", "transfer", "pay", "paycallback", "transferfrom"]
    count = 0
    index = 0
    while index < len(names):
        matched = True
        for offset, expected in enumerate(pattern):
            if index + offset >= len(names) or names[index + offset] != expected:
                matched = False
                break
        if matched:
            count += 1
            index += len(pattern)
        else:
            index += 1
    return count


class CallbackThirdPartyDrainDetector(BaseDetector):
    name: str = "callback_third_party_drain"
    label: str = "第三方回调资金抽离检测"
    description: str = "检测第三方 transferFrom 到协议后由协议中转给获利地址的 callback drain 模式"
    icon: str = ""
    color: str = "#dc2626"

    class ConfigModel(DetectorConfigMixin):
        threshold: float = Field(default=40.0, ge=0, le=100, description="0-100，评分达到此值视为 passed")
        min_repeat_count: int = Field(default=3, ge=1, description="触发检测的最小第三方 transferFrom 次数")
        critical_repeat_count: int = Field(default=10, ge=1, description="判定严重风险的重复次数阈值")
        min_usd_value: float = Field(default=100000.0, ge=0, description="触发检测的最小 USD 金额")
        critical_usd_value: float = Field(default=1000000.0, ge=0, description="判定 CRITICAL 的 USD 金额")
        min_match_ratio: float = Field(default=0.8, ge=0, le=1, description="第三方扣款与获利转账的最小匹配比例")

    OutputModel: type = CallbackThirdPartyDrainOutput

    async def process(self, tx_context: TransactionContext) -> CallbackThirdPartyDrainOutput:
        extra = tx_context.extra or {}
        sender = _addr(tx_context.from_address)
        top_profit = _addr(extra.get("top_profit_address"))
        top_loss = _addr(extra.get("top_loss_address"))
        profit_addresses = {addr for addr in {sender, top_profit} if addr}
        prices = {_addr(k): v for k, v in (extra.get("token_prices") or {}).items()}
        decimals = {_addr(k): v for k, v in (extra.get("token_decimals") or {}).items()}

        grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
        for call in extra.get("erc20_calls") or []:
            if str(call.get("method", "")).lower() != "transferfrom":
                continue
            victim = _addr(call.get("from"))
            if not victim or victim in profit_addresses:
                continue
            token = _addr(call.get("token"))
            protocol = _addr(call.get("to"))
            key = (token, victim, protocol)
            item = grouped.setdefault(key, {"amount": 0, "count": 0, "callers": set()})
            item["amount"] += _amount(call.get("amount_raw", call.get("amount", call.get("value"))))
            item["count"] += 1
            if call.get("caller"):
                item["callers"].add(_addr(call.get("caller")))

        if not grouped:
            return CallbackThirdPartyDrainOutput(
                score=0.0,
                passed=False,
                severity="UNKNOWN",
                labels=[],
                detection={"reason": "no matching third-party callback drain"},
                logs=["未检测到第三方 transferFrom 扣款"],
            )

        profit_in: dict[tuple[str, str], int] = defaultdict(int)
        for transfer in extra.get("transfers") or []:
            to_addr = _addr(transfer.get("to"))
            if to_addr not in profit_addresses:
                continue
            token = _addr(transfer.get("token"))
            from_addr = _addr(transfer.get("from"))
            profit_in[(token, from_addr)] += _amount(transfer.get("amount_raw", transfer.get("amount", transfer.get("value"))))

        callback_count = _callback_loop_count(extra.get("trace_calls") or [])
        best: dict[str, Any] | None = None
        best_score = 0.0

        for (token, victim, protocol), data in grouped.items():
            drained = int(data["amount"])
            matched = profit_in.get((token, protocol), 0)
            if drained <= 0 or matched <= 0:
                continue
            ratio = min(matched, drained) / drained
            usd_value = _token_value_usd(token, drained, prices, decimals)
            repeat_count = int(data["count"])
            if ratio < self.config.get("min_match_ratio", 0.8):
                continue
            if repeat_count < self.config.get("min_repeat_count", 3) and victim != top_loss:
                continue
            if usd_value < self.config.get("min_usd_value", 100000.0):
                continue

            score = 35.0
            if usd_value >= self.config.get("critical_usd_value", 1000000.0):
                score += 25.0
            if repeat_count >= self.config.get("critical_repeat_count", 10):
                score += 20.0
            if top_loss == victim:
                score += 10.0
            if sender and top_profit == sender:
                score += 10.0
            if callback_count >= self.config.get("critical_repeat_count", 10):
                score += 10.0
            score = min(score, 100.0)

            if score > best_score:
                best_score = score
                best = {
                    "token": token,
                    "victim": victim,
                    "profit_address": top_profit or sender,
                    "protocol": protocol,
                    "repeat_count": repeat_count,
                    "amount_raw": str(drained),
                    "matched_profit_raw": str(matched),
                    "matched_ratio": round(ratio, 4),
                    "usd_value": round(usd_value, 2),
                    "callback_loop_count": callback_count,
                    "callers": sorted(data["callers"]),
                }

        if not best:
            return CallbackThirdPartyDrainOutput(
                score=0.0,
                passed=False,
                severity="UNKNOWN",
                labels=[],
                detection={"reason": "no matching third-party callback drain"},
                logs=["第三方扣款未与获利地址入账形成高价值匹配闭环"],
            )

        labels = [
            "third_party_transfer_from",
            "protocol_pass_through",
            "callback_drain",
            "access_control_anomaly",
        ]
        severity = score_to_severity(best_score)
        return CallbackThirdPartyDrainOutput(
            score=best_score,
            passed=True,
            severity=severity,
            labels=labels,
            detection={
                "reason": "matched third-party callback drain",
                "evidence": best,
            },
            logs=[
                f"第三方 transferFrom 重复 {best['repeat_count']} 次",
                f"协议中转匹配比例 {best['matched_ratio']:.2f}",
                f"估算价值 ${best['usd_value']:,.2f}",
                f"callback loop 次数 {best['callback_loop_count']}",
            ],
        )


NodeRegistry.register(CallbackThirdPartyDrainDetector)
