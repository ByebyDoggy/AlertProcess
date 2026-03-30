"""
Unit tests for Notifier module
"""
import pytest
import asyncio
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch

import sys
sys.path.insert(0, '/workspace')

from models import AlertInput, TransactionContext, DetectionResult, FinalAlert, SeverityEnum
from notifiers.base import (
    NotifierConfig,
    NotificationFilter,
    NotificationContext,
    Notifier,
    WebhookNotifier,
    LogNotifier,
    NotifierRegistry,
    NotificationManager,
)


class TestNotifierConfig:
    """Test NotifierConfig"""
    
    def test_default_config(self):
        """Test default notifier config"""
        config = NotifierConfig()
        
        assert config.enabled is True
        assert config.min_severity == SeverityEnum.UNKNOWN
        assert config.rate_limit_per_minute == 0


class TestNotificationFilter:
    """Test NotificationFilter"""
    
    def test_default_filter(self):
        """Test default filter passes everything"""
        filter_config = NotificationFilter()
        
        assert filter_config.min_severity == SeverityEnum.UNKNOWN
        assert filter_config.min_score == 0.0
        assert filter_config.required_tags == []
        assert filter_config.excluded_tags == []


class TestNotificationContext:
    """Test NotificationContext"""
    
    def test_context_creation(self):
        """Test notification context creation"""
        alert = FinalAlert(
            alert_id="test-123",
            chain_id=1,
            tx_hash="0x123",
            severity=SeverityEnum.HIGH,
            score=85.0
        )
        context = TransactionContext(chain_id=1, tx_hash="0x123")
        
        notification_ctx = NotificationContext(
            alert=alert,
            context=context,
            detections=[],
            rule_results=[],
            scoring_result=None
        )
        
        assert notification_ctx.alert.alert_id == "test-123"
        assert notification_ctx.context.chain_id == 1


class TestNotifierShouldNotify:
    """Test Notifier should_notify logic"""
    
    def test_disabled_notifier(self):
        """Test disabled notifier doesn't notify"""
        config = NotifierConfig(enabled=False)
        notifier = LogNotifier(config)
        
        alert = FinalAlert(
            alert_id="test-123",
            chain_id=1,
            tx_hash="0x123",
            severity=SeverityEnum.HIGH,
            score=85.0
        )
        context = TransactionContext(chain_id=1, tx_hash="0x123")
        
        notification_ctx = NotificationContext(
            alert=alert,
            context=context,
            detections=[]
        )
        
        assert notifier.should_notify(notification_ctx) is False
    
    def test_severity_filter(self):
        """Test severity filter"""
        config = NotifierConfig(min_severity=SeverityEnum.HIGH)
        notifier = LogNotifier(config)
        
        # LOW severity should be filtered
        alert_low = FinalAlert(
            alert_id="test-123",
            chain_id=1,
            tx_hash="0x123",
            severity=SeverityEnum.LOW,
            score=20.0
        )
        ctx = TransactionContext(chain_id=1, tx_hash="0x123")
        notification_ctx_low = NotificationContext(alert=alert_low, context=ctx, detections=[])
        
        assert notifier.should_notify(notification_ctx_low) is False
        
        # HIGH severity should pass
        alert_high = FinalAlert(
            alert_id="test-456",
            chain_id=1,
            tx_hash="0x456",
            severity=SeverityEnum.HIGH,
            score=80.0
        )
        notification_ctx_high = NotificationContext(alert=alert_high, context=ctx, detections=[])
        
        assert notifier.should_notify(notification_ctx_high) is True
    
    def test_score_filter(self):
        """Test score filter"""
        config = NotifierConfig(min_severity=SeverityEnum.UNKNOWN)
        notifier = LogNotifier(config)
        
        # Set filter to require min score 50
        notifier.set_filter(NotificationFilter(min_score=50.0))
        
        alert_low_score = FinalAlert(
            alert_id="test-123",
            chain_id=1,
            tx_hash="0x123",
            severity=SeverityEnum.MEDIUM,
            score=30.0
        )
        ctx = TransactionContext(chain_id=1, tx_hash="0x123")
        notification_ctx = NotificationContext(alert=alert_low_score, context=ctx, detections=[])
        
        assert notifier.should_notify(notification_ctx) is False
        
        # HIGH score should pass
        alert_high_score = FinalAlert(
            alert_id="test-456",
            chain_id=1,
            tx_hash="0x456",
            severity=SeverityEnum.MEDIUM,
            score=70.0
        )
        notification_ctx_high = NotificationContext(alert=alert_high_score, context=ctx, detections=[])
        
        assert notifier.should_notify(notification_ctx_high) is True
    
    def test_required_tags_filter(self):
        """Test required tags filter"""
        config = NotifierConfig()
        notifier = LogNotifier(config)
        
        # Set filter to require "urgent" tag
        notifier.set_filter(NotificationFilter(required_tags=["urgent"]))
        
        # Alert without tag should be filtered
        alert = FinalAlert(
            alert_id="test-123",
            chain_id=1,
            tx_hash="0x123",
            severity=SeverityEnum.HIGH,
            score=85.0,
            metadata={}
        )
        ctx = TransactionContext(chain_id=1, tx_hash="0x123")
        notification_ctx = NotificationContext(alert=alert, context=ctx, detections=[])
        
        assert notifier.should_notify(notification_ctx) is False
        
        # Alert with tag should pass
        alert_with_tag = FinalAlert(
            alert_id="test-456",
            chain_id=1,
            tx_hash="0x456",
            severity=SeverityEnum.HIGH,
            score=85.0,
            metadata={"tags": ["urgent", "security"]}
        )
        notification_ctx_tagged = NotificationContext(alert=alert_with_tag, context=ctx, detections=[])
        
        assert notifier.should_notify(notification_ctx_tagged) is True
    
    def test_excluded_tags_filter(self):
        """Test excluded tags filter"""
        config = NotifierConfig()
        notifier = LogNotifier(config)
        
        # Set filter to exclude "test" tag
        notifier.set_filter(NotificationFilter(excluded_tags=["test"]))
        
        # Alert with excluded tag should be filtered
        alert = FinalAlert(
            alert_id="test-123",
            chain_id=1,
            tx_hash="0x123",
            severity=SeverityEnum.HIGH,
            score=85.0,
            metadata={"tags": ["test"]}
        )
        ctx = TransactionContext(chain_id=1, tx_hash="0x123")
        notification_ctx = NotificationContext(alert=alert, context=ctx, detections=[])
        
        assert notifier.should_notify(notification_ctx) is False
    
    def test_chain_ids_filter(self):
        """Test chain IDs filter"""
        config = NotifierConfig()
        notifier = LogNotifier(config)
        
        # Set filter to only allow chain_id 1
        notifier.set_filter(NotificationFilter(chain_ids=[1]))
        
        # Alert on chain 56 should be filtered
        alert_bsc = FinalAlert(
            alert_id="test-123",
            chain_id=56,  # BSC
            tx_hash="0x123",
            severity=SeverityEnum.HIGH,
            score=85.0
        )
        ctx_bsc = TransactionContext(chain_id=56, tx_hash="0x123")
        notification_ctx_bsc = NotificationContext(alert=alert_bsc, context=ctx_bsc, detections=[])
        
        assert notifier.should_notify(notification_ctx_bsc) is False
        
        # Alert on chain 1 should pass
        alert_eth = FinalAlert(
            alert_id="test-456",
            chain_id=1,  # Ethereum
            tx_hash="0x456",
            severity=SeverityEnum.HIGH,
            score=85.0
        )
        ctx_eth = TransactionContext(chain_id=1, tx_hash="0x456")
        notification_ctx_eth = NotificationContext(alert=alert_eth, context=ctx_eth, detections=[])
        
        assert notifier.should_notify(notification_ctx_eth) is True


class TestLogNotifier:
    """Test LogNotifier"""
    
    def test_log_notifier_creation(self):
        """Test log notifier creation"""
        notifier = LogNotifier(log_level="DEBUG")
        
        assert notifier.name == "log"
        assert notifier.log_level == "DEBUG"
    
    @pytest.mark.asyncio
    async def test_log_notifier_send(self):
        """Test log notifier sends successfully"""
        notifier = LogNotifier(log_level="INFO")
        
        alert = FinalAlert(
            alert_id="test-123",
            chain_id=1,
            tx_hash="0x123",
            severity=SeverityEnum.HIGH,
            score=85.0
        )
        ctx = TransactionContext(
            chain_id=1,
            tx_hash="0x123",
            from_address="0xabc",
            to_address="0xdef"
        )
        detection = DetectionResult(
            detector_name="test_detector",
            detected=True,
            alert_type="TEST",
            severity=SeverityEnum.HIGH
        )
        
        notification_ctx = NotificationContext(
            alert=alert,
            context=ctx,
            detections=[detection]
        )
        
        result = await notifier.send(notification_ctx)
        
        assert result is True


class TestWebhookNotifier:
    """Test WebhookNotifier"""
    
    def test_webhook_notifier_creation(self):
        """Test webhook notifier creation"""
        notifier = WebhookNotifier(webhook_url="https://example.com/webhook")
        
        assert notifier.name == "webhook"
        assert notifier.webhook_url == "https://example.com/webhook"


class TestNotifierRegistry:
    """Test NotifierRegistry"""
    
    def test_register_and_get(self):
        """Test registering and retrieving notifiers"""
        NotifierRegistry.clear()
        
        notifier = LogNotifier()
        NotifierRegistry.register(notifier)
        
        retrieved = NotifierRegistry.get("log")
        assert retrieved is not None
        assert retrieved.name == "log"
    
    def test_unregister(self):
        """Test unregistering notifiers"""
        NotifierRegistry.clear()
        
        notifier = LogNotifier()
        NotifierRegistry.register(notifier)
        NotifierRegistry.unregister("log")
        
        assert NotifierRegistry.get("log") is None
    
    def test_list_notifiers(self):
        """Test listing notifiers"""
        NotifierRegistry.clear()
        
        NotifierRegistry.register(LogNotifier())
        NotifierRegistry.register(WebhookNotifier(webhook_url="https://example.com"))
        
        names = NotifierRegistry.list_notifiers()
        
        assert "log" in names
        assert "webhook" in names
    
    def test_get_all_enabled(self):
        """Test getting all enabled notifiers"""
        NotifierRegistry.clear()
        
        LogNotifier(NotifierConfig(enabled=True))
        NotifierRegistry.register(LogNotifier(NotifierConfig(enabled=True)))
        NotifierRegistry.register(WebhookNotifier(NotifierConfig(enabled=False)))
        
        enabled = NotifierRegistry.get_all_enabled()
        
        # Should only return enabled notifiers
        # Note: default config has enabled=True


class TestNotificationManager:
    """Test NotificationManager"""
    
    @pytest.mark.asyncio
    async def test_manager_notify(self):
        """Test notification manager sends to all notifiers"""
        manager = NotificationManager()
        manager.add_notifier(LogNotifier())
        
        alert = FinalAlert(
            alert_id="test-123",
            chain_id=1,
            tx_hash="0x123",
            severity=SeverityEnum.HIGH,
            score=85.0
        )
        ctx = TransactionContext(chain_id=1, tx_hash="0x123")
        detections = []
        
        results = await manager.notify(alert, ctx, detections)
        
        assert "log" in results
        assert results["log"] is True
    
    @pytest.mark.asyncio
    async def test_manager_notify_batch(self):
        """Test batch notification"""
        manager = NotificationManager()
        manager.add_notifier(LogNotifier())
        
        alert1 = FinalAlert(
            alert_id="test-1",
            chain_id=1,
            tx_hash="0x1",
            severity=SeverityEnum.HIGH,
            score=85.0
        )
        alert2 = FinalAlert(
            alert_id="test-2",
            chain_id=1,
            tx_hash="0x2",
            severity=SeverityEnum.MEDIUM,
            score=50.0
        )
        
        ctx = TransactionContext(chain_id=1, tx_hash="0x123")
        
        notifications = [
            NotificationContext(alert=alert1, context=ctx, detections=[]),
            NotificationContext(alert=alert2, context=ctx, detections=[])
        ]
        
        results = await manager.notify_batch(notifications)
        
        assert "log" in results
        assert len(results["log"]) == 2


def run_tests():
    """Run all tests"""
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    run_tests()
