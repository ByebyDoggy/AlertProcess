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
    assert evidence["top_profit_address"] == JUDAO
    assert evidence["lp_loss_usd"] > 1_000_000
    assert evidence["sender_profit_usd"] > 200_000
    assert evidence["flash_loan_present"] is True
    assert evidence["temporary_contract_count"] == 2
