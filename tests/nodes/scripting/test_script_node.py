import pytest

from nodes.base import NodeOutput
from nodes.scripting.script_node import ScriptNode


@pytest.mark.asyncio
async def test_script_node_reads_namespace_outputs():
    node = ScriptNode(
        node_id="script",
        config={
            "script": """
result = all(passed)
score = max(scores) if scores else 0
labels = ["SCRIPT_MATCH"]
ctx["risk_reason"] = "script_match"
""",
            "timeout": 5,
        },
    )
    upstream = NodeOutput(node_id="detector", node_type="detection", score=80, passed=True)

    output = await node.execute({}, {"primary": [upstream]})

    assert output.passed is True
    assert output.score == 80
    assert output.labels == ["SCRIPT_MATCH"]
    assert output.context["risk_reason"] == "script_match"
    assert output.context["_custom_context"] == {"risk_reason": "script_match"}


@pytest.mark.asyncio
async def test_script_node_supports_explicit_result_dict():
    node = ScriptNode(
        node_id="script",
        config={
            "script": """
result = {
    "result": False,
    "score": 25,
    "labels": "LOW_CONFIDENCE",
    "ctx_output": {"reason": "manual_override"},
}
""",
            "timeout": 5,
        },
    )

    output = await node.execute({}, {"primary": []})

    assert output.passed is False
    assert output.score == 25
    assert output.labels == ["LOW_CONFIDENCE"]
    assert output.context["reason"] == "manual_override"


@pytest.mark.asyncio
async def test_script_node_injects_script_context_helpers():
    node = ScriptNode(
        node_id="script",
        config={
            "script": """
transfers = context.get_transfers("0xtoken")
result = len(transfers) == 1
score = transfers[0]["amount"] if result else 0
""",
            "timeout": 5,
        },
    )

    output = await node.execute(
        {
            "chain_id": 1,
            "tx_hash": "0xabc",
            "parsed_transfers": [
                {"token_address": "0xToken", "from_address": "0xa", "to_address": "0xb", "amount": 70},
            ],
        },
        {"primary": []},
    )

    assert output.passed is True
    assert output.score == 70


@pytest.mark.asyncio
async def test_script_node_returns_error_on_security_violation():
    node = ScriptNode(
        node_id="script",
        config={"script": "open('x.txt')", "timeout": 5},
    )

    output = await node.execute({}, {"primary": []})

    assert output.passed is False
    assert output.score == 0
    assert "Security check failed" in output.context["error"]
