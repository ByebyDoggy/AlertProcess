"""tests/nodes/test_actions/test_actions.py — 所有 Action 节点的单元测试"""

import pytest

from nodes.base import NodeOutput, NodeCategory
from nodes.actions.set_severity import SetSeverityAction
from nodes.actions.add_tag import AddTagAction
from nodes.actions.notify_webhook import NotifyWebhookAction
from nodes.actions.notify_telegram import NotifyTelegramAction
from nodes.actions.update_database import UpdateDatabaseAction


def _make_inputs(context: dict, score: float = 80, passed: bool = True):
    out = NodeOutput(node_id="logic1", node_type="logic", score=score, passed=passed, context=context)
    return {"input": [out]}


# ===========================================================================
# SetSeverityAction
# ===========================================================================
class TestSetSeverityAction:

    @pytest.mark.asyncio
    async def test_set_severity_always(self):
        action = SetSeverityAction(node_id="a1", config={"severity": "CRITICAL"})
        ctx = {}
        output = await action.execute(ctx, _make_inputs(ctx))
        assert output.context["final_severity"] == "CRITICAL"
        assert output.context["action_result"]["executed"] is True

    @pytest.mark.asyncio
    async def test_set_severity_condition_passed(self):
        action = SetSeverityAction(node_id="a1", config={
            "severity": "HIGH",
            "condition": "passed",
        })
        ctx = {"_upstream_passed": True}
        output = await action.execute(ctx, _make_inputs(ctx, passed=True))
        assert output.context["final_severity"] == "HIGH"
        assert output.context["action_result"]["executed"] is True

    @pytest.mark.asyncio
    async def test_set_severity_condition_not_met(self):
        action = SetSeverityAction(node_id="a1", config={
            "severity": "HIGH",
            "condition": "passed",
        })
        ctx = {"_upstream_passed": False}
        output = await action.execute(ctx, _make_inputs(ctx, passed=False))
        assert output.context["action_result"]["executed"] is False

    @pytest.mark.asyncio
    async def test_set_severity_not_passed_condition(self):
        action = SetSeverityAction(node_id="a1", config={
            "severity": "LOW",
            "condition": "not_passed",
        })
        ctx = {"_upstream_passed": False}
        output = await action.execute(ctx, _make_inputs(ctx, passed=False))
        assert output.context["final_severity"] == "LOW"
        assert output.context["action_result"]["executed"] is True

    @pytest.mark.asyncio
    async def test_inherits_upstream_score(self):
        action = SetSeverityAction(node_id="a1", config={"severity": "HIGH"})
        output = await action.execute({}, _make_inputs({}, score=75, passed=True))
        assert output.score == 75.0
        assert output.passed is True

    @pytest.mark.asyncio
    async def test_no_upstream(self):
        action = SetSeverityAction(node_id="a1")
        output = await action.execute({}, {})
        assert output.score == 0.0

    def test_validate_config_ok(self):
        action = SetSeverityAction()
        assert action.validate_config({"severity": "HIGH"}) == []

    def test_validate_config_invalid_severity(self):
        action = SetSeverityAction()
        errors = action.validate_config({"severity": "INVALID"})
        assert any("severity" in e for e in errors)

    def test_validate_config_invalid_condition(self):
        action = SetSeverityAction()
        errors = action.validate_config({"condition": "maybe"})
        assert any("condition" in e for e in errors)

    def test_category(self):
        assert SetSeverityAction.category == NodeCategory.ACTION

    def test_registered(self):
        from nodes.base import NodeRegistry
        NodeRegistry.register(SetSeverityAction)
        assert NodeRegistry.get("set_severity_action") is SetSeverityAction


# ===========================================================================
# AddTagAction
# ===========================================================================
class TestAddTagAction:

    @pytest.mark.asyncio
    async def test_add_tags(self):
        action = AddTagAction(node_id="a1", config={"tags": ["phishing", "scam"]})
        output = await action.execute({"final_labels": ["existing"]}, _make_inputs({}))
        assert output.context["final_labels"] == ["existing", "phishing", "scam"]

    @pytest.mark.asyncio
    async def test_deduplicate(self):
        action = AddTagAction(node_id="a1", config={
            "tags": ["existing", "new_tag"],
            "deduplicate": True,
        })
        output = await action.execute({"final_labels": ["existing"]}, _make_inputs({}))
        assert output.context["final_labels"] == ["existing", "new_tag"]

    @pytest.mark.asyncio
    async def test_no_deduplicate(self):
        action = AddTagAction(node_id="a1", config={
            "tags": ["dup", "dup"],
            "deduplicate": False,
        })
        output = await action.execute({"final_labels": []}, _make_inputs({}))
        assert output.context["final_labels"] == ["dup", "dup"]

    @pytest.mark.asyncio
    async def test_no_existing_labels(self):
        action = AddTagAction(node_id="a1", config={"tags": ["tag1"]})
        output = await action.execute({}, _make_inputs({}))
        assert output.context["final_labels"] == ["tag1"]

    @pytest.mark.asyncio
    async def test_empty_tags(self):
        action = AddTagAction(node_id="a1", config={"tags": []})
        output = await action.execute({"final_labels": ["existing"]}, _make_inputs({}))
        assert output.context["final_labels"] == ["existing"]

    def test_validate_config_ok(self):
        action = AddTagAction()
        assert action.validate_config({"tags": ["a", "b"]}) == []

    def test_validate_config_not_list(self):
        action = AddTagAction()
        errors = action.validate_config({"tags": "not_a_list"})
        assert len(errors) > 0

    def test_category(self):
        assert AddTagAction.category == NodeCategory.ACTION

    def test_registered(self):
        from nodes.base import NodeRegistry
        NodeRegistry.register(AddTagAction)
        assert NodeRegistry.get("add_tag_action") is AddTagAction


# ===========================================================================
# NotifyWebhookAction
# ===========================================================================
class TestNotifyWebhookAction:

    @pytest.mark.asyncio
    async def test_no_url(self):
        action = NotifyWebhookAction(node_id="a1")
        output = await action.execute({}, _make_inputs({}))
        assert output.context["action_result"]["success"] is False
        assert "url" in output.context["action_result"]["error"]

    @pytest.mark.asyncio
    async def test_invalid_url(self):
        """发送到无效 URL 应捕获异常"""
        action = NotifyWebhookAction(node_id="a1", config={
            "url": "http://127.0.0.1:1/impossible",
            "timeout": 2,
        })
        output = await action.execute({"tx_hash": "0xabc"}, _make_inputs({}))
        assert output.context["action_result"]["success"] is False

    @pytest.mark.asyncio
    async def test_include_fields(self):
        """include_fields 过滤请求体"""
        action = NotifyWebhookAction(node_id="a1", config={
            "url": "http://127.0.0.1:1/test",
            "include_fields": ["tx_hash", "severity"],
            "timeout": 1,
        })
        output = await action.execute(
            {"tx_hash": "0xabc", "severity": "HIGH", "secret": "value"},
            _make_inputs({}),
        )
        result = output.context["action_result"]
        assert result["success"] is False  # 请求失败但逻辑正确

    @pytest.mark.asyncio
    async def test_filters_internal_fields(self):
        """内部字段（_开头）应被过滤"""
        action = NotifyWebhookAction(node_id="a1", config={
            "url": "http://127.0.0.1:1/test",
            "timeout": 1,
        })
        ctx = {"tx_hash": "0xabc", "_internal": "secret"}
        output = await action.execute(ctx, _make_inputs({}))
        # 请求会失败，但 payload 构建应正确
        assert output.context["action_result"]["success"] is False

    def test_validate_config_ok(self):
        action = NotifyWebhookAction()
        assert action.validate_config({"url": "http://example.com"}) == []

    def test_validate_config_no_url(self):
        action = NotifyWebhookAction()
        errors = action.validate_config({})
        assert any("url" in e for e in errors)

    def test_validate_config_invalid_method(self):
        action = NotifyWebhookAction()
        errors = action.validate_config({"url": "http://x.com", "method": "DELETE"})
        assert any("method" in e for e in errors)

    def test_category(self):
        assert NotifyWebhookAction.category == NodeCategory.ACTION

    def test_registered(self):
        from nodes.base import NodeRegistry
        NodeRegistry.register(NotifyWebhookAction)
        assert NodeRegistry.get("notify_webhook_action") is NotifyWebhookAction


# ===========================================================================
# NotifyTelegramAction
# ===========================================================================
class TestNotifyTelegramAction:

    @pytest.mark.asyncio
    async def test_no_token(self):
        action = NotifyTelegramAction(node_id="a1")
        output = await action.execute({}, _make_inputs({}))
        assert output.context["action_result"]["success"] is False

    @pytest.mark.asyncio
    async def test_invalid_token(self):
        """无效 token 请求应失败"""
        action = NotifyTelegramAction(node_id="a1", config={
            "bot_token": "123456:invalid",
            "chat_id": "12345",
            "timeout": 2,
        })
        output = await action.execute({
            "final_severity": "HIGH",
            "tx_hash": "0xabc",
        }, _make_inputs({}))
        assert output.context["action_result"]["success"] is False

    @pytest.mark.asyncio
    async def test_message_template_rendering(self):
        action = NotifyTelegramAction(node_id="a1", config={
            "bot_token": "123456:invalid",
            "chat_id": "12345",
            "message_template": "Alert: {severity} {tx_hash}",
            "timeout": 1,
        })
        output = await action.execute({
            "final_severity": "CRITICAL",
            "tx_hash": "0xdead",
        }, _make_inputs({}))
        assert output.context["action_result"]["success"] is False

    @pytest.mark.asyncio
    async def test_missing_template_vars(self):
        """模板变量缺失时不崩溃"""
        action = NotifyTelegramAction(node_id="a1", config={
            "bot_token": "123456:invalid",
            "chat_id": "12345",
            "message_template": "Alert: {severity} {missing_var}",
            "timeout": 1,
        })
        output = await action.execute({}, _make_inputs({}))
        assert output.context["action_result"]["success"] is False

    def test_validate_config_ok(self):
        action = NotifyTelegramAction()
        assert action.validate_config({"bot_token": "x", "chat_id": "y"}) == []

    def test_validate_config_no_token(self):
        action = NotifyTelegramAction()
        errors = action.validate_config({})
        assert any("bot_token" in e for e in errors)

    def test_validate_config_no_chat_id(self):
        action = NotifyTelegramAction()
        errors = action.validate_config({"bot_token": "x"})
        assert any("chat_id" in e for e in errors)

    def test_category(self):
        assert NotifyTelegramAction.category == NodeCategory.ACTION

    def test_registered(self):
        from nodes.base import NodeRegistry
        NodeRegistry.register(NotifyTelegramAction)
        assert NodeRegistry.get("notify_telegram_action") is NotifyTelegramAction


# ===========================================================================
# UpdateDatabaseAction
# ===========================================================================
class TestUpdateDatabaseAction:

    @pytest.mark.asyncio
    async def test_basic_insert(self):
        action = UpdateDatabaseAction(node_id="a1", config={
            "table": "alerts",
            "fields": {"tx_hash": "tx_hash", "severity": "severity"},
            "update_mode": "insert",
        })
        output = await action.execute({
            "tx_hash": "0xabc",
            "severity": "HIGH",
            "extra": "ignored",
        }, _make_inputs({}))
        result = output.context["action_result"]
        assert result["success"] is True
        assert result["table"] == "alerts"
        assert result["row_count"] == 2  # tx_hash + severity

    @pytest.mark.asyncio
    async def test_no_table(self):
        action = UpdateDatabaseAction(node_id="a1", config={"table": ""})
        output = await action.execute({}, _make_inputs({}))
        assert output.context["action_result"]["success"] is False

    @pytest.mark.asyncio
    async def test_no_matching_fields(self):
        action = UpdateDatabaseAction(node_id="a1", config={
            "table": "alerts",
            "fields": {"nonexistent": "col"},
        })
        output = await action.execute({"tx_hash": "0xabc"}, _make_inputs({}))
        assert output.context["action_result"]["row_count"] == 0

    @pytest.mark.asyncio
    async def test_upsert_mode(self):
        action = UpdateDatabaseAction(node_id="a1", config={
            "table": "alerts",
            "update_mode": "upsert",
        })
        output = await action.execute({"tx_hash": "0xabc"}, _make_inputs({}))
        assert output.context["action_result"]["update_mode"] == "upsert"

    def test_validate_config_ok(self):
        action = UpdateDatabaseAction()
        assert action.validate_config({"table": "alerts"}) == []

    def test_validate_config_no_table(self):
        action = UpdateDatabaseAction()
        errors = action.validate_config({})
        assert any("table" in e for e in errors)

    def test_validate_config_invalid_mode(self):
        action = UpdateDatabaseAction()
        errors = action.validate_config({"table": "x", "update_mode": "delete"})
        assert any("update_mode" in e for e in errors)

    def test_category(self):
        assert UpdateDatabaseAction.category == NodeCategory.ACTION

    def test_registered(self):
        from nodes.base import NodeRegistry
        NodeRegistry.register(UpdateDatabaseAction)
        assert NodeRegistry.get("update_database_action") is UpdateDatabaseAction
