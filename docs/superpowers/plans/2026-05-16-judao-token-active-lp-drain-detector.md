# JUDAO Token Active LP Drain Detector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a focused `token_contract_active_lp_drain` detector that reuses existing flash-loan/economic anomaly concepts and detects token-contract-active LP drain behavior from the JUDAO incident via offline replay.

**Architecture:** Implement one new `BaseDetector` reading normalized `TransactionContext.extra` fields. Fixture data stores only the JUDAO fund-flow and trace summaries required for detection plus one normal behavior sample. Tests start with direct detector coverage, then add a minimal rule-chain replay.

**Tech Stack:** Python, pytest, AlertProcessor detector framework, `DetectorInputMixin.from_dict`, `ChainParser`, `ChainExecutor`.

---

## File Structure

- Create `tests/fixtures/judao_token_active_lp_drain.py`
  - Constants for the JUDAO incident.
  - `build_judao_context()` attack fixture.
  - `build_normal_fee_token_context()` false-positive fixture.
- Create `tests/nodes/test_detectors/test_token_contract_active_lp_drain.py`
  - Direct detector tests and registry test.
- Create `nodes/detectors/token_contract_active_lp_drain.py`
  - Detector implementation, config, helpers, registry registration.
- Modify `nodes/detectors/__init__.py`
  - Import/export `TokenContractActiveLPDrainDetector`.
- Create `tests/engine/test_judao_token_active_lp_drain_replay.py`
  - Minimal `alert_trigger -> token_contract_active_lp_drain` replay.
- Modify `docs/JUDAO_TOKEN_DETECTOR_STRATEGY.md`
  - Add implementation status after tests pass.

## Task 1: Attack and Normal Fixtures

**Files:**
- Create: `tests/fixtures/judao_token_active_lp_drain.py`

- [ ] **Step 1: Create fixture file**

Write `tests/fixtures/judao_token_active_lp_drain.py`:

```python
ATTACK_TX_HASH = "0x956e38b8ddb40ba080c8042c685ae52ee5c1b096f1d7f0c4a6c59be3eb4265bd"
SENDER = "0x5384b34c74024d6563b323351a4bbfa18432161b"
ENTRY_CONTRACT = "0x3b9bc53af5012b12b6886a665bb22382211ae432"
EXECUTOR_CONTRACT = "0x530904b5b5ec86cca0528a682614f57f87e7f079"
JUDAO = "0xf55dff7898930a2d28cdbc39d615b1624ac86888"
JUDAO_LP = "0x5d7b61e91cb59e90f7fae8d0fe2e73976161592f"
MOOLAH_PROXY = "0x8f73b65b4caaf64fba2af91cc5d4a2a1318e5d8c"
PANCAKE_ROUTER = "0x10ed43c718714eb63d5aa57b78b54704e256024e"
USDT = "0x55d398326f99059ff775485246999027b3197955"
WBNB = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"
NATIVE_BNB = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
DEAD = "0x000000000000000000000000000000000000dead"
FEE = "0x0000000000000000000000000000000000000fee"
INTERMEDIATE_USDT = "0x27ba602286ea321ea610a96bc8fdb8505489ffdb"
REWARD_A = "0xe7b95eaada89a0b2cce3086d5d4d1537d087a6e1"
REWARD_B = "0xccdd127594f24bf3a6ec08e5ea793203a8941540"
REWARD_C = "0x82ea37296171b3f06702b0a6e0671172f79910ba"
ERC1967_PROXY = "0x8599068597fd27d87514cb90c42300c03a474084"
WBNB_LP = "0x16b9a82891338f9ba80e2d6970fdda79d1eb0dae"

USDT_DECIMALS = 18
JUDAO_DECIMALS = 18
WBNB_DECIMALS = 18
USDT_PRICE = 0.999921782
JUDAO_PRICE = 0.355330638
WBNB_PRICE = 626.76874723

FLASH_LOAN_RAW = 2_295_723_159_642_210_185_991_283
LP_TO_EXECUTOR_JUDAO_RAW = 5_473_557_853_503_254_662_548_079
LP_TO_JUDAO_RAW = 3_019_432_906_656_452_109_766_422
LP_TO_DEAD_JUDAO_RAW = 3_019_432_906_656_452_109_766_424
JUDAO_TO_LP_RAW = 389_206_461_086_932_694_355_629
EXECUTOR_TO_LP_JUDAO_RAW = 5_198_393_287_782_908_758_112_995
LP_TO_EXECUTOR_USDT_RAW = 2_523_596_497_552_140_965_784_945
EXECUTOR_TO_SENDER_USDT_RAW = 205_259_490_762_457_026_328_485
SENDER_BNB_RAW = 36_000_000_000_000_000_000


def transfer(token: str, from_addr: str, to_addr: str, amount_raw: int) -> dict:
    return {
        "token": token,
        "from": from_addr,
        "to": to_addr,
        "amount_raw": str(amount_raw),
    }


def call(caller: str, callee: str, selector: str, operation: str = "CALL") -> dict:
    return {
        "caller": caller,
        "callee": callee,
        "selector": selector,
        "operation": operation,
    }


def build_judao_context() -> dict:
    return {
        "chain_id": 56,
        "tx_hash": ATTACK_TX_HASH,
        "from_address": SENDER,
        "to_address": ENTRY_CONTRACT,
        "value": 0,
        "top_profit_address": JUDAO,
        "top_loss_address": JUDAO_LP,
        "address_labels": {
            JUDAO_LP: "0x5d7b_Cake-LP",
            WBNB_LP: "0x16b9_Cake-LP",
            PANCAKE_ROUTER: "PancakeSwap: Router v2",
            MOOLAH_PROXY: "ListaDAO : Moolah (Proxy)",
            USDT: "USDT",
            WBNB: "WBNB",
            JUDAO: "JUDAO",
        },
        "stablecoins": [USDT],
        "wrapped_native_tokens": [WBNB, NATIVE_BNB],
        "token_prices": {
            USDT: USDT_PRICE,
            JUDAO: JUDAO_PRICE,
            WBNB: WBNB_PRICE,
            NATIVE_BNB: WBNB_PRICE,
        },
        "token_decimals": {
            USDT: USDT_DECIMALS,
            JUDAO: JUDAO_DECIMALS,
            WBNB: WBNB_DECIMALS,
            NATIVE_BNB: WBNB_DECIMALS,
        },
        "transfers": [
            transfer(USDT, MOOLAH_PROXY, EXECUTOR_CONTRACT, FLASH_LOAN_RAW),
            transfer(USDT, EXECUTOR_CONTRACT, JUDAO_LP, FLASH_LOAN_RAW),
            transfer(JUDAO, JUDAO_LP, FEE, 169_285_294_438_244_989_563_342),
            transfer(JUDAO, JUDAO_LP, EXECUTOR_CONTRACT, LP_TO_EXECUTOR_JUDAO_RAW),
            transfer(JUDAO, JUDAO_LP, JUDAO, LP_TO_JUDAO_RAW),
            transfer(JUDAO, JUDAO_LP, DEAD, LP_TO_DEAD_JUDAO_RAW),
            transfer(JUDAO, EXECUTOR_CONTRACT, JUDAO_LP, EXECUTOR_TO_LP_JUDAO_RAW),
            transfer(JUDAO, JUDAO, JUDAO_LP, JUDAO_TO_LP_RAW),
            transfer(USDT, JUDAO_LP, INTERMEDIATE_USDT, 236_331_524_657_750_233_556_859),
            transfer(USDT, INTERMEDIATE_USDT, JUDAO, 236_331_524_657_750_233_556_859),
            transfer(USDT, JUDAO, REWARD_A, 10_106_292_909_056_116_654_102),
            transfer(USDT, JUDAO, REWARD_B, 44_864_746_539_606_315_267_924),
            transfer(USDT, JUDAO, REWARD_C, 54_971_039_448_662_431_922_027),
            transfer(USDT, JUDAO, ERC1967_PROXY, 126_390_017_945_602_680_958_641),
            transfer(USDT, JUDAO_LP, EXECUTOR_CONTRACT, LP_TO_EXECUTOR_USDT_RAW),
            transfer(USDT, EXECUTOR_CONTRACT, MOOLAH_PROXY, FLASH_LOAN_RAW),
            transfer(USDT, EXECUTOR_CONTRACT, WBNB_LP, 22_613_847_147_473_753_465_178),
            transfer(WBNB, WBNB_LP, PANCAKE_ROUTER, SENDER_BNB_RAW),
            transfer(NATIVE_BNB, PANCAKE_ROUTER, SENDER, SENDER_BNB_RAW),
            transfer(USDT, EXECUTOR_CONTRACT, SENDER, EXECUTOR_TO_SENDER_USDT_RAW),
        ],
        "trace_calls": [
            call(SENDER, ENTRY_CONTRACT, "", "CREATE"),
            call(ENTRY_CONTRACT, EXECUTOR_CONTRACT, "", "CREATE"),
            call(EXECUTOR_CONTRACT, JUDAO, "0x5930919b", "STATICCALL"),
            call(EXECUTOR_CONTRACT, MOOLAH_PROXY, "0xe0232b42"),
            call(EXECUTOR_CONTRACT, PANCAKE_ROUTER, "0x38ed1739"),
            call(PANCAKE_ROUTER, JUDAO_LP, "0x022c0d9f"),
            call(JUDAO_LP, JUDAO, "0xa9059cbb"),
            call(JUDAO, JUDAO_LP, "0x0902f1ac", "STATICCALL"),
            call(JUDAO, PANCAKE_ROUTER, "0x1f00ca74", "STATICCALL"),
            call(JUDAO, PANCAKE_ROUTER, "0xd06ca61f", "STATICCALL"),
            call(JUDAO, PANCAKE_ROUTER, "0x38ed1739"),
            call(PANCAKE_ROUTER, JUDAO_LP, "0x022c0d9f"),
            call(JUDAO, ERC1967_PROXY, "0xaf10939b"),
            call(EXECUTOR_CONTRACT, JUDAO_LP, "0x022c0d9f"),
            call(EXECUTOR_CONTRACT, PANCAKE_ROUTER, "0x4a25d94a"),
            call(PANCAKE_ROUTER, WBNB_LP, "0x022c0d9f"),
            call(PANCAKE_ROUTER, WBNB, "0x2e1a7d4d"),
        ],
        "flash_loan_present": True,
        "temporary_contract_count": 2,
    }


def build_normal_fee_token_context() -> dict:
    fee_token = "0x1111111111111111111111111111111111111111"
    lp = "0x2222222222222222222222222222222222222222"
    user = "0x3333333333333333333333333333333333333333"
    treasury = "0x4444444444444444444444444444444444444444"
    return {
        "chain_id": 56,
        "tx_hash": "0xnormaljudao000000000000000000000000000000000000000000000000000000",
        "from_address": user,
        "to_address": PANCAKE_ROUTER,
        "value": 0,
        "top_profit_address": user,
        "top_loss_address": user,
        "address_labels": {lp: "ExampleToken-Cake-LP", PANCAKE_ROUTER: "PancakeSwap: Router v2"},
        "stablecoins": [USDT],
        "wrapped_native_tokens": [WBNB, NATIVE_BNB],
        "token_prices": {USDT: USDT_PRICE, fee_token: 1.0},
        "token_decimals": {USDT: 18, fee_token: 18},
        "transfers": [
            transfer(fee_token, user, lp, 10_000 * 10**18),
            transfer(fee_token, user, fee_token, 300 * 10**18),
            transfer(fee_token, fee_token, treasury, 300 * 10**18),
            transfer(USDT, lp, user, 9_900 * 10**18),
        ],
        "trace_calls": [
            call(user, PANCAKE_ROUTER, "0x38ed1739"),
            call(PANCAKE_ROUTER, lp, "0x022c0d9f"),
            call(fee_token, treasury, "0xa9059cbb"),
        ],
        "flash_loan_present": False,
        "temporary_contract_count": 0,
    }
```

- [ ] **Step 2: Do not run tests yet**

This fixture exists only to support the first failing test in Task 2.

## Task 2: Direct Detector Tests RED

**Files:**
- Create: `tests/nodes/test_detectors/test_token_contract_active_lp_drain.py`

- [ ] **Step 1: Write failing direct tests**

Write `tests/nodes/test_detectors/test_token_contract_active_lp_drain.py`:

```python
import pytest

from nodes.base import NodeRegistry
from nodes.detectors.base import DetectorInputMixin
from nodes.detectors.token_contract_active_lp_drain import TokenContractActiveLPDrainDetector
from tests.fixtures.judao_token_active_lp_drain import (
    EXECUTOR_TO_SENDER_USDT_RAW,
    JUDAO,
    JUDAO_LP,
    SENDER,
    build_judao_context,
    build_normal_fee_token_context,
)


class TestTokenContractActiveLPDrainDetector:
    def test_registered(self):
        assert NodeRegistry.get("token_contract_active_lp_drain") is TokenContractActiveLPDrainDetector

    @pytest.mark.asyncio
    async def test_judao_fixture_detects_critical_token_contract_active_lp_drain(self):
        detector = TokenContractActiveLPDrainDetector(node_id="token_lp_drain")
        tx = DetectorInputMixin.from_dict(build_judao_context())

        output = await detector.process(tx)

        assert output.passed is True
        assert output.severity == "CRITICAL"
        assert output.score >= 90.0
        assert "token_contract_active_lp_drain" in output.labels
        assert "lp_top_loss" in output.labels
        assert "token_contract_top_profit" in output.labels
        assert "business_logic_anomaly" in output.labels
        assert "flash_loan_amplified" in output.labels
        assert "temporary_contract_execution" in output.labels

        evidence = output.detection["evidence"]
        assert evidence["token_contract"] == JUDAO
        assert evidence["lp_address"] == JUDAO_LP
        assert evidence["sender_profit_address"] == SENDER
        assert evidence["top_profit_address"] == JUDAO
        assert evidence["sender_profit_raw_by_token"]["0x55d398326f99059ff775485246999027b3197955"] == str(EXECUTOR_TO_SENDER_USDT_RAW)
        assert evidence["lp_loss_usd"] > 1_000_000
        assert evidence["sender_profit_usd"] > 200_000
        assert evidence["token_contract_fund_flow_count"] >= 4
        assert evidence["token_contract_call_count"] >= 3
        assert evidence["pair_swap_count"] >= 2
        assert evidence["reserve_read_count"] >= 1
        assert evidence["flash_loan_present"] is True
        assert evidence["temporary_contract_count"] == 2

    @pytest.mark.asyncio
    async def test_normal_fee_token_swap_does_not_trigger(self):
        detector = TokenContractActiveLPDrainDetector(node_id="token_lp_drain")
        tx = DetectorInputMixin.from_dict(build_normal_fee_token_context())

        output = await detector.process(tx)

        assert output.passed is False
        assert output.score < 40.0
        assert output.labels == []
        assert output.detection["reason"] == "top loss is not a confirmed LP"
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
AlertProcessor/.venv/Scripts/python.exe -m pytest AlertProcessor/tests/nodes/test_detectors/test_token_contract_active_lp_drain.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'nodes.detectors.token_contract_active_lp_drain'`.

## Task 3: Minimal Detector Implementation GREEN

**Files:**
- Create: `nodes/detectors/token_contract_active_lp_drain.py`
- Modify: `nodes/detectors/__init__.py`

- [ ] **Step 1: Implement detector**

Create `nodes/detectors/token_contract_active_lp_drain.py`:

```python
from __future__ import annotations

from collections import defaultdict
from typing import Any

from pydantic import Field

from nodes.base import NodeRegistry, score_to_severity
from nodes.detectors.base import BaseDetector, DetectorConfigMixin, DetectorOutputMixin
from nodes.models import TransactionContext


BSC_USDT = "0x55d398326f99059ff775485246999027b3197955"
BSC_WBNB = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"
NATIVE_PLACEHOLDER = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
PAIR_SWAP_SELECTOR = "0x022c0d9f"
GET_RESERVES_SELECTOR = "0x0902f1ac"
FLASH_LOAN_SELECTORS = {"0xe0232b42"}


class TokenContractActiveLPDrainOutput(DetectorOutputMixin):
    pass


def _addr(value: Any) -> str:
    return str(value or "").lower()


def _amount(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        cleaned = value.replace(",", "")
        try:
            return int(cleaned, 16) if cleaned.startswith("0x") else int(cleaned)
        except ValueError:
            try:
                return int(float(cleaned))
            except ValueError:
                return 0
    return 0


def _usd(token: str, raw_amount: int, prices: dict[str, Any], decimals: dict[str, Any]) -> float:
    token_key = _addr(token)
    price = float(prices.get(token_key, prices.get(token, 0.0)) or 0.0)
    token_decimals = int(decimals.get(token_key, decimals.get(token, 18)) or 18)
    return raw_amount / (10 ** token_decimals) * price


def _net_by_token(address: str, transfers: list[dict[str, Any]]) -> dict[str, int]:
    target = _addr(address)
    net: dict[str, int] = defaultdict(int)
    for transfer in transfers:
        token = _addr(transfer.get("token"))
        amount = _amount(transfer.get("amount_raw", transfer.get("amount", transfer.get("value"))))
        if _addr(transfer.get("to")) == target:
            net[token] += amount
        if _addr(transfer.get("from")) == target:
            net[token] -= amount
    return dict(net)


def _sum_positive_usd(net: dict[str, int], prices: dict[str, Any], decimals: dict[str, Any], tokens: set[str] | None = None) -> float:
    total = 0.0
    for token, amount in net.items():
        if amount <= 0:
            continue
        if tokens is not None and token not in tokens:
            continue
        total += _usd(token, amount, prices, decimals)
    return total


def _sum_negative_usd(net: dict[str, int], prices: dict[str, Any], decimals: dict[str, Any]) -> float:
    return sum(_usd(token, -amount, prices, decimals) for token, amount in net.items() if amount < 0)


class TokenContractActiveLPDrainDetector(BaseDetector):
    name: str = "token_contract_active_lp_drain"
    label: str = "Token合约主动LP抽离检测"
    description: str = "检测 token 合约自身作为资金流/调用流参与者并伴随 LP top loss 和 sender 获利的业务逻辑漏洞模式"
    icon: str = ""
    color: str = "#dc2626"

    class ConfigModel(DetectorConfigMixin):
        threshold: float = Field(default=40.0, ge=0, le=100, description="0-100，评分达到此值视为 passed")
        min_lp_loss_usd: float = Field(default=100000.0, ge=0, description="LP 最小净损失 USD")
        critical_lp_loss_usd: float = Field(default=1000000.0, ge=0, description="LP 严重净损失 USD")
        min_sender_profit_usd: float = Field(default=10000.0, ge=0, description="sender 最小稳定币/原生币利润 USD")
        min_token_contract_call_count: int = Field(default=1, ge=0, description="token 合约作为 caller 的最小调用次数")

    OutputModel: type = TokenContractActiveLPDrainOutput

    async def process(self, tx_context: TransactionContext) -> TokenContractActiveLPDrainOutput:
        extra = tx_context.extra or {}
        transfers = extra.get("transfers") or []
        trace_calls = extra.get("trace_calls") or []
        sender = _addr(tx_context.from_address)
        top_profit = _addr(extra.get("top_profit_address"))
        lp = _addr(extra.get("top_loss_address"))
        labels_by_address = {_addr(k): str(v).lower() for k, v in (extra.get("address_labels") or {}).items()}
        prices = {_addr(k): v for k, v in (extra.get("token_prices") or {}).items()}
        decimals = {_addr(k): v for k, v in (extra.get("token_decimals") or {}).items()}
        stable_tokens = {_addr(t) for t in extra.get("stablecoins") or []} | {BSC_USDT}
        wrapped_tokens = {_addr(t) for t in extra.get("wrapped_native_tokens") or []} | {BSC_WBNB, NATIVE_PLACEHOLDER}
        profit_tokens = stable_tokens | wrapped_tokens

        if not lp:
            return self._miss("missing top loss address")

        lp_confirmed, lp_evidence = self._confirm_lp(lp, transfers, trace_calls, labels_by_address)
        if not lp_confirmed:
            return self._miss("top loss is not a confirmed LP")

        lp_net = _net_by_token(lp, transfers)
        lp_loss_usd = _sum_negative_usd(lp_net, prices, decimals)
        sender_net = _net_by_token(sender, transfers)
        sender_profit_usd = _sum_positive_usd(sender_net, prices, decimals, profit_tokens)

        if lp_loss_usd < self.config.get("min_lp_loss_usd", 100000.0):
            return self._miss("LP loss is below threshold")
        if sender_profit_usd < self.config.get("min_sender_profit_usd", 10000.0):
            return self._miss("sender profit is below threshold")

        candidates = self._candidate_token_contracts(lp, transfers, stable_tokens | wrapped_tokens)
        best: dict[str, Any] | None = None
        best_score = 0.0

        for token in candidates:
            fund_flow_count = sum(
                1 for transfer in transfers
                if _addr(transfer.get("from")) == token or _addr(transfer.get("to")) == token
            )
            call_count = sum(1 for call in trace_calls if _addr(call.get("caller")) == token)
            token_is_top_profit = token == top_profit
            active_in_fund_flow = fund_flow_count > 0
            active_as_caller = call_count >= self.config.get("min_token_contract_call_count", 1)
            if not token_is_top_profit and not (active_in_fund_flow and active_as_caller):
                continue

            pair_swap_count = sum(1 for call in trace_calls if _addr(call.get("callee")) == lp and _addr(call.get("selector")) == PAIR_SWAP_SELECTOR)
            reserve_read_count = sum(1 for call in trace_calls if _addr(call.get("callee")) == lp and _addr(call.get("selector")) == GET_RESERVES_SELECTOR)
            flash_loan_present = bool(extra.get("flash_loan_present")) or any(_addr(call.get("selector")) in FLASH_LOAN_SELECTORS for call in trace_calls)
            temporary_contract_count = int(extra.get("temporary_contract_count") or sum(1 for call in trace_calls if str(call.get("operation", "")).upper() == "CREATE"))

            score = 20.0
            if lp_loss_usd >= self.config.get("min_lp_loss_usd", 100000.0):
                score += 25.0
            if lp_loss_usd >= self.config.get("critical_lp_loss_usd", 1000000.0):
                score += 20.0
            if token_is_top_profit:
                score += 20.0
            if active_in_fund_flow:
                score += 15.0
            if active_as_caller:
                score += 15.0
            if sender_profit_usd >= self.config.get("min_sender_profit_usd", 10000.0):
                score += 15.0
            if flash_loan_present:
                score += 10.0
            if temporary_contract_count > 0:
                score += 10.0
            score = min(score, 100.0)

            if score > best_score:
                best_score = score
                best = {
                    "token_contract": token,
                    "lp_address": lp,
                    "sender_profit_address": sender,
                    "top_profit_address": top_profit,
                    "lp_loss_usd": round(lp_loss_usd, 2),
                    "sender_profit_usd": round(sender_profit_usd, 2),
                    "lp_loss_raw_by_token": {k: str(-v) for k, v in lp_net.items() if v < 0},
                    "sender_profit_raw_by_token": {k: str(v) for k, v in sender_net.items() if v > 0},
                    "token_contract_fund_flow_count": fund_flow_count,
                    "token_contract_call_count": call_count,
                    "pair_swap_count": pair_swap_count,
                    "reserve_read_count": reserve_read_count,
                    "flash_loan_present": flash_loan_present,
                    "temporary_contract_count": temporary_contract_count,
                    "lp_evidence": lp_evidence,
                }

        if not best:
            return self._miss("no active token contract participant matched LP drain")

        output_labels = ["token_contract_active_lp_drain", "lp_top_loss", "business_logic_anomaly"]
        if best["token_contract"] == top_profit:
            output_labels.append("token_contract_top_profit")
        if best["flash_loan_present"]:
            output_labels.append("flash_loan_amplified")
        if best["temporary_contract_count"] > 0:
            output_labels.append("temporary_contract_execution")

        return TokenContractActiveLPDrainOutput(
            score=best_score,
            passed=best_score >= self.config.get("threshold", 40.0),
            severity=score_to_severity(best_score),
            labels=output_labels,
            detection={
                "reason": "matched token contract active LP drain",
                "evidence": best,
            },
            logs=[
                f"LP loss ${best['lp_loss_usd']:,.2f}",
                f"sender profit ${best['sender_profit_usd']:,.2f}",
                f"token contract calls {best['token_contract_call_count']}",
            ],
        )

    def _confirm_lp(
        self,
        lp: str,
        transfers: list[dict[str, Any]],
        trace_calls: list[dict[str, Any]],
        labels_by_address: dict[str, str],
    ) -> tuple[bool, list[str]]:
        evidence = []
        label = labels_by_address.get(lp, "")
        if any(term in label for term in ("lp", "pair", "cake-lp")):
            evidence.append("label")
        if any(_addr(call.get("callee")) == lp and _addr(call.get("selector")) == GET_RESERVES_SELECTOR for call in trace_calls):
            evidence.append("get_reserves")
        if any(_addr(call.get("callee")) == lp and _addr(call.get("selector")) == PAIR_SWAP_SELECTOR for call in trace_calls):
            evidence.append("pair_swap")
        lp_tokens = {
            _addr(transfer.get("token"))
            for transfer in transfers
            if _addr(transfer.get("from")) == lp or _addr(transfer.get("to")) == lp
        }
        if len(lp_tokens) >= 2:
            evidence.append("multi_token_flow")
        return bool(evidence), evidence

    def _candidate_token_contracts(
        self,
        lp: str,
        transfers: list[dict[str, Any]],
        excluded_tokens: set[str],
    ) -> set[str]:
        candidates = set()
        for transfer in transfers:
            if _addr(transfer.get("from")) != lp and _addr(transfer.get("to")) != lp:
                continue
            token = _addr(transfer.get("token"))
            if token and token not in excluded_tokens:
                candidates.add(token)
        return candidates

    def _miss(self, reason: str) -> TokenContractActiveLPDrainOutput:
        return TokenContractActiveLPDrainOutput(
            score=0.0,
            passed=False,
            severity="UNKNOWN",
            labels=[],
            detection={"reason": reason},
            logs=[reason],
        )


NodeRegistry.register(TokenContractActiveLPDrainDetector)
```

- [ ] **Step 2: Export detector**

Modify `nodes/detectors/__init__.py`:

```python
from nodes.detectors.token_contract_active_lp_drain import TokenContractActiveLPDrainDetector
```

Add to `__all__`:

```python
"TokenContractActiveLPDrainDetector",
```

- [ ] **Step 3: Run direct tests to verify GREEN**

Run:

```bash
AlertProcessor/.venv/Scripts/python.exe -m pytest AlertProcessor/tests/nodes/test_detectors/test_token_contract_active_lp_drain.py -q
```

Expected: PASS.

## Task 4: Rule-Chain Replay Test

**Files:**
- Create: `tests/engine/test_judao_token_active_lp_drain_replay.py`

- [ ] **Step 1: Write replay test**

Write `tests/engine/test_judao_token_active_lp_drain_replay.py`:

```python
import pytest

from engine.executor import ChainExecutor
from engine.parser import ChainParser
from tests.fixtures.judao_token_active_lp_drain import JUDAO, JUDAO_LP, SENDER, build_judao_context


@pytest.mark.asyncio
async def test_judao_transaction_replay_hits_token_contract_active_lp_drain_detector():
    chain = ChainParser.parse({
        "nodes": [
            {"id": "trigger", "type": "alert_trigger"},
            {"id": "token_lp_drain", "type": "token_contract_active_lp_drain"},
        ],
        "edges": [
            {"source": "trigger", "sourcePort": "output", "target": "token_lp_drain", "targetPort": "input"},
        ],
    })
    executor = ChainExecutor()

    ctx = await executor.execute(chain, build_judao_context())

    assert ctx.get_success()
    output = ctx.get_output("token_lp_drain")
    assert output is not None
    assert output.passed is True
    assert output.severity == "CRITICAL"
    assert output.score >= 90.0
    assert ctx.final_severity == "CRITICAL"
    assert "token_contract_active_lp_drain" in ctx.collected_labels
    assert "business_logic_anomaly" in ctx.collected_labels

    evidence = output.context["detection"]["evidence"]
    assert evidence["token_contract"] == JUDAO
    assert evidence["lp_address"] == JUDAO_LP
    assert evidence["sender_profit_address"] == SENDER
    assert evidence["flash_loan_present"] is True
    assert evidence["temporary_contract_count"] == 2
```

- [ ] **Step 2: Run replay test**

Run:

```bash
AlertProcessor/.venv/Scripts/python.exe -m pytest AlertProcessor/tests/engine/test_judao_token_active_lp_drain_replay.py -q
```

Expected: PASS.

- [ ] **Step 3: Run combined focused tests**

Run:

```bash
AlertProcessor/.venv/Scripts/python.exe -m pytest AlertProcessor/tests/nodes/test_detectors/test_token_contract_active_lp_drain.py AlertProcessor/tests/engine/test_judao_token_active_lp_drain_replay.py -q
```

Expected: PASS.

## Task 5: Documentation Update

**Files:**
- Modify: `docs/JUDAO_TOKEN_DETECTOR_STRATEGY.md`

- [ ] **Step 1: Append implementation status**

Append to `docs/JUDAO_TOKEN_DETECTOR_STRATEGY.md` before `## 结论`:

```markdown
## 落地状态（2026-05-16）

已按复用优先方案落地标准检测器 `token_contract_active_lp_drain`：

- 检测器文件：`nodes/detectors/token_contract_active_lp_drain.py`
- 离线 fixture：`tests/fixtures/judao_token_active_lp_drain.py`
- 单元测试：`tests/nodes/test_detectors/test_token_contract_active_lp_drain.py`
- 规则链回放测试：`tests/engine/test_judao_token_active_lp_drain_replay.py`

实现范围：复用已有 flash loan / economic anomaly / price manipulation 策略边界，仅新增 token 合约主动参与 LP drain 的窄职责检测逻辑。本 JUDAO fixture 输出 `CRITICAL`，正常 fee-on-transfer token swap fixture 不触发。

已通过针对性测试：

```bash
AlertProcessor/.venv/Scripts/python.exe -m pytest AlertProcessor/tests/nodes/test_detectors/test_token_contract_active_lp_drain.py AlertProcessor/tests/engine/test_judao_token_active_lp_drain_replay.py -q
```
```

- [ ] **Step 2: Confirm status only after tests passed**

Do not add this section until Task 4 combined focused tests pass.

## Task 6: Scoped Commit

**Files:**
- Add only intended JUDAO detector files and docs.

- [ ] **Step 1: Check status**

Run:

```bash
git -C AlertProcessor status --short
```

Expected: many unrelated dirty files may exist. Do not stage them.

- [ ] **Step 2: Stage intended files**

Run:

```bash
git -C AlertProcessor add nodes/detectors/token_contract_active_lp_drain.py nodes/detectors/__init__.py

git -C AlertProcessor add -f tests/fixtures/judao_token_active_lp_drain.py tests/nodes/test_detectors/test_token_contract_active_lp_drain.py tests/engine/test_judao_token_active_lp_drain_replay.py docs/JUDAO_TOKEN_DETECTOR_STRATEGY.md docs/superpowers/specs/2026-05-16-judao-token-active-lp-drain-detector-design.md docs/superpowers/plans/2026-05-16-judao-token-active-lp-drain-detector.md
```

- [ ] **Step 3: Verify staged names**

Run:

```bash
git -C AlertProcessor diff --cached --name-only
```

Expected staged files only:

```text
docs/JUDAO_TOKEN_DETECTOR_STRATEGY.md
docs/superpowers/plans/2026-05-16-judao-token-active-lp-drain-detector.md
docs/superpowers/specs/2026-05-16-judao-token-active-lp-drain-detector-design.md
nodes/detectors/__init__.py
nodes/detectors/token_contract_active_lp_drain.py
tests/engine/test_judao_token_active_lp_drain_replay.py
tests/fixtures/judao_token_active_lp_drain.py
tests/nodes/test_detectors/test_token_contract_active_lp_drain.py
```

- [ ] **Step 4: Commit**

Run:

```bash
git -C AlertProcessor commit -m "$(cat <<'EOF'
feat: add token contract LP drain detector

Detect token contracts that actively participate in LP drains while reusing existing flash-loan and economic-anomaly signals.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```
