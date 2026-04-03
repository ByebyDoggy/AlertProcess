"""tests/nodes/test_comparators/test_regex.py — RegexComparator 测试"""

import pytest

from nodes.comparators.regex import RegexComparator
from nodes.base import NodeOutput, NodeCategory


def _make_inputs(context: dict, score: float = 50):
    out = NodeOutput(node_id="d1", node_type="detection", score=score, passed=True, context=context)
    return {"input_0": [out]}


class TestRegexComparator:

    @pytest.mark.asyncio
    async def test_search_match(self):
        """search 模式匹配成功"""
        comp = RegexComparator(node_id="c1", config={
            "field": "detection.detected_issues",
            "pattern": "FLASH_LOAN",
            "match_mode": "search",
        })
        ctx = {"detection": {"detected_issues": ["FLASH_LOAN_PROTOCOL:Aave"]}}
        result = await comp.execute({}, _make_inputs(ctx))
        assert result.passed is True
        assert result.score == 100.0

    @pytest.mark.asyncio
    async def test_search_no_match(self):
        """search 模式不匹配"""
        comp = RegexComparator(node_id="c1", config={
            "field": "detection.detected_issues",
            "pattern": "FLASH_LOAN",
            "match_mode": "search",
        })
        ctx = {"detection": {"detected_issues": ["NORMAL_TRANSACTION"]}}
        result = await comp.execute({}, _make_inputs(ctx))
        assert result.passed is False
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_fullmatch(self):
        """fullmatch 模式"""
        comp = RegexComparator(node_id="c1", config={
            "field": "detection.method",
            "pattern": r"approve",
            "match_mode": "fullmatch",
        })
        ctx = {"detection": {"method": "approve"}}
        result = await comp.execute({}, _make_inputs(ctx))
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_fullmatch_partial_fails(self):
        """fullmatch 模式部分匹配不通过"""
        comp = RegexComparator(node_id="c1", config={
            "field": "detection.method",
            "pattern": r"approve",
            "match_mode": "fullmatch",
        })
        ctx = {"detection": {"method": "approve_and_transfer"}}
        result = await comp.execute({}, _make_inputs(ctx))
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_match_mode(self):
        """match 模式（头部匹配）"""
        comp = RegexComparator(node_id="c1", config={
            "field": "detection.method",
            "pattern": r"approve",
            "match_mode": "match",
        })
        ctx = {"detection": {"method": "approve_and_transfer"}}
        result = await comp.execute({}, _make_inputs(ctx))
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_nested_field(self):
        """嵌套字段路径"""
        comp = RegexComparator(node_id="c1", config={
            "field": "detection.details.sub_field",
            "pattern": "dangerous",
            "match_mode": "search",
        })
        ctx = {"detection": {"details": {"sub_field": "dangerous_operation"}}}
        result = await comp.execute({}, _make_inputs(ctx))
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_list_field_multiple_matches(self):
        """列表字段中多项匹配"""
        comp = RegexComparator(node_id="c1", config={
            "field": "detection.detected_issues",
            "pattern": r".*LOAN.*",
            "match_mode": "search",
        })
        ctx = {"detection": {"detected_issues": ["FLASH_LOAN", "LARGE_LOAN", "NORMAL"]}}
        result = await comp.execute({}, _make_inputs(ctx))
        assert result.passed is True
        assert len(result.context["matched_items"]) == 2

    @pytest.mark.asyncio
    async def test_no_field_configured(self):
        """未配置 field → 不通过"""
        comp = RegexComparator(node_id="c1", config={"pattern": "test"})
        result = await comp.execute({}, _make_inputs({}))
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_no_pattern_configured(self):
        """未配置 pattern → 不通过"""
        comp = RegexComparator(node_id="c1", config={"field": "test"})
        result = await comp.execute({}, _make_inputs({}))
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_field_not_found(self):
        """字段不存在 → 不通过"""
        comp = RegexComparator(node_id="c1", config={
            "field": "nonexistent.field",
            "pattern": "test",
        })
        result = await comp.execute({}, _make_inputs({}))
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_invalid_regex(self):
        """无效正则 → 不通过"""
        comp = RegexComparator(node_id="c1", config={
            "field": "test",
            "pattern": "[invalid",
        })
        result = await comp.execute({}, _make_inputs({}))
        assert result.passed is False
        assert "regex error" in result.context.get("error", "")

    @pytest.mark.asyncio
    async def test_context_merge(self):
        """应合并上游 context"""
        comp = RegexComparator(node_id="c1", config={
            "field": "detection.detected_issues",
            "pattern": "FOUND",
            "match_mode": "search",
        })
        ctx = {"detection": {"detected_issues": ["FOUND_IT"]}}
        result = await comp.execute({}, _make_inputs(ctx))
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_null_value_converted_to_string(self):
        """None 值转为空字符串"""
        comp = RegexComparator(node_id="c1", config={
            "field": "some_field",
            "pattern": "anything",
        })
        result = await comp.execute({}, _make_inputs({"some_field": None}))
        assert result.passed is False

    def test_validate_config_ok(self):
        comp = RegexComparator()
        assert comp.validate_config({"field": "x", "pattern": ".*"}) == []

    def test_validate_config_no_field(self):
        comp = RegexComparator()
        errors = comp.validate_config({"pattern": ".*"})
        assert any("field" in e for e in errors)

    def test_validate_config_no_pattern(self):
        comp = RegexComparator()
        errors = comp.validate_config({"field": "x"})
        assert any("pattern" in e for e in errors)

    def test_validate_config_invalid_mode(self):
        comp = RegexComparator()
        errors = comp.validate_config({"field": "x", "pattern": ".*", "match_mode": "invalid"})
        assert any("match_mode" in e for e in errors)

    def test_validate_config_invalid_regex(self):
        comp = RegexComparator()
        errors = comp.validate_config({"field": "x", "pattern": "[invalid"})
        assert any("regex" in e.lower() for e in errors)

    def test_category(self):
        assert RegexComparator.category == NodeCategory.COMPARISON

    def test_registered(self):
        from nodes.base import NodeRegistry
        NodeRegistry.register(RegexComparator)
        assert NodeRegistry.get("regex_comparator") is RegexComparator
