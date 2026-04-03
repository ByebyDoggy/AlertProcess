"""添加标签动作 — 在执行上下文中添加标签"""

from __future__ import annotations

from typing import Any

from nodes.base import NodeRegistry
from nodes.actions.base import BaseAction


class AddTagAction(BaseAction):
    """
    添加标签动作 — 向执行上下文中的标签列表添加指定标签。

    配置:
    - tags: 要添加的标签列表
    - deduplicate: 是否去重（默认 True）
    """

    name: str = "add_tag_action"
    label: str = "添加标签"
    description: str = "向告警添加自定义标签"
    icon: str = "\U0001f3f7"
    color: str = "#22c55e"

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": "要添加的标签列表",
                },
                "deduplicate": {
                    "type": "boolean",
                    "default": True,
                    "description": "是否去重",
                },
            },
        }

    @classmethod
    def get_default_config(cls) -> dict[str, Any]:
        return {"tags": [], "deduplicate": True}

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors = []
        tags = config.get("tags", [])
        if not isinstance(tags, list):
            errors.append("tags must be a list of strings")
        elif any(not isinstance(t, str) for t in tags):
            errors.append("tags must contain only strings")
        return errors

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        tags = self.config.get("tags", [])
        dedup = self.config.get("deduplicate", True)

        existing = context.get("final_labels", [])

        if dedup:
            combined = list(dict.fromkeys(existing + tags))
        else:
            combined = existing + tags

        context["final_labels"] = combined

        return {
            "action": "add_tag",
            "tags_added": tags,
            "total_tags": len(combined),
            "deduplicated": dedup,
        }


NodeRegistry.register(AddTagAction)
