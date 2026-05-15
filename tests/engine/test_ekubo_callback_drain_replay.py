import pytest

from engine.executor import ChainExecutor
from engine.parser import ChainParser
from tests.fixtures.ekubo_callback_drain import (
    ATTACKER,
    EKUBO_CORE,
    REPEAT_COUNT,
    TOTAL_RAW_AMOUNT,
    VICTIM,
    WBTC,
    build_ekubo_context,
)


@pytest.mark.asyncio
async def test_ekubo_transaction_replay_hits_callback_drain_detector():
    chain = ChainParser.parse({
        "nodes": [
            {"id": "trigger", "type": "alert_trigger"},
            {"id": "callback_drain", "type": "callback_third_party_drain"},
        ],
        "edges": [
            {"source": "trigger", "sourcePort": "output", "target": "callback_drain", "targetPort": "input"},
        ],
    })
    executor = ChainExecutor()

    ctx = await executor.execute(chain, build_ekubo_context())

    assert ctx.get_success()
    output = ctx.get_output("callback_drain")
    assert output is not None
    assert output.passed is True
    assert output.severity == "CRITICAL"
    assert output.score >= 90.0
    assert ctx.final_severity == "CRITICAL"
    assert "callback_drain" in ctx.collected_labels

    evidence = output.context["detection"]["evidence"]
    assert evidence["victim"] == VICTIM
    assert evidence["profit_address"] == ATTACKER
    assert evidence["protocol"] == EKUBO_CORE
    assert evidence["token"] == WBTC
    assert evidence["repeat_count"] == REPEAT_COUNT
    assert evidence["amount_raw"] == str(TOTAL_RAW_AMOUNT)
    assert evidence["callback_loop_count"] >= 80
