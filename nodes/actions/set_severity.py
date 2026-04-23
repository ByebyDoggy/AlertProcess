from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from nodes.base import NodeRegistry
from nodes.actions.base import BaseAction, ActionInputMixin, ActionOutputMixin


VALID_SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN")


class SetSeverityAction(BaseAction):
    """
    设置严重级别动作 — 将执行上下文中的 final_severity 设置为指定值。
    """

    name: str = "set_severity_action"
    label: str = "设置严重级别"
    description: str = "设置告警的最终严重级别（CRITICAL/HIGH/MEDIUM/LOW），支持条件触发：always 始终设置、passed 仅通过时设置、not_passed 仅未通过时设置"
    icon: str = "\U0001f7e1"
    color: str = "#f43f5e"

    # ── Pydantic 配置模型 ──
    class ConfigModel(BaseModel):
        severity: str = Field(default="HIGH", description="要设置的严重级别")
        condition: str = Field(default="always", description="执行条件")

        @field_validator("severity")
        @classmethod
        def _valid_sev(cls, v):
            if v not in VALID_SEVERITIES:
                raise ValueError(f"severity must be one of {VALID_SEVERITIES}")
            return v

        @field_validator("condition")
        @classmethod
        def _valid_cond(cls, v):
            if v not in ("always", "passed", "not_passed"):
                raise ValueError("condition must be 'always', 'passed' or 'not_passed'")
            return v

    async def process(self, input: ActionInputMixin) -> ActionOutputMixin:
        context = input.context
        severity = self.config.get("severity", "HIGH")
        condition = self.config.get("condition", "always")

        upstream_passed = context.get("_upstream_passed", input.upstream_passed)

        should_execute = True
        if condition == "passed" and not upstream_passed:
            should_execute = False
        elif condition == "not_passed" and upstream_passed:
            should_execute = False

        if should_execute:
            context["final_severity"] = severity
            return ActionOutputMixin(
                score=input.upstream_score, passed=input.upstream_passed, severity=severity, labels=[],
                action_result={"action": "set_severity", "severity": severity, "executed": True},
            )
        return ActionOutputMixin(
            score=input.upstream_score, passed=input.upstream_passed, severity="UNKNOWN", labels=[],
            action_result={"action": "set_severity", "severity": severity, "executed": False, "reason": "condition not met"},
        )


NodeRegistry.register(SetSeverityAction)
