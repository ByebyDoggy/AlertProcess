from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from nodes.base import NodeRegistry
from nodes.actions.base import BaseAction, ActionInputMixin, ActionOutputMixin


class AddTagAction(BaseAction):
    """
    添加标签动作 — 向执行上下文中的标签列表添加指定标签。

    配置:
    - tags: 要添加的标签列表
    - deduplicate: 是否去重（默认 True）
    """

    name: str = "add_tag_action"
    label: str = "添加标签"
    description: str = "向告警执行上下文中添加自定义标签（如 phishing、flash_loan），支持去重合并。标签会传递给下游动作节点用于通知或持久化"
    icon: str = "\U0001f3f7"
    color: str = "#22c55e"

    # ── Pydantic 配置模型 ──
    class ConfigModel(BaseModel):
        tags: list[str] = Field(default=[], description="要添加的标签列表")
        deduplicate: bool = Field(default=True, description="是否去重")

        @field_validator("tags")
        @classmethod
        def _valid_tags(cls, v):
            if not isinstance(v, list) or any(not isinstance(t, str) for t in v):
                raise ValueError("tags must be a list of strings")
            return v

    async def process(self, input: ActionInputMixin) -> ActionOutputMixin:
        context = input.context
        tags = self.config.get("tags", [])
        dedup = self.config.get("deduplicate", True)

        existing = context.get("final_labels", [])

        if dedup:
            combined = list(dict.fromkeys(existing + tags))
        else:
            combined = existing + tags

        context["final_labels"] = combined

        return ActionOutputMixin(
            score=input.upstream_score, passed=input.upstream_passed, severity="UNKNOWN", labels=combined,
            action_result={
                "action": "add_tag",
                "tags_added": tags,
                "total_tags": len(combined),
                "deduplicated": dedup,
            },
        )


NodeRegistry.register(AddTagAction)
