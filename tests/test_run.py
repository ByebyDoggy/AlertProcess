"""
Unit tests for Rule Chain Test-Run Endpoint
"""
import pytest
from fastapi.testclient import TestClient

from main import app
from database.models import SessionLocal, KnowledgeBaseDB, RuleChainDB


client = TestClient(app)


def get_auth_headers():
    return {"X-API-Key": "default_secret_key_change_in_production"}


def cleanup():
    db = SessionLocal()
    try:
        db.query(KnowledgeBaseDB).filter(
            KnowledgeBaseDB.title.like("test_%")
        ).delete()
        db.query(RuleChainDB).filter(
            RuleChainDB.name.like("test_%")
        ).delete()
        db.commit()
    finally:
        db.close()


# 一个简单但有效的规则链：AlertTrigger -> GasPriceDetector
SIMPLE_CHAIN = {
    "name": "test_gas_chain",
    "description": "Test chain with gas price detector",
    "enabled": True,
    "nodes": [
        {
            "id": "trigger_1",
            "type": "alert_trigger",
            "label": "告警触发器",
            "position": {"x": 100, "y": 100},
        },
        {
            "id": "gas_1",
            "type": "gas_price_detector",
            "label": "Gas价格检测",
            "position": {"x": 300, "y": 100},
            "config": {
                "threshold": 50,
                "high_gas_threshold_usd": 100.0,
                "extreme_gas_threshold_usd": 500.0,
                "chain_id_to_native_token_price": {1: 2000.0},
            },
        },
    ],
    "edges": [
        {"id": "e1", "source": "trigger_1", "source_port": "output", "target": "gas_1", "target_port": "input"},
    ],
}

# 闪电贷检测链
FLASH_LOAN_CHAIN = {
    "name": "test_flash_chain",
    "description": "Test chain with flash loan detector",
    "enabled": True,
    "nodes": [
        {
            "id": "trigger_1",
            "type": "alert_trigger",
            "label": "告警触发器",
            "position": {"x": 100, "y": 100},
        },
        {
            "id": "fl_1",
            "type": "flash_loan_detector",
            "label": "闪电贷检测",
            "position": {"x": 300, "y": 100},
            "config": {
                "chain_id_to_native_token_price": {1: 2000.0},
            },
        },
    ],
    "edges": [
        {"id": "e1", "source": "trigger_1", "source_port": "output", "target": "fl_1", "target_port": "input"},
    ],
}

# 带 Action 的链（用于测试 dry-run 模式）
CHAIN_WITH_ACTION = {
    "name": "test_action_chain",
    "description": "Test chain with action node for dry-run",
    "enabled": True,
    "nodes": [
        {
            "id": "trigger_1",
            "type": "alert_trigger",
            "label": "告警触发器",
            "position": {"x": 100, "y": 100},
        },
        {
            "id": "fl_1",
            "type": "flash_loan_detector",
            "label": "闪电贷检测",
            "position": {"x": 300, "y": 100},
            "config": {
                "chain_id_to_native_token_price": {1: 2000.0},
            },
        },
        {
            "id": "action_1",
            "type": "set_severity_action",
            "label": "设置严重级别",
            "position": {"x": 500, "y": 100},
            "config": {"condition": "passed", "severity": "CRITICAL"},
        },
    ],
    "edges": [
        {"id": "e1", "source": "trigger_1", "source_port": "output", "target": "fl_1", "target_port": "input"},
        {"id": "e2", "source": "fl_1", "source_port": "output", "target": "action_1", "target_port": "input"},
    ],
}


class TestTestRunEndpoint:

    def setup_method(self):
        cleanup()

    def teardown_method(self):
        cleanup()

    def _create_chain(self, chain_data: dict) -> str:
        resp = client.post("/rule-chain/", headers=get_auth_headers(), json=chain_data)
        return resp.json()["id"]

    def _create_sample(self, overrides: dict = None) -> str:
        sample = {
            "title": "test_flash_sample",
            "description": "Test flash loan",
            "category": "flash_loan",
            "tags": ["闪电贷"],
            "chain_id": 1,
            "tx_hash": "0xtestfl",
            "alert_data": {
                "chain_id": 1,
                "tx_hash": "0xtestfl",
                "to_address": "0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9",
                "input_data": "0x0906f8c8",
                "value": "197000000000000000000",
                "gas_price": 35000000000,
                "gas_used": 650000,
            },
            "expected_severity": "CRITICAL",
            "expected_labels": ["LARGE_FLASH_LOAN_ATTACK"],
            "expected_min_score": 80,
        }
        if overrides:
            sample.update(overrides)
        resp = client.post("/knowledge-base/", headers=get_auth_headers(), json=sample)
        return resp.json()["id"]

    def test_test_run_without_auth(self):
        chain_id = self._create_chain(SIMPLE_CHAIN)
        resp = client.post(f"/rule-chain/{chain_id}/test-run", json={"alert_data": {}})
        assert resp.status_code == 401

    def test_test_run_chain_not_found(self):
        resp = client.post(
            "/rule-chain/nonexistent/test-run",
            headers=get_auth_headers(),
            json={"alert_data": {"chain_id": 1}},
        )
        assert resp.status_code == 404

    def test_test_run_with_custom_alert_data(self):
        chain_id = self._create_chain(SIMPLE_CHAIN)

        resp = client.post(
            f"/rule-chain/{chain_id}/test-run",
            headers=get_auth_headers(),
            json={
                "alert_data": {
                    "chain_id": 1,
                    "tx_hash": "0xabc",
                    "gas_price": 800000000000,  # 800 Gwei, very high
                    "gas_used": 300000,
                    "to_address": "0xdef",
                }
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert len(data["results"]) == 1

        result = data["results"][0]
        assert result["success"] is True
        assert result["chain_name"] == "test_gas_chain"
        assert result["final_score"] > 0
        assert len(result["node_results"]) > 0
        assert result["duration_ms"] >= 0

    def test_test_run_with_low_gas(self):
        chain_id = self._create_chain(SIMPLE_CHAIN)

        resp = client.post(
            f"/rule-chain/{chain_id}/test-run",
            headers=get_auth_headers(),
            json={
                "alert_data": {
                    "chain_id": 1,
                    "tx_hash": "0xlowgas",
                    "gas_price": 15000000000,  # 15 Gwei, normal
                    "gas_used": 21000,
                    "to_address": "0xabc",
                }
            },
        )
        assert resp.status_code == 200
        result = resp.json()["results"][0]
        assert result["success"] is True
        # Low gas should produce a low score
        assert result["final_score"] < 50

    def test_test_run_with_flash_loan_sample(self):
        chain_id = self._create_chain(FLASH_LOAN_CHAIN)
        sample_id = self._create_sample()

        resp = client.post(
            f"/rule-chain/{chain_id}/test-run",
            headers=get_auth_headers(),
            json={"sample_ids": [sample_id]},
        )
        assert resp.status_code == 200
        result = resp.json()["results"][0]
        assert result["success"] is True
        assert result["sample_id"] == sample_id
        assert result["sample_title"] == "test_flash_sample"
        assert result["final_score"] >= 80  # Flash loan to Aave + large value = 95
        assert result["final_severity"] in ("CRITICAL", "HIGH")

    def test_test_run_dry_mode_action_simulated(self):
        """验证 dry-run 模式下 Action 节点仅模拟不实际执行"""
        chain_id = self._create_chain(CHAIN_WITH_ACTION)
        sample_id = self._create_sample()

        resp = client.post(
            f"/rule-chain/{chain_id}/test-run",
            headers=get_auth_headers(),
            json={"sample_ids": [sample_id]},
        )
        assert resp.status_code == 200
        result = resp.json()["results"][0]
        assert result["success"] is True

        # 检查 Action 节点结果
        action_results = [r for r in result["node_results"] if r["node_type"] == "set_severity_action"]
        assert len(action_results) >= 1

        # 检查 actions_executed 包含模拟标记
        assert len(result["actions_executed"]) >= 1
        action = result["actions_executed"][0]
        assert action["result"].get("dry_run") is True
        assert action["result"].get("simulated") is True

    def test_test_run_expected_matching(self):
        """验证预期结果比对"""
        chain_id = self._create_chain(FLASH_LOAN_CHAIN)
        sample_id = self._create_sample(
            overrides={
                "expected_min_score": 50,
                "expected_severity": "HIGH",
                "expected_labels": [],
            }
        )

        resp = client.post(
            f"/rule-chain/{chain_id}/test-run",
            headers=get_auth_headers(),
            json={"sample_ids": [sample_id]},
        )
        assert resp.status_code == 200
        result = resp.json()["results"][0]
        assert result["expected_matched"] is not None
        # Flash loan + large value should get >= 80, >= HIGH
        assert result["expected_matched"] is True
        assert "severity" in result["expected_details"]
        assert "score" in result["expected_details"]

    def test_test_run_no_data(self):
        chain_id = self._create_chain(SIMPLE_CHAIN)

        resp = client.post(
            f"/rule-chain/{chain_id}/test-run",
            headers=get_auth_headers(),
            json={"sample_ids": [], "alert_data": None},
        )
        assert resp.status_code == 400

    def test_test_run_nonexistent_sample_ids(self):
        chain_id = self._create_chain(SIMPLE_CHAIN)

        resp = client.post(
            f"/rule-chain/{chain_id}/test-run",
            headers=get_auth_headers(),
            json={"sample_ids": ["nonexistent-id-1", "nonexistent-id-2"]},
        )
        # 没有找到样本，应返回空结果
        assert resp.status_code == 200
        assert len(resp.json()["results"]) == 0


class TestDryRunExecution:

    """直接测试引擎的 dry-run 行为"""

    @pytest.fixture(autouse=True)
    def _init_registry(self):
        """确保真实节点已注册"""
        from nodes import force_init_registry
        force_init_registry()

    @pytest.mark.anyio
    async def test_action_dry_run(self):
        from engine.parser import ChainParser
        from engine.executor import ChainExecutor
        from engine.context import ExecutionContext

        chain_config = {
            "nodes": [
                {"id": "t1", "type": "alert_trigger", "config": {}, "position": {"x": 0, "y": 0}},
                {"id": "a1", "type": "set_severity_action", "config": {"condition": "passed", "severity": "CRITICAL"}, "position": {"x": 100, "y": 0}},
            ],
            "edges": [
                {"id": "e1", "source": "t1", "source_port": "output", "target": "a1", "target_port": "input"},
            ],
        }

        parsed = ChainParser.parse(chain_config)
        executor = ChainExecutor()
        ctx = await executor.execute(parsed, {"chain_id": 1}, dry_run=True)

        assert ctx.dry_run is True
        assert ctx.get_success() is True
        assert len(ctx.actions_executed) == 1
        assert ctx.actions_executed[0]["result"].get("dry_run") is True
        assert ctx.actions_executed[0]["result"].get("simulated") is True

    @pytest.mark.anyio
    async def test_normal_mode_action_runs(self):
        from engine.parser import ChainParser
        from engine.executor import ChainExecutor

        chain_config = {
            "nodes": [
                {"id": "t1", "type": "alert_trigger", "config": {}, "position": {"x": 0, "y": 0}},
                {"id": "a1", "type": "set_severity_action", "config": {"condition": "passed", "severity": "HIGH"}, "position": {"x": 100, "y": 0}},
            ],
            "edges": [
                {"id": "e1", "source": "t1", "source_port": "output", "target": "a1", "target_port": "input"},
            ],
        }

        parsed = ChainParser.parse(chain_config)
        executor = ChainExecutor()
        ctx = await executor.execute(parsed, {"chain_id": 1}, dry_run=False)

        assert ctx.dry_run is False
        assert ctx.get_success() is True
        assert len(ctx.actions_executed) == 1
        # 正常模式下 action_result 不应有 dry_run 标记
        assert ctx.actions_executed[0]["result"].get("dry_run") is not True
