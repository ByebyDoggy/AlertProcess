# Ekubo Callback Drain Detector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable `callback_third_party_drain` detector and offline Ekubo replay tests that catch the 85-cycle WBTC drain without network access.

**Architecture:** Implement one focused detector under `nodes/detectors/` that consumes normalized `TransactionContext.extra` data: `erc20_calls`, `transfers`, profit/loss addresses, token prices, token decimals, and optional `trace_calls`. Keep replay data in a small Python fixture that stores only the extracted signals needed by the detector, then test both direct detector behavior and rule-chain executor behavior.

**Tech Stack:** Python 3.14, Pydantic, pytest, pytest-asyncio, existing AlertProcessor `BaseDetector`, `NodeRegistry`, `ChainParser`, and `ChainExecutor`.

---

## File Map

- Create `tests/fixtures/ekubo_callback_drain.py`: offline Ekubo fixture plus a normal router/swap fixture.
- Create `tests/nodes/test_detectors/test_callback_third_party_drain.py`: TDD unit tests for registration, defaults, Ekubo CRITICAL hit, and normal router non-hit.
- Create `nodes/detectors/callback_third_party_drain.py`: detector implementation.
- Modify `nodes/detectors/__init__.py`: export `CallbackThirdPartyDrainDetector`.
- Create `tests/engine/test_ekubo_callback_drain_replay.py`: rule-chain replay test using the offline fixture.

## Task 1: Add failing detector unit tests and fixture

**Files:**
- Create: `tests/fixtures/ekubo_callback_drain.py`
- Create: `tests/nodes/test_detectors/test_callback_third_party_drain.py`

- [ ] **Step 1: Create the offline fixture**

Create `tests/fixtures/ekubo_callback_drain.py`:

```python
from __future__ import annotations

ATTACK_TX_HASH = "0x770bc9a1f7c32cb63a5002b9ceb5c7994cd3af0fc6b2309cb32d3c46f629daa0"
ATTACKER = "0xa911ff351b143634dbc5af3e204ea074583a83e3"
ENTRY_CONTRACT = "0x61b0dad9628d3e644eb560a5c9b0f960430e3a75"
HELPER = "0x8ccb1ffd5c2aa6bd926473425dea4c8c15de60fd"
EKUBO_CORE = "0xe0e0e08a6a4b9dc7bd67bcb7aade5cf48157d444"
VICTIM = "0x765decf4fa157756e850c1079f60801b9219edd1"
WBTC = "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599"
WBTC_DECIMALS = 8
WBTC_PRICE = 81023.323
RAW_AMOUNT_PER_LOOP = 20_000_000
REPEAT_COUNT = 85
TOTAL_RAW_AMOUNT = RAW_AMOUNT_PER_LOOP * REPEAT_COUNT


def _repeat_calls() -> list[dict]:
    calls: list[dict] = []
    for _ in range(REPEAT_COUNT):
        calls.extend([
            {"method": "lock", "caller": HELPER, "callee": EKUBO_CORE},
            {"method": "locked", "caller": EKUBO_CORE, "callee": HELPER, "amount_raw": RAW_AMOUNT_PER_LOOP},
            {
                "method": "withdraw",
                "caller": HELPER,
                "callee": EKUBO_CORE,
                "token": WBTC,
                "to": ATTACKER,
                "amount_raw": RAW_AMOUNT_PER_LOOP,
            },
            {
                "method": "transfer",
                "caller": EKUBO_CORE,
                "token": WBTC,
                "from": EKUBO_CORE,
                "to": ATTACKER,
                "amount_raw": RAW_AMOUNT_PER_LOOP,
            },
            {"method": "pay", "caller": HELPER, "callee": EKUBO_CORE, "token": WBTC},
            {"method": "payCallback", "caller": EKUBO_CORE, "callee": HELPER, "token": WBTC},
            {
                "method": "transferFrom",
                "caller": HELPER,
                "token": WBTC,
                "from": VICTIM,
                "to": EKUBO_CORE,
                "amount_raw": RAW_AMOUNT_PER_LOOP,
            },
        ])
    return calls


def ekubo_attack_context() -> dict:
    return {
        "tx_hash": ATTACK_TX_HASH,
        "chain_id": 1,
        "block_number": 25030409,
        "from_address": ATTACKER,
        "to_address": ENTRY_CONTRACT,
        "value": 0,
        "gas_used": 1_735_786,
        "input_data": "0x718a549d",
        "extra": {
            "top_profit_address": ATTACKER,
            "top_loss_address": VICTIM,
            "token_prices": {WBTC: WBTC_PRICE},
            "token_decimals": {WBTC: WBTC_DECIMALS},
            "erc20_calls": _repeat_calls(),
            "transfers": [
                {"from": VICTIM, "to": EKUBO_CORE, "token": WBTC, "value": TOTAL_RAW_AMOUNT},
                {"from": EKUBO_CORE, "to": ATTACKER, "token": WBTC, "value": TOTAL_RAW_AMOUNT},
            ],
            "expected_loss_usd": 1_377_396.49,
        },
    }


def normal_router_context() -> dict:
    user = "0x1111111111111111111111111111111111111111"
    router = "0x2222222222222222222222222222222222222222"
    recipient = "0x3333333333333333333333333333333333333333"
    token_in = WBTC
    token_out = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
    return {
        "tx_hash": "0xnormal",
        "chain_id": 1,
        "from_address": user,
        "to_address": router,
        "value": 0,
        "extra": {
            "top_profit_address": recipient,
            "top_loss_address": user,
            "token_prices": {token_in: WBTC_PRICE, token_out: 3000.0},
            "token_decimals": {token_in: WBTC_DECIMALS, token_out: 18},
            "erc20_calls": [
                {
                    "method": "transferFrom",
                    "caller": router,
                    "token": token_in,
                    "from": user,
                    "to": router,
                    "amount_raw": 10_000_000,
                }
            ],
            "transfers": [
                {"from": user, "to": router, "token": token_in, "value": 10_000_000},
                {"from": router, "to": recipient, "token": token_out, "value": 2_700_000_000_000_000_000},
            ],
        },
    }
```

- [ ] **Step 2: Create failing unit tests**

Create `tests/nodes/test_detectors/test_callback_third_party_drain.py`:

```python
from __future__ import annotations

import pytest

from nodes.base import NodeCategory, NodeRegistry
from nodes.detectors.base import DetectorInputMixin
from nodes.detectors.callback_third_party_drain import CallbackThirdPartyDrainDetector
from tests.fixtures.ekubo_callback_drain import (
    ATTACKER,
    EKUBO_CORE,
    TOTAL_RAW_AMOUNT,
    VICTIM,
    WBTC,
    ekubo_attack_context,
    normal_router_context,
)


class TestCallbackThirdPartyDrainBasics:
    def test_category(self):
        assert CallbackThirdPartyDrainDetector.category == NodeCategory.DETECTION

    def test_name(self):
        assert CallbackThirdPartyDrainDetector.name == "callback_third_party_drain"

    def test_registered(self):
        assert NodeRegistry.get("callback_third_party_drain") is CallbackThirdPartyDrainDetector

    def test_default_config(self):
        cfg = CallbackThirdPartyDrainDetector.get_default_config()
        assert cfg["min_repeat_count"] == 3
        assert cfg["critical_repeat_count"] == 10
        assert cfg["min_usd_value"] == 100000.0
        assert cfg["critical_usd_value"] == 1000000.0
        assert cfg["min_match_ratio"] == 0.8


class TestCallbackThirdPartyDrainDetection:
    @pytest.mark.asyncio
    async def test_ekubo_fixture_detects_critical_third_party_callback_drain(self):
        detector = CallbackThirdPartyDrainDetector(node_id="d1")
        tx = DetectorInputMixin(**ekubo_attack_context())

        output = await detector.process(tx)

        assert output.passed is True
        assert output.score == 100.0
        assert output.severity == "CRITICAL"
        assert "third_party_transfer_from" in output.labels
        assert "protocol_pass_through" in output.labels
        assert "callback_drain" in output.labels
        assert "access_control_anomaly" in output.labels

        evidence = output.detection["evidence"]
        assert evidence["victim"] == VICTIM
        assert evidence["profit_address"] == ATTACKER
        assert evidence["protocol"] == EKUBO_CORE
        assert evidence["token"] == WBTC
        assert evidence["repeat_count"] == 85
        assert evidence["amount_raw"] == TOTAL_RAW_AMOUNT
        assert evidence["matched_ratio"] == 1.0
        assert evidence["usd_value"] > 1_000_000
        assert evidence["callback_loop_count"] >= 80

    @pytest.mark.asyncio
    async def test_normal_router_swap_does_not_trigger(self):
        detector = CallbackThirdPartyDrainDetector(node_id="d1")
        tx = DetectorInputMixin(**normal_router_context())

        output = await detector.process(tx)

        assert output.passed is False
        assert output.score < detector.config["threshold"]
        assert output.severity in {"UNKNOWN", "LOW"}
        assert output.detection["reason"] == "no third-party callback drain pattern found"
```

- [ ] **Step 3: Run tests to verify RED**

Run:

```bash
AlertProcessor/.venv/Scripts/python.exe -m pytest AlertProcessor/tests/nodes/test_detectors/test_callback_third_party_drain.py -q
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'nodes.detectors.callback_third_party_drain'`.

## Task 2: Implement minimal detector

**Files:**
- Create: `nodes/detectors/callback_third_party_drain.py`
- Modify: `nodes/detectors/__init__.py`
- Test: `tests/nodes/test_detectors/test_callback_third_party_drain.py`

- [ ] **Step 1: Create detector implementation**

Create `nodes/detectors/callback_third_party_drain.py`:

```python
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


def _token(value: Any) -> str:
    return str(value or "").lower()


def _amount(value: Any) -> int:
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
        cleaned = value.replace(",", "")
        try:
            return int(cleaned)
        except ValueError:
            try:
                return int(float(cleaned))
            except ValueError:
                return 0
    return 0


def _method(call: dict[str, Any]) -> str:
    return str(call.get("method") or call.get("name") or "")


@NodeRegistry.register
class CallbackThirdPartyDrainDetector(BaseDetector):
    name: str = "callback_third_party_drain"
    label: str = "第三方回调资金抽离检测"
    description: str = "检测 transferFrom(third-party -> protocol) 与 protocol -> profit address 的 callback drain 模式"
    icon: str = ""
    color: str = "#dc2626"

    class ConfigModel(DetectorConfigMixin):
        min_repeat_count: int = Field(default=3, ge=1, description="触发检测的最小第三方 transferFrom 次数")
        critical_repeat_count: int = Field(default=10, ge=1, description="判定严重风险的重复次数阈值")
        min_usd_value: float = Field(default=100000.0, ge=0, description="触发检测的最小 USD 金额")
        critical_usd_value: float = Field(default=1000000.0, ge=0, description="判定 CRITICAL 的 USD 金额")
        min_match_ratio: float = Field(default=0.8, ge=0, le=1, description="第三方扣款与获利转账的最小匹配比例")

    OutputModel: type = CallbackThirdPartyDrainOutput

    async def process(self, tx_context: TransactionContext) -> CallbackThirdPartyDrainOutput:
        sender = _addr(tx_context.from_address)
        top_profit = _addr(tx_context.extra.get("top_profit_address")) or sender
        top_loss = _addr(tx_context.extra.get("top_loss_address"))
        profit_addresses = {sender, top_profit} - {""}

        erc20_calls = tx_context.extra.get("erc20_calls") or []
        transfers = tx_context.extra.get("transfers") or []
        token_prices = {_token(k): float(v) for k, v in (tx_context.extra.get("token_prices") or {}).items()}
        token_decimals = {_token(k): int(v) for k, v in (tx_context.extra.get("token_decimals") or {}).items()}

        third_party = defaultdict(lambda: {"amount": 0, "count": 0, "callers": set()})
        for call in erc20_calls:
            if _method(call) != "transferFrom":
                continue
            victim = _addr(call.get("from"))
            protocol = _addr(call.get("to"))
            token = _token(call.get("token"))
            amount = _amount(call.get("amount_raw", call.get("value", call.get("amount", 0))))
            if amount <= 0 or not victim or not protocol or not token:
                continue
            if victim in profit_addresses:
                continue
            key = (token, victim, protocol)
            third_party[key]["amount"] += amount
            third_party[key]["count"] += 1
            third_party[key]["callers"].add(_addr(call.get("caller")))

        profit_in = defaultdict(lambda: {"amount": 0, "count": 0})
        for transfer in transfers:
            token = _token(transfer.get("token"))
            to_addr = _addr(transfer.get("to"))
            amount = _amount(transfer.get("value", transfer.get("amount_raw", transfer.get("amount", 0))))
            if amount <= 0 or not token or to_addr not in profit_addresses:
                continue
            profit_in[token]["amount"] += amount
            profit_in[token]["count"] += 1

        best = None
        for (token, victim, protocol), drain in third_party.items():
            drained_amount = int(drain["amount"])
            profit_amount = int(profit_in[token]["amount"])
            if drained_amount <= 0 or profit_amount <= 0:
                continue
            matched_ratio = min(drained_amount, profit_amount) / max(drained_amount, profit_amount)
            decimals = token_decimals.get(token, 18)
            usd_value = drained_amount / (10 ** decimals) * token_prices.get(token, 0.0)
            repeat_count = int(drain["count"])
            if repeat_count < self.config["min_repeat_count"]:
                continue
            if usd_value < self.config["min_usd_value"]:
                continue
            if matched_ratio < self.config["min_match_ratio"]:
                continue
            candidate = {
                "token": token,
                "victim": victim,
                "protocol": protocol,
                "profit_address": top_profit or sender,
                "repeat_count": repeat_count,
                "amount_raw": drained_amount,
                "profit_amount_raw": profit_amount,
                "matched_ratio": round(matched_ratio, 6),
                "usd_value": usd_value,
                "callback_loop_count": self._count_callback_loops(erc20_calls),
                "top_loss_address": top_loss,
                "callers": sorted(drain["callers"]),
            }
            if best is None or candidate["usd_value"] > best["usd_value"]:
                best = candidate

        if best is None:
            return CallbackThirdPartyDrainOutput(
                score=0.0,
                passed=False,
                severity="UNKNOWN",
                labels=[],
                detection={"reason": "no third-party callback drain pattern found"},
                logs=["No matching third-party callback drain candidate found"],
            )

        score = self._score(best, top_loss)
        labels = [
            "third_party_transfer_from",
            "protocol_pass_through",
            "access_control_anomaly",
        ]
        if best["callback_loop_count"] >= self.config["min_repeat_count"]:
            labels.append("callback_drain")

        return CallbackThirdPartyDrainOutput(
            score=score,
            passed=score >= self.config["threshold"],
            severity=score_to_severity(score),
            labels=labels,
            detection={"evidence": best},
            logs=[
                f"Detected third-party transferFrom drain: victim={best['victim']} token={best['token']} "
                f"repeat_count={best['repeat_count']} usd_value={best['usd_value']:.2f}"
            ],
        )

    def _score(self, evidence: dict[str, Any], top_loss: str) -> float:
        score = 35.0
        if evidence["usd_value"] >= self.config["critical_usd_value"]:
            score += 25.0
        if evidence["repeat_count"] >= self.config["critical_repeat_count"]:
            score += 20.0
        if evidence["callback_loop_count"] >= self.config["critical_repeat_count"]:
            score += 15.0
        if top_loss and evidence["victim"] == top_loss:
            score += 10.0
        if evidence["matched_ratio"] >= 0.95:
            score += 10.0
        return min(score, 100.0)

    @staticmethod
    def _count_callback_loops(calls: list[dict[str, Any]]) -> int:
        names = [_method(call) for call in calls]
        required = {"lock", "locked", "withdraw", "pay", "payCallback", "transferFrom"}
        if not required.issubset(set(names)):
            return 0
        return min(names.count(name) for name in required)
```

- [ ] **Step 2: Export the detector**

Modify `nodes/detectors/__init__.py`:

```python
from nodes.detectors.callback_third_party_drain import CallbackThirdPartyDrainDetector
```

Add to `__all__`:

```python
"CallbackThirdPartyDrainDetector",
```

- [ ] **Step 3: Run unit tests to verify GREEN**

Run:

```bash
AlertProcessor/.venv/Scripts/python.exe -m pytest AlertProcessor/tests/nodes/test_detectors/test_callback_third_party_drain.py -q
```

Expected: PASS, all tests in the file pass.

- [ ] **Step 4: Commit Task 1-2 changes**

Run:

```bash
git -C AlertProcessor add nodes/detectors/callback_third_party_drain.py nodes/detectors/__init__.py tests/fixtures/ekubo_callback_drain.py tests/nodes/test_detectors/test_callback_third_party_drain.py
git -C AlertProcessor commit -m "feat: add callback third-party drain detector"
```

## Task 3: Add failing offline rule-chain replay test

**Files:**
- Create: `tests/engine/test_ekubo_callback_drain_replay.py`

- [ ] **Step 1: Write failing replay test**

Create `tests/engine/test_ekubo_callback_drain_replay.py`:

```python
from __future__ import annotations

import pytest

from engine.executor import ChainExecutor
from engine.parser import ChainParser
from nodes.base import BaseNode, NodeCategory, NodeOutput, NodeRegistry, PortDef
from nodes.detectors.callback_third_party_drain import CallbackThirdPartyDrainDetector
from tests.fixtures.ekubo_callback_drain import ATTACKER, ATTACK_TX_HASH, VICTIM, ekubo_attack_context


class _ReplayTrigger(BaseNode):
    name = "_ekubo_replay_trigger"
    label = "Ekubo Replay Trigger"
    category = NodeCategory.INPUT
    icon = ""
    color = ""

    @classmethod
    def get_inputs(cls):
        return []

    @classmethod
    def get_outputs(cls):
        return [PortDef(key="output", label="输出", data_type="context")]

    async def execute(self, context, inputs):
        return NodeOutput(node_id=self.node_id, node_type="input", passed=True, context=dict(context))


@pytest.fixture(autouse=True)
def register_replay_nodes():
    saved_nodes = dict(NodeRegistry._nodes)
    NodeRegistry.register(_ReplayTrigger)
    NodeRegistry.register(CallbackThirdPartyDrainDetector)
    yield
    NodeRegistry._nodes.clear()
    NodeRegistry._nodes.update(saved_nodes)


@pytest.mark.asyncio
async def test_ekubo_transaction_replay_hits_callback_drain_detector():
    chain = ChainParser.parse({
        "nodes": [
            {"id": "t1", "type": "_ekubo_replay_trigger"},
            {"id": "d1", "type": "callback_third_party_drain"},
        ],
        "edges": [
            {"id": "e1", "source": "t1", "sourcePort": "output", "target": "d1", "targetPort": "input"},
        ],
    })

    ctx = await ChainExecutor().execute(chain, ekubo_attack_context())

    assert ctx.get_success()
    output = ctx.get_output("d1")
    assert output is not None
    assert output.passed is True
    assert output.score == 100.0
    assert output.severity == "CRITICAL"
    assert "callback_drain" in output.labels
    assert output.context["tx_hash"] == ATTACK_TX_HASH

    evidence = output.context["detection"]["evidence"]
    assert evidence["victim"] == VICTIM
    assert evidence["profit_address"] == ATTACKER
    assert evidence["repeat_count"] == 85
```

- [ ] **Step 2: Run replay test to verify RED if executor output port assumptions are wrong**

Run:

```bash
AlertProcessor/.venv/Scripts/python.exe -m pytest AlertProcessor/tests/engine/test_ekubo_callback_drain_replay.py -q
```

Expected: Either PASS if the existing `BaseDetector.execute` behavior matches the test, or FAIL with a concrete mismatch in output context shape. If it passes immediately because Task 2 already implemented the production detector, this is acceptable only for this replay test because the production behavior was already driven by earlier failing unit tests.

## Task 4: Adjust replay integration if needed and run focused suite

**Files:**
- Modify if needed: `tests/engine/test_ekubo_callback_drain_replay.py`
- Modify if needed: `nodes/detectors/callback_third_party_drain.py`

- [ ] **Step 1: If replay test failed due output port shape, update assertion only**

If `output.context["detection"]` is missing but detector evidence is available under another existing executor field, change only the assertions to match existing `BaseDetector.execute` behavior. Do not weaken the semantic assertions. The final assertions must still check:

```python
assert output.passed is True
assert output.score == 100.0
assert output.severity == "CRITICAL"
assert "callback_drain" in output.labels
assert evidence["victim"] == VICTIM
assert evidence["profit_address"] == ATTACKER
assert evidence["repeat_count"] == 85
```

- [ ] **Step 2: Run replay test to verify GREEN**

Run:

```bash
AlertProcessor/.venv/Scripts/python.exe -m pytest AlertProcessor/tests/engine/test_ekubo_callback_drain_replay.py -q
```

Expected: PASS.

- [ ] **Step 3: Run detector focused suite**

Run:

```bash
AlertProcessor/.venv/Scripts/python.exe -m pytest AlertProcessor/tests/nodes/test_detectors/test_callback_third_party_drain.py AlertProcessor/tests/engine/test_ekubo_callback_drain_replay.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit replay test**

Run:

```bash
git -C AlertProcessor add tests/engine/test_ekubo_callback_drain_replay.py nodes/detectors/callback_third_party_drain.py
git -C AlertProcessor commit -m "test: add offline Ekubo callback drain replay"
```

## Task 5: Update detector strategy documentation

**Files:**
- Modify: `docs/EKUBO_ATTACK_DETECTOR_STRATEGY.md`

- [ ] **Step 1: Add implementation status section**

Append to `docs/EKUBO_ATTACK_DETECTOR_STRATEGY.md`:

```markdown
## Implementation Status

- Detector: `callback_third_party_drain`
- Implementation file: `nodes/detectors/callback_third_party_drain.py`
- Offline fixture: `tests/fixtures/ekubo_callback_drain.py`
- Replay test: `tests/engine/test_ekubo_callback_drain_replay.py`
- Unit tests: `tests/nodes/test_detectors/test_callback_third_party_drain.py`

The implementation uses summarized offline transaction data rather than live Phalcon, RPC, or explorer calls. This keeps the replay deterministic and suitable for CI.
```

- [ ] **Step 2: Run focused tests again**

Run:

```bash
AlertProcessor/.venv/Scripts/python.exe -m pytest AlertProcessor/tests/nodes/test_detectors/test_callback_third_party_drain.py AlertProcessor/tests/engine/test_ekubo_callback_drain_replay.py -q
```

Expected: PASS.

- [ ] **Step 3: Commit docs**

Run:

```bash
git -C AlertProcessor add -f docs/EKUBO_ATTACK_DETECTOR_STRATEGY.md
git -C AlertProcessor commit -m "docs: record Ekubo detector implementation status"
```

## Self-Review

Spec coverage:

- New `callback_third_party_drain` detector: Task 2.
- Offline Ekubo fixture: Task 1.
- Unit test for Ekubo CRITICAL hit: Task 1.
- Normal router/swap non-hit: Task 1.
- Rule-chain replay test: Tasks 3-4.
- Documentation update: Task 5.
- No online Phalcon/RPC dependency: fixture-only tests in Task 1 and Task 3.

Placeholder scan: no TBD/TODO/implement-later placeholders remain. All file paths, commands, and expected results are concrete.

Type consistency: tests instantiate `DetectorInputMixin`, detector accepts `TransactionContext`, fixture data uses existing `extra` pattern, and replay test uses existing `NodeRegistry`, `ChainParser`, and `ChainExecutor` conventions.
