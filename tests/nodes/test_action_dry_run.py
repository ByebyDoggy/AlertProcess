from __future__ import annotations

import pytest

from nodes.actions.base import ActionInputMixin, ActionOutputMixin, BaseAction
from nodes.base import NodeOutput


class SideEffectAction(BaseAction):
    name = "side_effect_action"
    label = "Side Effect Action"
    icon = ""
    color = ""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.calls = 0

    async def process(self, input: ActionInputMixin) -> ActionOutputMixin:
        self.calls += 1
        input.context["side_effect"] = True
        return ActionOutputMixin(
            score=input.upstream_score,
            passed=input.upstream_passed,
            severity="HIGH",
            labels=["sent"],
            action_result={"sent": True},
        )


@pytest.mark.asyncio
async def test_base_action_dry_run_does_not_call_process():
    action = SideEffectAction(node_id="a1")
    upstream = NodeOutput(
        node_id="d1",
        node_type="detection",
        score=70.0,
        passed=True,
        severity="HIGH",
        labels=["risk"],
        context={"tx_hash": "0x123"},
    )

    output = await action.execute({"__dry_run__": True}, {"input": [upstream]})

    assert action.calls == 0
    assert output.score == 70.0
    assert output.passed is True
    assert output.severity == "HIGH"
    assert output.labels == ["risk"]
    assert output.context["action_result"] == {"dry_run": True, "simulated": True, "skipped": True}
    assert "side_effect" not in output.context
