from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from backend.detection import DetectionContext, DetectionResult, DetectionRuntime, DetectionScript
from backend.ingestion.balance_changes import BalanceChangeCalculator, BalanceChangeSummary
from backend.providers.address_age import AddressAge, AddressAgeProvider
from backend.providers.trace import TraceProvider


@dataclass(frozen=True)
class SingleTransactionRiskConfig:
    min_net_outflow_usd: float = 1_000_000.0
    new_address_window: timedelta = timedelta(days=2)


@dataclass
class SingleTransactionRiskResult:
    tx_hash: str
    chain_id: int
    balance_summary: BalanceChangeSummary
    trace_fetched: bool = False
    runtime_errors: list[dict[str, Any]] = field(default_factory=list)
    passed_detection_results: list[DetectionResult] = field(default_factory=list)
    checked_addresses: list[AddressAge] = field(default_factory=list)
    new_addresses: list[AddressAge] = field(default_factory=list)
    alert_candidate: dict[str, Any] | None = None

    @property
    def top_loss_address(self) -> str:
        return self.balance_summary.top_loss_address

    @property
    def top_loss_usd(self) -> float:
        return self.balance_summary.top_loss_usd

    @property
    def top_profit_address(self) -> str:
        return self.balance_summary.top_profit_address

    @property
    def top_profit_usd(self) -> float:
        return self.balance_summary.top_profit_usd


class SingleTransactionRiskPipeline:
    def __init__(
        self,
        trace_provider: TraceProvider,
        address_age_provider: AddressAgeProvider,
        scripts: list[DetectionScript],
        config: SingleTransactionRiskConfig | None = None,
    ) -> None:
        self.trace_provider = trace_provider
        self.address_age_provider = address_age_provider
        self.scripts = scripts
        self.config = config or SingleTransactionRiskConfig()
        self.balance_calculator = BalanceChangeCalculator()

    async def analyze(self, event: dict[str, Any]) -> SingleTransactionRiskResult:
        chain_id = int(event.get("chain_id") or 0)
        tx_hash = str(event.get("tx_hash") or "").lower()
        transfers = list(event.get("transfers") or [])
        balance_summary = self.balance_calculator.calculate(
            transfers=transfers,
            token_prices=event.get("token_prices") or {},
            token_decimals=event.get("token_decimals") or {},
        )
        result = SingleTransactionRiskResult(tx_hash=tx_hash, chain_id=chain_id, balance_summary=balance_summary)

        if balance_summary.top_loss_usd < self.config.min_net_outflow_usd:
            return result

        trace_calls = await self.trace_provider.get_trace_calls(chain_id, tx_hash)
        result.trace_fetched = True

        ctx = DetectionContext.from_dict(
            {
                **event,
                "tx_hash": tx_hash,
                "chain_id": chain_id,
                "transfers": transfers,
                "trace_calls": trace_calls,
                "balance_changes": balance_summary.to_context_balance_changes(),
                "metadata": {
                    **dict(event.get("metadata") or {}),
                    "top_loss_address": balance_summary.top_loss_address,
                    "top_loss_usd": balance_summary.top_loss_usd,
                    "top_profit_address": balance_summary.top_profit_address,
                    "top_profit_usd": balance_summary.top_profit_usd,
                },
            }
        )
        runtime_result = await DetectionRuntime(self.scripts).run(ctx)
        result.runtime_errors = list(runtime_result.errors)
        result.passed_detection_results = [item for item in runtime_result.results if item.passed]
        if not result.passed_detection_results:
            return result

        reference_time = self._reference_time(event)
        addresses = self._candidate_addresses(event, result.passed_detection_results, balance_summary)
        for address in addresses:
            age = await self.address_age_provider.get_address_age(chain_id, address, reference_time)
            result.checked_addresses.append(age)
            if age.is_new:
                result.new_addresses.append(age)

        if result.new_addresses:
            result.alert_candidate = self._build_alert_candidate(result)
        return result

    def _reference_time(self, event: dict[str, Any]) -> datetime:
        timestamp = event.get("timestamp")
        if isinstance(timestamp, datetime):
            return timestamp
        if isinstance(timestamp, str) and timestamp:
            return datetime.fromisoformat(timestamp)
        return datetime.now().astimezone()

    def _candidate_addresses(
        self,
        event: dict[str, Any],
        passed_results: list[DetectionResult],
        balance_summary: BalanceChangeSummary,
    ) -> list[str]:
        addresses = [
            event.get("from_address"),
            event.get("to_address"),
            balance_summary.top_profit_address,
            balance_summary.top_loss_address,
        ]
        for detection in passed_results:
            addresses.extend(self._flatten_entity_addresses(detection.entities))
        seen: set[str] = set()
        unique: list[str] = []
        for address in addresses:
            normalized = str(address or "").lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique.append(normalized)
        return unique

    def _flatten_entity_addresses(self, value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            addresses: list[str] = []
            for item in value.values():
                addresses.extend(self._flatten_entity_addresses(item))
            return addresses
        if isinstance(value, (list, tuple, set)):
            addresses = []
            for item in value:
                addresses.extend(self._flatten_entity_addresses(item))
            return addresses
        return []

    def _build_alert_candidate(self, result: SingleTransactionRiskResult) -> dict[str, Any]:
        max_result = max(result.passed_detection_results, key=lambda item: item.score)
        return {
            "tx_hash": result.tx_hash,
            "chain_id": result.chain_id,
            "top_loss_address": result.top_loss_address,
            "top_loss_usd": result.top_loss_usd,
            "top_profit_address": result.top_profit_address,
            "top_profit_usd": result.top_profit_usd,
            "passed_scripts": [item.script_id for item in result.passed_detection_results],
            "max_score": max_result.score,
            "severity": max_result.severity,
            "new_addresses": [age.address for age in result.new_addresses],
            "new_address_details": [
                {
                    "address": age.address,
                    "created_at": age.created_at.isoformat() if age.created_at else None,
                    "age_seconds": age.age_seconds,
                }
                for age in result.new_addresses
            ],
        }
