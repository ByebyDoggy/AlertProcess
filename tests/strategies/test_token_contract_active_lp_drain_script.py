import pytest

from backend.detection import DetectionContext
from backend.strategies.token_contract_active_lp_drain import TokenContractActiveLPDrainScript
from tests.fixtures.judao_token_active_lp_drain import (
    JUDAO,
    JUDAO_LP,
    SENDER,
    build_judao_context,
    build_normal_fee_token_context,
)


@pytest.mark.asyncio
async def test_judao_fixture_detects_critical_token_contract_active_lp_drain_script():
    script = TokenContractActiveLPDrainScript()
    ctx = DetectionContext.from_dict(build_judao_context())

    result = await script.detect(ctx)

    assert result.passed is True
    assert result.severity == "CRITICAL"
    assert result.score >= 90.0
    assert "token_contract_active_lp_drain" in result.labels
    assert "lp_top_loss" in result.labels
    assert "token_contract_top_profit" in result.labels
    assert "business_logic_anomaly" in result.labels
    assert "flash_loan_amplified" in result.labels
    assert "temporary_contract_execution" in result.labels

    assert result.entities["token_contract"] == JUDAO
    assert result.entities["lp_address"] == JUDAO_LP
    assert result.entities["sender_profit_address"] == SENDER
    assert result.details["lp_loss_usd"] > 1_000_000
    assert result.details["sender_profit_usd"] > 200_000
    assert result.details["token_contract_fund_flow_count"] >= 2
    assert result.details["token_contract_call_count"] >= 3
    assert result.details["pair_swap_count"] >= 2
    assert result.details["reserve_read_count"] >= 2
    assert result.details["flash_loan_present"] is True
    assert result.details["temporary_contract_count"] == 2
    assert {item.kind for item in result.evidence} >= {"LP_TOP_LOSS", "SENDER_PROFIT", "TOKEN_CONTRACT_ACTIVE_FLOW"}


@pytest.mark.asyncio
async def test_judao_fixture_detects_critical_with_normalized_trace_address_keys():
    script = TokenContractActiveLPDrainScript()
    payload = build_judao_context()
    payload["trace_calls"] = [
        {
            "from_address": call["caller"],
            "to_address": call["callee"],
            "selector": call["selector"],
            "operation": call["operation"],
        }
        for call in payload["trace_calls"]
    ]
    ctx = DetectionContext.from_dict(payload)

    result = await script.detect(ctx)

    assert result.passed is True
    assert result.severity == "CRITICAL"
    assert result.details["token_contract_call_count"] >= 3
    assert result.details["pair_swap_count"] >= 2
    assert result.details["reserve_read_count"] >= 2


@pytest.mark.asyncio
async def test_judao_fixture_detects_critical_with_raw_from_to_trace_keys():
    script = TokenContractActiveLPDrainScript()
    payload = build_judao_context()
    payload["trace_calls"] = [
        {
            "from": call["caller"],
            "to": call["callee"],
            "selector": call["selector"],
            "operation": call["operation"],
        }
        for call in payload["trace_calls"]
    ]
    ctx = DetectionContext.from_dict(payload)

    result = await script.detect(ctx)

    assert result.passed is True
    assert result.severity == "CRITICAL"
    assert result.details["token_contract_call_count"] >= 3
    assert result.details["pair_swap_count"] >= 2
    assert result.details["reserve_read_count"] >= 2


@pytest.mark.asyncio
async def test_normal_fee_token_swap_does_not_trigger_script():
    script = TokenContractActiveLPDrainScript()
    ctx = DetectionContext.from_dict(build_normal_fee_token_context())

    result = await script.detect(ctx)

    assert result.passed is False
    assert result.score < 40.0
    assert result.labels == []
    assert result.details["reason"] in {
        "lp loss below threshold",
        "sender profit below threshold",
        "no active token contract lp drain",
    }
