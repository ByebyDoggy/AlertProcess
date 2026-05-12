import pytest

from engine.script_context import ScriptContext
from nodes.base import NodeOutput


def test_script_context_get_transfers_from_extra():
    ctx = ScriptContext({
        "chain_id": 1,
        "tx_hash": "0xabc",
        "parsed_transfers": [
            {"token_address": "0xToken", "from_address": "0xa", "to_address": "0xb", "amount": 10},
        ],
    })

    transfers = ctx.get_transfers("0xtoken")

    assert len(transfers) == 1
    assert transfers[0]["amount"] == 10


def test_script_context_get_trace_calls_from_extra():
    ctx = ScriptContext({
        "eth_trace": {
            "traces": [
                {
                    "action": {
                        "callType": "delegatecall",
                        "from": "0x1",
                        "to": "0x2",
                        "input": "0xabcdef001122",
                        "value": "0x0",
                    },
                    "traceAddress": [0, 1],
                }
            ]
        }
    })

    calls = ctx.get_trace_calls(min_depth=1)

    assert len(calls) == 1
    assert calls[0]["depth"] == 2
    assert calls[0]["function_selector"] == "0xabcdef00"
    assert calls[0]["call_type"] == "delegatecall"


def test_script_context_get_inputs():
    output = NodeOutput(node_id="detector", node_type="detection", score=80, passed=True)
    ctx = ScriptContext({}, {"primary": [output]})

    assert ctx.get_input_outputs("primary") == [output]
    assert ctx.get_input_outputs() == [output]


def test_script_context_tools():
    ctx = ScriptContext({})

    assert ctx.calculate_roi(150, 100) == 50
    assert ctx.calculate_roi(150, 0) == 0
    assert ctx.match_pattern(r"0x[a-f0-9]+", "target 0xabc") is True


def test_script_context_match_sequence():
    ctx = ScriptContext({})
    events = [
        {"type": "swap"},
        {"type": "transfer"},
        {"type": "approval"},
    ]

    matches = ctx.match_sequence(events, ["swap", "approval"])

    assert len(matches) == 1
    assert matches[0]["start_index"] == 0
    assert matches[0]["end_index"] == 2
