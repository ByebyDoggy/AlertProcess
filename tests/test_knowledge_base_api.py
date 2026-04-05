"""
Unit tests for Knowledge Base API Endpoints
"""
import pytest
from fastapi.testclient import TestClient

from main import app
from database.models import SessionLocal, KnowledgeBaseDB


client = TestClient(app)


def get_auth_headers():
    return {"X-API-Key": "default_secret_key_change_in_production"}


def cleanup_test_samples():
    db = SessionLocal()
    try:
        db.query(KnowledgeBaseDB).filter(
            KnowledgeBaseDB.title.like("test_%")
        ).delete()
        db.commit()
    finally:
        db.close()


SAMPLE_CREATE = {
    "title": "test_flash_loan_sample",
    "description": "Test flash loan sample",
    "category": "flash_loan",
    "tags": ["闪电贷", "Aave"],
    "chain_id": 1,
    "tx_hash": "0xtest123",
    "exploiter_address": "0xabc",
    "alert_data": {
        "chain_id": 1,
        "tx_hash": "0xtest123",
        "to_address": "0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9",
        "input_data": "0x0906f8c8",
        "value": "100000000000000000000",
        "gas_price": 35000000000,
        "gas_used": 650000,
    },
    "expected_severity": "CRITICAL",
    "expected_labels": ["LARGE_FLASH_LOAN_ATTACK"],
    "expected_min_score": 80,
    "source": "test",
}


class TestKnowledgeBaseCRUD:

    def setup_method(self):
        cleanup_test_samples()

    def teardown_method(self):
        cleanup_test_samples()

    def test_list_without_auth(self):
        resp = client.get("/knowledge-base/")
        assert resp.status_code == 401

    def test_list_with_auth(self):
        resp = client.get("/knowledge-base/", headers=get_auth_headers())
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_create_sample(self):
        resp = client.post(
            "/knowledge-base/",
            headers=get_auth_headers(),
            json=SAMPLE_CREATE,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "test_flash_loan_sample"
        assert data["category"] == "flash_loan"
        assert data["tags"] == ["闪电贷", "Aave"]
        assert data["chain_id"] == 1
        assert "id" in data
        assert data["alert_data"]["tx_hash"] == "0xtest123"
        assert data["expected_severity"] == "CRITICAL"

    def test_get_sample(self):
        create = client.post("/knowledge-base/", headers=get_auth_headers(), json=SAMPLE_CREATE)
        sample_id = create.json()["id"]

        resp = client.get(f"/knowledge-base/{sample_id}", headers=get_auth_headers())
        assert resp.status_code == 200
        assert resp.json()["id"] == sample_id
        assert resp.json()["title"] == "test_flash_loan_sample"

    def test_get_sample_not_found(self):
        resp = client.get("/knowledge-base/nonexistent", headers=get_auth_headers())
        assert resp.status_code == 404

    def test_update_sample(self):
        create = client.post("/knowledge-base/", headers=get_auth_headers(), json=SAMPLE_CREATE)
        sample_id = create.json()["id"]

        resp = client.put(
            f"/knowledge-base/{sample_id}",
            headers=get_auth_headers(),
            json={"title": "test_updated_title", "category": "gas_manipulation"},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "test_updated_title"
        assert resp.json()["category"] == "gas_manipulation"

    def test_update_sample_alert_data(self):
        create = client.post("/knowledge-base/", headers=get_auth_headers(), json=SAMPLE_CREATE)
        sample_id = create.json()["id"]

        new_alert_data = {"chain_id": 56, "tx_hash": "0xupdated", "gas_price": 100}
        resp = client.put(
            f"/knowledge-base/{sample_id}",
            headers=get_auth_headers(),
            json={"alert_data": new_alert_data},
        )
        assert resp.status_code == 200
        assert resp.json()["alert_data"]["tx_hash"] == "0xupdated"

    def test_delete_sample(self):
        create = client.post("/knowledge-base/", headers=get_auth_headers(), json=SAMPLE_CREATE)
        sample_id = create.json()["id"]

        resp = client.delete(f"/knowledge-base/{sample_id}", headers=get_auth_headers())
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

        resp2 = client.get(f"/knowledge-base/{sample_id}", headers=get_auth_headers())
        assert resp2.status_code == 404

    def test_delete_sample_not_found(self):
        resp = client.delete("/knowledge-base/nonexistent", headers=get_auth_headers())
        assert resp.status_code == 404

    def test_list_with_filters(self):
        # 创建两个不同分类的样本
        client.post("/knowledge-base/", headers=get_auth_headers(), json=SAMPLE_CREATE)
        client.post("/knowledge-base/", headers=get_auth_headers(), json={
            **SAMPLE_CREATE,
            "title": "test_gas_sample",
            "category": "gas_manipulation",
            "chain_id": 56,
        })

        # 按 category 过滤
        resp = client.get("/knowledge-base/?category=flash_loan", headers=get_auth_headers())
        assert resp.status_code == 200
        assert all(r["category"] == "flash_loan" for r in resp.json())

        # 按 chain_id 过滤
        resp = client.get("/knowledge-base/?chain_id=56", headers=get_auth_headers())
        assert resp.status_code == 200
        assert all(r["chain_id"] == 56 for r in resp.json())

        # 按搜索关键词过滤
        resp = client.get("/knowledge-base/?search=flash", headers=get_auth_headers())
        assert resp.status_code == 200
        assert all("flash" in r["title"].lower() for r in resp.json())

    def test_import_samples(self):
        samples = [
            SAMPLE_CREATE,
            {**SAMPLE_CREATE, "title": "test_import_2", "category": "mev"},
        ]
        resp = client.post(
            "/knowledge-base/import",
            headers=get_auth_headers(),
            json={"samples": samples},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 2
        assert len(data["samples"]) == 2

    def test_export_samples(self):
        client.post("/knowledge-base/", headers=get_auth_headers(), json=SAMPLE_CREATE)
        resp = client.get("/knowledge-base/export/all", headers=get_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert isinstance(data["samples"], list)

    def test_categories_endpoint(self):
        resp = client.get("/knowledge-base/meta/categories", headers=get_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert "preset" in data
        assert isinstance(data["preset"], list)
        assert len(data["preset"]) > 0

    def test_pagination(self):
        for i in range(5):
            client.post("/knowledge-base/", headers=get_auth_headers(), json={
                **SAMPLE_CREATE, "title": f"test_page_{i}"
            })

        resp = client.get("/knowledge-base/?skip=0&limit=2", headers=get_auth_headers())
        assert resp.status_code == 200
        assert len(resp.json()) == 2
