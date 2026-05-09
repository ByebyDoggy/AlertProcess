"""
Unit tests for Rule Chain API Endpoints
"""
import pytest
from fastapi.testclient import TestClient
import sys
sys.path.insert(0, '/workspace')

from main import app
from database.models import SessionLocal, RuleChainDB


client = TestClient(app)


def get_auth_headers():
    """Get authentication headers with valid API key"""
    return {"X-API-Key": "default_secret_key_change_in_production"}


def cleanup_test_chains():
    """Clean up test rule chains"""
    db = SessionLocal()
    try:
        db.query(RuleChainDB).filter(RuleChainDB.name.like('test_%')).delete()
        db.commit()
    finally:
        db.close()


class TestRuleChainAPI:
    """Test rule chain API endpoints"""
    
    def setup_method(self):
        """Setup before each test"""
        cleanup_test_chains()
    
    def teardown_method(self):
        """Cleanup after each test"""
        cleanup_test_chains()
    
    def test_list_rule_chains_without_auth(self):
        """Test listing rule chains without authentication"""
        response = client.get("/rule-chain/")
        assert response.status_code == 401
    
    def test_list_rule_chains_with_valid_key(self):
        """Test listing rule chains with valid API key"""
        response = client.get("/rule-chain/", headers=get_auth_headers())
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_create_rule_chain(self):
        """Test creating a new rule chain"""
        chain_data = {
            "name": "test_chain_1",
            "description": "Test rule chain",
            "enabled": True,
            "nodes": [
                {
                    "id": "node_1",
                    "type": "trigger",
                    "label": "开始",
                    "position": {"x": 100, "y": 100}
                },
                {
                    "id": "node_2",
                    "type": "condition",
                    "label": "条件判断",
                    "position": {"x": 300, "y": 100},
                    "config": {
                        "field": "detector.flash_loan",
                        "operator": "equals",
                        "value": True
                    }
                }
            ],
            "edges": [
                {"id": "edge_1", "source": "node_1", "target": "node_2"}
            ]
        }
        
        response = client.post(
            "/rule-chain/",
            headers=get_auth_headers(),
            json=chain_data
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "test_chain_1"
        assert data["description"] == "Test rule chain"
        assert data["enabled"] == True
        assert "id" in data
        assert "chain_config" in data
        assert len(data["chain_config"]["nodes"]) == 2
        assert len(data["chain_config"]["edges"]) == 1
    
    def test_get_rule_chain(self):
        """Test getting a specific rule chain"""
        create_response = client.post(
            "/rule-chain/",
            headers=get_auth_headers(),
            json={
                "name": "test_chain_get",
                "description": "Get test",
                "nodes": [{"id": "n1", "type": "trigger", "label": "Test"}],
                "edges": []
            }
        )
        chain_id = create_response.json()["id"]
        
        response = client.get(f"/rule-chain/{chain_id}", headers=get_auth_headers())
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "test_chain_get"
    
    def test_get_rule_chain_not_found(self):
        """Test getting a non-existent rule chain"""
        response = client.get(
            "/rule-chain/non-existent-id",
            headers=get_auth_headers()
        )
        assert response.status_code == 404
    
    def test_update_rule_chain(self):
        """Test updating a rule chain"""
        create_response = client.post(
            "/rule-chain/",
            headers=get_auth_headers(),
            json={
                "name": "test_chain_update",
                "description": "Original description",
                "nodes": [],
                "edges": []
            }
        )
        chain_id = create_response.json()["id"]
        
        update_data = {
            "name": "test_chain_updated",
            "description": "Updated description",
            "enabled": False
        }
        
        response = client.put(
            f"/rule-chain/{chain_id}",
            headers=get_auth_headers(),
            json=update_data
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "test_chain_updated"
        assert data["description"] == "Updated description"
        assert data["enabled"] == False
    
    def test_update_rule_chain_nodes(self):
        """Test updating rule chain nodes and edges"""
        create_response = client.post(
            "/rule-chain/",
            headers=get_auth_headers(),
            json={
                "name": "test_chain_nodes",
                "nodes": [{"id": "n1", "type": "trigger", "label": "Start"}],
                "edges": []
            }
        )
        chain_id = create_response.json()["id"]
        
        new_nodes = [
            {"id": "n1", "type": "trigger", "label": "Start"},
            {"id": "n2", "type": "condition", "label": "Check"},
            {"id": "n3", "type": "action", "label": "Notify"}
        ]
        new_edges = [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "target": "n3"}
        ]
        
        response = client.put(
            f"/rule-chain/{chain_id}",
            headers=get_auth_headers(),
            json={"nodes": new_nodes, "edges": new_edges}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["chain_config"]["nodes"]) == 3
        assert len(data["chain_config"]["edges"]) == 2
    
    def test_delete_rule_chain(self):
        """Test deleting a rule chain"""
        create_response = client.post(
            "/rule-chain/",
            headers=get_auth_headers(),
            json={
                "name": "test_chain_delete",
                "nodes": [],
                "edges": []
            }
        )
        chain_id = create_response.json()["id"]
        
        response = client.delete(f"/rule-chain/{chain_id}", headers=get_auth_headers())
        
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        
        get_response = client.get(f"/rule-chain/{chain_id}", headers=get_auth_headers())
        assert get_response.status_code == 404
    
    def test_delete_rule_chain_not_found(self):
        """Test deleting a non-existent rule chain"""
        response = client.delete(
            "/rule-chain/non-existent-id",
            headers=get_auth_headers()
        )
        assert response.status_code == 404
    
    def test_create_rule_chain_minimal(self):
        """Test creating a rule chain with minimal data"""
        chain_data = {
            "name": "test_minimal",
            "nodes": [],
            "edges": []
        }
        
        response = client.post(
            "/rule-chain/",
            headers=get_auth_headers(),
            json=chain_data
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "test_minimal"
        assert data["description"] == ""
        assert data["enabled"] == True
    
    def test_rule_chain_validation(self):
        """Test rule chain data validation"""
        chain_data = {
            "name": "test_validation",
            "nodes": [
                {
                    "id": "cond_1",
                    "type": "condition",
                    "label": "Flash Loan Check",
                    "position": {"x": 200, "y": 150},
                    "config": {
                        "field": "detector.flash_loan.detected",
                        "operator": "equals",
                        "value": True
                    }
                },
                {
                    "id": "action_1",
                    "type": "action",
                    "label": "Set Severity",
                    "position": {"x": 400, "y": 150},
                    "config": {
                        "actionType": "set_severity",
                        "actionValue": "CRITICAL"
                    }
                }
            ],
            "edges": [
                {"id": "edge_1", "source": "cond_1", "target": "action_1", "label": "匹配"}
            ]
        }

        response = client.post(
            "/rule-chain/",
            headers=get_auth_headers(),
            json=chain_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["chain_config"]["nodes"][0]["config"]["field"] == "detector.flash_loan.detected"

    def test_validate_returns_structured_errors(self):
        """Test validation returns machine-readable errors and normalized config"""
        response = client.post(
            "/rule-chain/validate",
            headers=get_auth_headers(),
            json={
                "nodes": [{"id": "bad_1", "type": "missing_detector", "label": "Missing"}],
                "edges": [],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert data["normalized_config"]["nodes"][0]["type"] == "missing_detector"
        assert data["stats"]["node_count"] == 1
        assert any(error["code"] == "UNKNOWN_NODE_TYPE" for error in data["errors"])
        first_error = data["errors"][0]
        assert first_error["severity"] == "error"
        assert first_error["field_path"]
        assert "suggestion" in first_error

    def test_ai_generate_returns_generation_meta_on_provider_error(self, monkeypatch):
        from services.ai.client import AIClientError

        async def fake_generate_rule_chain_draft(**kwargs):
            return {
                "draft": {"name": "AI 生成规则链", "description": "", "nodes": [], "edges": []},
                "validation": {"valid": True, "errors": [], "warnings": [], "normalized_config": {"nodes": [], "edges": []}, "stats": {"node_count": 0, "edge_count": 0, "trigger_count": 0, "error_count": 0, "warning_count": 0}},
                "explanation": "ok",
                "assumptions": [],
                "generation_meta": {"mode": kwargs["mode"], "model": "mock-model", "used_current_chain": False},
            }

        monkeypatch.setattr("services.ai.rule_chain_generator.generate_rule_chain_draft", fake_generate_rule_chain_draft)
        response = client.post(
            "/rule-chain/ai/generate",
            headers=get_auth_headers(),
            json={
                "prompt": "生成一个检测高 gas 的规则链",
                "mode": "new",
                "current_chain": {"nodes": [], "edges": []},
                "constraints": {"allow_actions": True},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["generation_meta"]["mode"] == "new"
        assert data["generation_meta"]["model"] == "mock-model"
        assert data["generation_meta"]["used_current_chain"] is False

    def test_validate_accepts_standard_port_aliases(self):
        """Test validation normalizes camelCase and snake_case port fields"""
        response = client.post(
            "/rule-chain/validate",
            headers=get_auth_headers(),
            json={
                "nodes": [
                    {"id": "trigger_1", "type": "alert_trigger", "label": "Trigger"},
                    {"id": "gas_1", "type": "gas_price_detector", "label": "Gas"},
                ],
                "edges": [
                    {
                        "id": "edge_1",
                        "source": "trigger_1",
                        "source_port": "output",
                        "target": "gas_1",
                        "target_port": "input",
                    }
                ],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["errors"] == []
        assert data["normalized_config"]["edges"][0]["sourcePort"] == "output"
        assert data["normalized_config"]["edges"][0]["targetPort"] == "input"

    def test_mcp_schema_endpoint(self):
        """Test MCP schema bundle exposes construction contract"""
        response = client.get("/rule-chain/schema/mcp")

        assert response.status_code == 200
        data = response.json()
        assert "standard_payload" in data
        assert "nodes" in data
        assert "connection_rules" in data
        assert data["endpoints"]["validate"] == "POST /rule-chain/validate"
        assert any(node["name"] == "alert_trigger" for node in data["nodes"])

    def test_ai_generate_returns_validated_draft(self, monkeypatch):
        """Test AI generation endpoint validates the model draft before returning"""
        async def fake_generate_rule_chain_draft(**kwargs):
            return {
                "draft": {
                    "name": "test_ai_chain",
                    "description": "Generated",
                    "nodes": [{"id": "trigger_1", "type": "alert_trigger", "label": "Trigger", "config": {}, "position": {"x": 0, "y": 0}}],
                    "edges": [],
                },
                "validation": {"valid": True, "errors": [], "warnings": [], "normalized_config": {}, "stats": {"node_count": 1}},
                "explanation": "Generated a trigger-only chain.",
                "assumptions": ["No detector requested"],
            }

        monkeypatch.setattr(
            "services.ai.rule_chain_generator.generate_rule_chain_draft",
            fake_generate_rule_chain_draft,
        )
        response = client.post(
            "/rule-chain/ai/generate",
            headers=get_auth_headers(),
            json={"prompt": "create a trigger chain", "mode": "new"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["draft"]["name"] == "test_ai_chain"
        assert data["validation"]["valid"] is True


def run_tests():
    """Run all tests"""
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    run_tests()