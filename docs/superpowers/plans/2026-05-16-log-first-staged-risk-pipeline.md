
## Task 3: Single-transaction pipeline gates

**Files:**
- Create: `backend/pipeline/__init__.py`
- Create: `backend/pipeline/single_transaction.py`
- Test: `tests/pipeline/test_single_transaction_pipeline.py`

- [ ] **Step 1: Write failing pipeline gate tests**

Create `tests/pipeline/test_single_transaction_pipeline.py` with a local fake detection script:

```python
from datetime import UTC, datetime, timedelta

import pytest

from backend.detection import DetectionContext, DetectionResult, DetectionScript
from backend.pipeline.single_transaction import SingleTransactionRiskPipeline
from backend.providers.address_age import StaticAddressAgeProvider
from backend.providers.trace import StaticTraceProvider

TOKEN = "0xtoken"
LOSER = "0xloser"
PROFIT = "0xprofit"
ATTACKER = "0xattacker"
TX_HASH = "0xabc"
REFERENCE_TIME = datetime(2026, 5, 16, tzinfo=UTC)


class PassingScript(DetectionScript):
    id = "passing_trace_feature"
    required_inputs = ["trace_calls"]

    async def detect(self, ctx: DetectionContext) -> DetectionResult:
        return DetectionResult.from_score(
            script_id=self.id,
            score=80.0,
            threshold=40.0,
            attack_type="test_attack",
            labels=["sensitive_trace_feature"],
            entities={"attacker": ATTACKER, "profit_address": PROFIT},
            details={"trace_call_count": len(ctx.trace_calls)},
        )


class NoMatchScript(DetectionScript):
    id = "no_match_trace_feature"
    required_inputs = ["trace_calls"]

    async def detect(self, ctx: DetectionContext) -> DetectionResult:
        return DetectionResult.no_match(self.id, "no feature")


def high_loss_event() -> dict:
    return {
        "chain_id": 56,
        "tx_hash": TX_HASH,
        "from_address": ATTACKER,
        "timestamp": REFERENCE_TIME.isoformat(),
        "transfers": [
            {"token": TOKEN, "from": LOSER, "to": PROFIT, "amount_raw": "150000000"},
        ],
        "token_prices": {TOKEN: 1.0},
        "token_decimals": {TOKEN: 2},
    }


def low_loss_event() -> dict:
    event = high_loss_event()
    event["transfers"] = [{"token": TOKEN, "from": LOSER, "to": PROFIT, "amount_raw": "10"}]
    return event


@pytest.mark.asyncio
async def test_pipeline_skips_trace_when_log_loss_is_below_threshold():
    trace_provider = StaticTraceProvider({(56, TX_HASH): [{"caller": ATTACKER, "callee": PROFIT}]})
    age_provider = StaticAddressAgeProvider({ATTACKER: REFERENCE_TIME - timedelta(hours=1)})
    pipeline = SingleTransactionRiskPipeline(
        trace_provider=trace_provider,
        address_age_provider=age_provider,
        scripts=[PassingScript()],
    )

    result = await pipeline.analyze(low_loss_event())

    assert result.trace_fetched is False
    assert trace_provider.calls == []
    assert age_provider.calls == []
    assert result.alert_candidate is None


@pytest.mark.asyncio
async def test_pipeline_fetches_trace_after_large_log_loss():
    trace_provider = StaticTraceProvider({(56, TX_HASH): []})
    pipeline = SingleTransactionRiskPipeline(
        trace_provider=trace_provider,
        address_age_provider=StaticAddressAgeProvider({}),
        scripts=[NoMatchScript()],
    )

    result = await pipeline.analyze(high_loss_event())

    assert result.trace_fetched is True
    assert trace_provider.calls == [(56, TX_HASH)]
    assert result.top_loss_address == LOSER
    assert result.top_loss_usd == 1_500_000.0


@pytest.mark.asyncio
async def test_pipeline_skips_address_age_when_no_sensitive_feature_passes():
    trace_provider = StaticTraceProvider({(56, TX_HASH): [{"caller": ATTACKER, "callee": PROFIT}]})
    age_provider = StaticAddressAgeProvider({ATTACKER: REFERENCE_TIME - timedelta(hours=1)})
    pipeline = SingleTransactionRiskPipeline(
        trace_provider=trace_provider,
        address_age_provider=age_provider,
        scripts=[NoMatchScript()],
    )

    result = await pipeline.analyze(high_loss_event())

    assert result.passed_detection_results == []
    assert age_provider.calls == []
    assert result.alert_candidate is None


@pytest.mark.asyncio
async def test_pipeline_does_not_alert_when_sensitive_addresses_are_old():
    trace_provider = StaticTraceProvider({(56, TX_HASH): [{"caller": ATTACKER, "callee": PROFIT}]})
    age_provider = StaticAddressAgeProvider(
        {
            ATTACKER: REFERENCE_TIME - timedelta(days=10),
            PROFIT: REFERENCE_TIME - timedelta(days=9),
        }
    )
    pipeline = SingleTransactionRiskPipeline(
        trace_provider=trace_provider,
        address_age_provider=age_provider,
        scripts=[PassingScript()],
    )

    result = await pipeline.analyze(high_loss_event())

    assert [item.script_id for item in result.passed_detection_results] == ["passing_trace_feature"]
    assert result.new_addresses == []
    assert result.alert_candidate is None


@pytest.mark.asyncio
async def test_pipeline_alerts_when_sensitive_feature_has_new_key_address():
    trace_provider = StaticTraceProvider({(56, TX_HASH): [{"caller": ATTACKER, "callee": PROFIT}]})
    age_provider = StaticAddressAgeProvider(
        {
            ATTACKER: REFERENCE_TIME - timedelta(hours=1),
            PROFIT: REFERENCE_TIME - timedelta(days=9),
        }
    )
    pipeline = SingleTransactionRiskPipeline(
        trace_provider=trace_provider,
        address_age_provider=age_provider,
        scripts=[PassingScript()],
    )

    result = await pipeline.analyze(high_loss_event())

    assert [age.address for age in result.new_addresses] == [ATTACKER]
    assert result.alert_candidate is not None
    assert result.alert_candidate["tx_hash"] == TX_HASH
    assert result.alert_candidate["top_loss_address"] == LOSER
    assert result.alert_candidate["passed_scripts"] == ["passing_trace_feature"]
    assert result.alert_candidate["new_addresses"] == [ATTACKER]
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
AlertProcessor/.venv/Scripts/python.exe -m pytest AlertProcessor/tests/pipeline/test_single_transaction_pipeline.py -v
```

Expected: import failure because `backend.pipeline.single_transaction` does not exist.

- [ ] **Step 3: Implement pipeline module**

Create `backend/pipeline/single_transaction.py`:

```python
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
        if isinstance(value, list | tuple | set):
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
```

Create `backend/pipeline/__init__.py`:

```python
from .single_transaction import SingleTransactionRiskConfig, SingleTransactionRiskPipeline, SingleTransactionRiskResult

__all__ = ["SingleTransactionRiskConfig", "SingleTransactionRiskPipeline", "SingleTransactionRiskResult"]
```

- [ ] **Step 4: Run pipeline tests and verify GREEN**

Run:

```bash
AlertProcessor/.venv/Scripts/python.exe -m pytest AlertProcessor/tests/pipeline/test_single_transaction_pipeline.py -v
```

Expected: all tests pass.

## Task 4: Integration with existing LP drain script

**Files:**
- Test: `tests/pipeline/test_single_transaction_pipeline.py`

- [ ] **Step 1: Add failing integration test using `TokenContractActiveLPDrainScript`**

Append this test to `tests/pipeline/test_single_transaction_pipeline.py`:

```python
from backend.strategies.token_contract_active_lp_drain import TokenContractActiveLPDrainScript


@pytest.mark.asyncio
async def test_pipeline_runs_existing_lp_drain_strategy_inside_sensitive_stage():
    lp = "0xlp"
    token_contract = "0xmalicioustoken"
    usdt = "0x55d398326f99059ff775485246999027b3197955"
    event = {
        "chain_id": 56,
        "tx_hash": TX_HASH,
        "from_address": ATTACKER,
        "timestamp": REFERENCE_TIME.isoformat(),
        "transfers": [
            {"token": usdt, "from": lp, "to": PROFIT, "amount_raw": "1500000000000000000000000"},
            {"token": token_contract, "from": lp, "to": token_contract, "amount_raw": "1"},
            {"token": usdt, "from": token_contract, "to": PROFIT, "amount_raw": "10000000000000000000000"},
        ],
        "token_prices": {usdt: 1.0, token_contract: 0.0},
        "token_decimals": {usdt: 18, token_contract: 18},
        "address_labels": {lp: "Pancake LP"},
    }
    trace_provider = StaticTraceProvider(
        {
            (56, TX_HASH): [
                {"caller": token_contract, "callee": lp, "selector": "0x022c0d9f"},
            ]
        }
    )
    age_provider = StaticAddressAgeProvider({ATTACKER: REFERENCE_TIME - timedelta(hours=1)})
    pipeline = SingleTransactionRiskPipeline(
        trace_provider=trace_provider,
        address_age_provider=age_provider,
        scripts=[TokenContractActiveLPDrainScript()],
    )

    result = await pipeline.analyze(event)

    assert [item.script_id for item in result.passed_detection_results] == ["token_contract_active_lp_drain"]
    assert result.alert_candidate is not None
    assert result.alert_candidate["passed_scripts"] == ["token_contract_active_lp_drain"]
```

- [ ] **Step 2: Run the integration test and verify RED if needed**

Run:

```bash
AlertProcessor/.venv/Scripts/python.exe -m pytest AlertProcessor/tests/pipeline/test_single_transaction_pipeline.py::test_pipeline_runs_existing_lp_drain_strategy_inside_sensitive_stage -v
```

Expected: if it fails, the failure should point to missing metadata/context wiring, not import errors.

- [ ] **Step 3: Adjust pipeline context wiring only if the test fails**

If needed, update `SingleTransactionRiskPipeline.analyze()` so `metadata.top_loss_address`, `metadata.top_profit_address`, `balance_changes`, `trace_calls`, and token price/decimal fields are preserved exactly as expected by existing scripts.

- [ ] **Step 4: Run pipeline tests and verify GREEN**

Run:

```bash
AlertProcessor/.venv/Scripts/python.exe -m pytest AlertProcessor/tests/pipeline/test_single_transaction_pipeline.py -v
```

Expected: all pipeline tests pass.

## Task 5: Documentation and full verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README**

Add a short section to `README.md` explaining:

```markdown
## Log-first staged risk pipeline

The detection platform uses a staged single-transaction pipeline for high-confidence alerts:

1. Parse transfer logs and compute net USD balance changes by address.
2. Fetch transaction trace only when an address loses more than the configured USD threshold.
3. Run script-first trace detectors through `DetectionRuntime`.
4. Query key address creation/first-seen time only when a sensitive detector passes.
5. Produce an alert candidate only when suspicious behavior and a fresh key address are both present.

Trace and address-age lookups are provider interfaces. Unit tests use static offline providers; live Moralis/RPC/Blocksec adapters should be added behind the same interfaces.
```

- [ ] **Step 2: Run targeted test suite**

Run:

```bash
AlertProcessor/.venv/Scripts/python.exe -m pytest AlertProcessor/tests/ingestion AlertProcessor/tests/providers AlertProcessor/tests/pipeline -v
```

Expected: all new tests pass.

- [ ] **Step 3: Run broader regression suite**

Run:

```bash
AlertProcessor/.venv/Scripts/python.exe -m pytest AlertProcessor/tests -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit implementation**

Run:

```bash
git -C AlertProcessor status --short
git -C AlertProcessor add backend/ingestion backend/providers backend/pipeline tests/ingestion tests/providers tests/pipeline README.md docs/superpowers/specs/2026-05-16-log-first-staged-risk-pipeline-design.md docs/superpowers/plans/2026-05-16-log-first-staged-risk-pipeline.md
git -C AlertProcessor commit -m "feat: add log-first staged risk pipeline"
```

Expected: commit succeeds after tests pass.
