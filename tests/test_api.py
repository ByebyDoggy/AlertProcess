"""
Unit tests for Alert API Endpoints
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import sys
sys.path.insert(0, '/workspace')

from main import app
from database.models import SessionLocal, AlertDB, SeverityEnum
from datetime import datetime


client = TestClient(app)


def get_auth_headers():
    """Get authentication headers with valid API key"""
    return {"X-API-Key": "default_secret_key_change_in_production"}


class TestAlertAPI:
    """Test alert API endpoints"""
    
    def test_health_check(self):
        """Test health check endpoint"""
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    def test_get_alerts_without_auth(self):
        """Test getting alerts without authentication"""
        response = client.get("/alert/alerts")
        assert response.status_code == 401
    
    def test_get_alerts_with_invalid_key(self):
        """Test getting alerts with invalid API key"""
        response = client.get(
            "/alert/alerts",
            headers={"X-API-Key": "invalid-key"}
        )
        assert response.status_code == 403
    
    def test_get_alerts_with_valid_key(self):
        """Test getting alerts with valid API key"""
        response = client.get(
            "/alert/alerts",
            headers=get_auth_headers()
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "alerts" in data
        assert "skip" in data
        assert "limit" in data
    
    def test_get_alerts_pagination(self):
        """Test alerts pagination"""
        response = client.get(
            "/alert/alerts?skip=0&limit=10",
            headers=get_auth_headers()
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["skip"] == 0
        assert data["limit"] == 10
    
    def test_get_alerts_with_severity_filter(self):
        """Test getting alerts filtered by severity"""
        response = client.get(
            "/alert/alerts?severity=CRITICAL",
            headers=get_auth_headers()
        )
        
        assert response.status_code == 200
    
    def test_get_stats_without_auth(self):
        """Test getting stats without authentication"""
        response = client.get("/alert/stats")
        assert response.status_code == 401
    
    def test_get_stats_with_valid_key(self):
        """Test getting stats with valid API key"""
        response = client.get(
            "/alert/stats",
            headers=get_auth_headers()
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "critical" in data
        assert "suspicious" in data
        assert "avg_score" in data
    
    def test_submit_alert_without_auth(self):
        """Test submitting alert without authentication"""
        response = client.post("/alert/submit", json={
            "chain_id": 1,
            "tx_hash": "0x123",
            "attacked_address": "0xabc",
            "exploiter_address": "0xdef"
        })
        assert response.status_code == 401
    
    def test_submit_alert_with_valid_key(self):
        """Test submitting alert with valid API key"""
        response = client.post(
            "/alert/submit",
            headers=get_auth_headers(),
            json={
                "chain_id": 1,
                "tx_hash": "0x" + "a" * 64,
                "attacked_address": "0xabc",
                "exploiter_address": "0xdef"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "alert_id" in data
    
    def test_get_single_alert_not_found(self):
        """Test getting a non-existent alert"""
        response = client.get(
            "/alert/alerts/non-existent-id",
            headers=get_auth_headers()
        )
        
        assert response.status_code == 404


def run_tests():
    """Run all tests"""
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    run_tests()
