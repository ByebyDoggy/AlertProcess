"""设置严重级别动作 — 在执行上下文中设置告警严重级别"""

from __future__ import annotations

from typing import Any

from nodes.base import NodeRegistry
from nodes.actions.base import BaseAction


VALID_SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN")


class SetSeverityAction(BaseAction):
    """
    设置严重级别动作 — 将执行上下文中的 final_severity 设置为指定值。

    配置:
    - severity: 要设置的严重级别 (CRITICAL/HIGH/MEDIUM/LOW/UNKNOWN)
    - condition: 可选，"always"/"passed"/"not_passed"，默认 "always"
    """

    name: str = "set_severity_action"
    label: str = "设置严重级别"
    description: str = "设置告警的严重级别"
    icon: str = "\U0001f7e1"
    color: str = "#f43f5e"

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "severity": {
                    "type": "string",
                    "enum": list(VALID_SEVERITIES),
                    "default": "HIGH",
                    "description": "要设置的严重级别",
                },
                "condition": {
                    "type": "string",
                    "enum": ["always", "passed", "not_passed"],
                    "default": "always",
                    "description": "执行条件",
                },
            },
        }

    @classmethod
    def get_default_config(cls) -> dict[str, Any]:
        return {"severity": "HIGH", "condition": "always"}

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors = []
        sev = config.get("severity", "HIGH")
        if sev not in VALID_SEVERITIES:
            errors.append(f"severity must be one of {VALID_SEVERITIES}")
        cond = config.get("condition", "always")
        if cond not in ("always", "passed", "not_passed"):
            errors.append("condition must be 'always', 'passed' or 'not_passed'")
        return errors

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        severity = self.config.get("severity", "HIGH")
        condition = self.config.get("condition", "always")

        upstream_passed = context.get("_upstream_passed", True)

        should_execute = True
        if condition == "passed" and not upstream_passed:
            should_execute = False
        elif condition == "not_passed" and upstream_passed:
            should_execute = False

        if should_execute:
            context["final_severity"] = severity
            return {"action": "set_severity", "severity": severity, "executed": True}
        return {"action": "set_severity", "severity": severity, "executed": False, "reason": "condition not met"}


NodeRegistry.register(SetSeverityAction)
