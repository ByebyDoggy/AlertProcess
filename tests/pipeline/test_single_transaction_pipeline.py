from datetime import UTC, datetime, timedelta

import pytest

from backend.detection import DetectionContext, DetectionResult, DetectionScript
from backend.pipeline.single_transaction import SingleTransactionRiskPipeline
from backend.providers.address_age import StaticAddressAgeProvider
from backend.providers.trace import StaticTraceProvider
from backend.strategies.token_contract_active_lp_drain import TokenContractActiveLPDrainScript

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
            {"token": usdt, "from": lp, "to": ATTACKER, "amount_raw": "1500000000000000000000000"},
            {"token": token_contract, "from": lp, "to": token_contract, "amount_raw": "1"},
            {"token": usdt, "from": token_contract, "to": ATTACKER, "amount_raw": "10000000000000000000000"},
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
