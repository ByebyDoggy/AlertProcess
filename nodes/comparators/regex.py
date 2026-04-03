"""正则匹配比较器 — 对 context 字段进行正则匹配"""

from __future__ import annotations

import re
from typing import Any

from nodes.base import NodeRegistry, NodeOutput
from nodes.comparators.base import BaseComparator


class RegexComparator(BaseComparator):
    """
    正则匹配比较器 — 对上游 context 中的指定字段进行正则匹配。

    配置:
    - field: 要匹配的 context 字段名
    - pattern: 正则表达式
    - match_mode: 匹配模式 - "search"(默认), "fullmatch", "match"
    """

    name: str = "regex_comparator"
    label: str = "正则匹配"
    description: str = "对 context 字段进行正则表达式匹配"
    icon: str = "\U0001f50d"
    color: str = "#a855f7"

    MATCH_MODES = ("search", "fullmatch", "match")

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "field": {
                    "type": "string",
                    "default": "",
                    "description": "要匹配的 context 字段名（支持嵌套，如 detection.detected_issues）",
                },
                "pattern": {
                    "type": "string",
                    "default": "",
                    "description": "正则表达式",
                },
                "match_mode": {
                    "type": "string",
                    "enum": ["search", "fullmatch", "match"],
                    "default": "search",
                    "description": "匹配模式: search=搜索, fullmatch=完全匹配, match=头部匹配",
                },
            },
        }

    @classmethod
    def get_default_config(cls) -> dict[str, Any]:
        return {"field": "", "pattern": "", "match_mode": "search"}

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors = []
        if not config.get("field"):
            errors.append("field is required")
        if not config.get("pattern"):
            errors.append("pattern is required")
        else:
            try:
                re.compile(config["pattern"])
            except re.error as e:
                errors.append(f"Invalid regex pattern: {e}")
        mode = config.get("match_mode", "search")
        if mode not in self.MATCH_MODES:
            errors.append(f"match_mode must be one of {self.MATCH_MODES}")
        return errors

    @staticmethod
    def _get_nested_value(data: dict, path: str):
        """从嵌套字典中按点分路径获取值"""
        keys = path.split(".")
        current = data
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
            else:
                return None
        return current

    async def compare(self, scores: list[float]) -> tuple[bool, dict[str, Any]]:
        # RegexComparator 主要使用 context 中的字段，score 不直接参与比较
        # 但仍返回 (result, details) 符合基类契约
        # 实际匹配在 execute 重写中完成
        return False, {"comparator_type": "regex", "note": "context matching done in execute override"}

    async def execute(
        self,
        context: dict[str, Any],
        inputs: dict[str, list[NodeOutput]],
    ) -> NodeOutput:
        """重写 execute 以支持 context 字段正则匹配"""
        field = self.config.get("field", "")
        pattern = self.config.get("pattern", "")
        mode = self.config.get("match_mode", "search")

        # 无配置时直接不通过
        if not field or not pattern:
            return NodeOutput(
                node_id=self.node_id,
                node_type=self.category.value,
                score=0.0,
                passed=False,
                context={"comparator_type": "regex", "result": False, "error": "field or pattern not configured"},
            )

        # 收集上游 context 进行合并
        merged = dict(context)
        for port_key in sorted(inputs.keys()):
            for inp in inputs[port_key]:
                merged = {**merged, **inp.context}

        # 获取字段值
        value = self._get_nested_value(merged, field)

        # 编译正则
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return NodeOutput(
                node_id=self.node_id,
                node_type=self.category.value,
                score=0.0,
                passed=False,
                context={"comparator_type": "regex", "result": False, "error": f"regex error: {e}"},
            )

        # 字段值可能是列表（如 detected_issues），逐项匹配
        if isinstance(value, list):
            matched_items = [str(v) for v in value if regex.search(str(v))]
            result = len(matched_items) > 0
        else:
            str_value = str(value) if value is not None else ""
            if mode == "fullmatch":
                result = regex.fullmatch(str_value) is not None
            elif mode == "match":
                result = regex.match(str_value) is not None
            else:
                result = regex.search(str_value) is not None
            matched_items = [str_value] if result else []

        score_val = max(0.0, min(1.0, len(matched_items) / max(1, len(matched_items)))) * 100.0 if result else 0.0

        details: dict[str, Any] = {
            "comparator_type": "regex",
            "field": field,
            "pattern": pattern,
            "match_mode": mode,
            "field_value": value,
            "matched_items": matched_items,
            "result": result,
        }

        return NodeOutput(
            node_id=self.node_id,
            node_type=self.category.value,
            score=100.0 if result else 0.0,
            passed=result,
            context=details,
        )


NodeRegistry.register(RegexComparator)
