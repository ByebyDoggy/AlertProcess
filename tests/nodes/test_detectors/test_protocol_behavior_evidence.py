import pytest

from nodes.detectors.protocol.access_control import AccessControlBypassDetector
from nodes.detectors.protocol.flash_loan_trace import FlashLoanTraceDetector
from nodes.detectors.protocol.signatures import FLASH_LOAN_SIGNATURES, PROXY_UPGRADE_SIGNATURES
from nodes.models import TransactionContext


ATTACKER = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
FLASH_POOL = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
CALLBACK_CONTRACT = "0xcccccccccccccccccccccccccccccccccccccccc"
DEX_POOL = "0xdddddddddddddddddddddddddddddddddddddddd"
LENDING_POOL = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
PROXY = "0x1111111111111111111111111111111111111111"
IMPLEMENTATION = "0x2222222222222222222222222222222222222222"
ADMIN_TARGET = "0x3333333333333333333333333333333333333333"


def _trace(action, trace_address):
    return {
        "type": "call",
        "action": {
            "callType": action.get("callType", "call"),
            "from": action.get("from", ATTACKER),
            "to": action.get("to", FLASH_POOL),
            "input": action.get("input", "0x"),
            "value": action.get("value", "0x0"),
            "gas": action.get("gas", "0x0"),
        },
        "result": {"gasUsed": "0x0", "output": "0x"},
        "traceAddress": trace_address,
        "subtraces": 0,
    }


def _context(traces):
    call_types = [trace["action"].get("callType", "").lower() for trace in traces]
    return TransactionContext.from_dict({
        "chain_id": 1,
        "tx_hash": "0x" + "1" * 64,
        "from_address": ATTACKER,
        "to_address": FLASH_POOL,
        "eth_trace": {
            "traces": traces,
            "trace_count": len(traces),
            "has_delegatecall": "delegatecall" in call_types,
            "has_staticcall": "staticcall" in call_types,
            "max_depth": max((len(trace["traceAddress"]) for trace in traces), default=0),
        },
    })


@pytest.mark.asyncio
async def test_flash_loan_selector_only_does_not_pass():
    selector = next(iter(FLASH_LOAN_SIGNATURES))
    detector = FlashLoanTraceDetector("flash", {"threshold": 50.0, "min_trace_count": 1})

    output = await detector.process(_context([
        _trace({"input": selector + "00" * 32}, []),
    ]))

    assert output.passed is False
    assert output.score < 50.0


@pytest.mark.asyncio
async def test_access_control_selector_only_does_not_pass():
    selector = next(iter(PROXY_UPGRADE_SIGNATURES))
    detector = AccessControlBypassDetector("access", {"threshold": 50.0, "min_trace_count": 1})

    output = await detector.process(_context([
        _trace({"to": PROXY, "input": selector + "00" * 32}, []),
    ]))

    assert output.passed is False
    assert output.score < 50.0


@pytest.mark.asyncio
async def test_flash_loan_behavior_without_known_selectors_passes():
    detector = FlashLoanTraceDetector("flash", {"threshold": 50.0, "min_trace_count": 2})

    output = await detector.process(_context([
        _trace({"to": FLASH_POOL, "input": "0xaaaaaaaa", "value": hex(100 * 10**18)}, []),
        _trace({"from": FLASH_POOL, "to": CALLBACK_CONTRACT, "input": "0xbbbbbbbb"}, [0]),
        _trace({"from": CALLBACK_CONTRACT, "to": DEX_POOL, "input": "0xcccccccc"}, [0, 0]),
        _trace({"from": CALLBACK_CONTRACT, "to": LENDING_POOL, "input": "0xdddddddd"}, [0, 1]),
        _trace({"from": CALLBACK_CONTRACT, "to": FLASH_POOL, "input": "0xeeeeeeee", "value": hex(100 * 10**18)}, [0, 2]),
    ]))

    assert output.passed is True
    assert output.score >= 50.0
    assert "FLASH_LOAN_BEHAVIOR:LARGE_TRANSIENT_VALUE" in output.labels
    assert "FLASH_LOAN_BEHAVIOR:POST_BORROW_FANOUT" in output.labels


@pytest.mark.asyncio
async def test_flash_loan_large_value_alone_does_not_pass():
    detector = FlashLoanTraceDetector("flash", {"threshold": 50.0, "min_trace_count": 1})

    output = await detector.process(_context([
        _trace({"to": FLASH_POOL, "input": "0xaaaaaaaa", "value": hex(100 * 10**18)}, []),
    ]))

    assert output.passed is False
    assert output.score < 50.0


@pytest.mark.asyncio
async def test_access_control_behavior_without_known_selector_passes():
    detector = AccessControlBypassDetector("access", {"threshold": 50.0, "min_trace_count": 2})

    output = await detector.process(_context([
        _trace({"to": PROXY, "input": "0xaaaaaaaa"}, []),
        _trace({"from": PROXY, "to": IMPLEMENTATION, "input": "0xbbbbbbbb", "callType": "delegatecall"}, [0]),
        _trace({"from": IMPLEMENTATION, "to": ADMIN_TARGET, "input": "0xcccccccc"}, [0, 0]),
        _trace({"from": IMPLEMENTATION, "to": PROXY, "input": "0xdddddddd"}, [0, 1]),
    ]))

    assert output.passed is True
    assert output.score >= 50.0
    assert "ACCESS_CONTROL_BEHAVIOR:DELEGATECALL" in output.labels
    assert "ACCESS_CONTROL_BEHAVIOR:PROXY_LIKE_MULTIHOP" in output.labels


@pytest.mark.asyncio
async def test_proxy_upgrade_selector_without_delegatecall_or_structure_does_not_pass():
    selector = next(iter(PROXY_UPGRADE_SIGNATURES))
    detector = AccessControlBypassDetector("access", {"threshold": 50.0, "min_trace_count": 1})

    output = await detector.process(_context([
        _trace({"to": PROXY, "input": selector + "00" * 32}, []),
    ]))

    assert output.passed is False
    assert output.score < 50.0
