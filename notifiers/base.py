"""
Notifier module for pluggable alert notification channels
Supports multiple notification backends with filtering and rate limiting
"""
from abc import ABC, abstractmethod
from typing import Any
from pydantic import BaseModel
import asyncio
import time

from models import AlertInput, TransactionContext, DetectionResult, FinalAlert, SeverityEnum


class NotifierConfig(BaseModel):
    """Base notifier configuration"""
    enabled: bool = True
    min_severity: SeverityEnum = SeverityEnum.UNKNOWN  # Only notify for >= this severity
    rate_limit_per_minute: int = 0  # 0 = no limit


class NotificationFilter(BaseModel):
    """Filter criteria for notifications"""
    min_severity: SeverityEnum = SeverityEnum.UNKNOWN
    min_score: float = 0.0
    required_tags: list[str] = []  # Must have ALL of these tags
    excluded_tags: list[str] = []  # Must NOT have ANY of these tags
    required_detectors: list[str] = []  # Must have detections from ALL of these
    chain_ids: list[int] = []  # Empty = all chains


class NotificationContext(BaseModel):
    """Context passed to notifier when sending notification"""
    alert: FinalAlert
    context: TransactionContext
    detections: list[DetectionResult]
    rule_results: list[Any] = []  # Rule evaluation results
    scoring_result: Any = None
    timestamp: float = time.time()


class Notifier(ABC):
    """
    Base class for notifiers
    
    Notifiers send alerts to various channels (webhook, slack, email, etc.)
    They can be configured with filters to control which alerts get sent.
    """
    
    def __init__(self, config: NotifierConfig | None = None):
        self.config = config or self.get_default_config()
        self._rate_limit_cache: dict[str, list[float]] = {}  # key -> list of timestamps
        self._filter = NotificationFilter()
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique notifier name"""
        pass
    
    @property
    def description(self) -> str:
        """Human-readable description"""
        return ""
    
    @classmethod
    def get_default_config(cls) -> NotifierConfig:
        """Get default configuration"""
        return NotifierConfig()
    
    def set_filter(self, filter_config: NotificationFilter):
        """Set notification filter"""
        self._filter = filter_config
    
    def should_notify(self, notification_context: NotificationContext) -> bool:
        """
        Determine if notification should be sent based on filter criteria
        """
        # Check if notifier is enabled
        if not self.config.enabled:
            return False
        
        # Check rate limit
        if self.config.rate_limit_per_minute > 0:
            if self._is_rate_limited(notification_context.alert.alert_id):
                return False
        
        # Check severity filter - use config's min_severity as baseline
        # Filter can make it stricter but not looser
        SEVERITY_ORDER = {
            SeverityEnum.UNKNOWN: 0,
            SeverityEnum.LOW: 1,
            SeverityEnum.MEDIUM: 2,
            SeverityEnum.HIGH: 3,
            SeverityEnum.CRITICAL: 4,
        }
        
        alert_severity_level = SEVERITY_ORDER.get(notification_context.alert.severity, 0)
        # Use whichever is stricter (higher number)
        config_min_level = SEVERITY_ORDER.get(self.config.min_severity, 0)
        filter_min_level = SEVERITY_ORDER.get(self._filter.min_severity, 0)
        effective_min_level = max(config_min_level, filter_min_level)
        
        if alert_severity_level < effective_min_level:
            return False
        
        # Check score filter - use whichever is stricter (higher number)
        config_min_score = 0.0  # Config doesn't have min_score, only filter does
        filter_min_score = self._filter.min_score
        effective_min_score = max(config_min_score, filter_min_score)
        if notification_context.alert.score < effective_min_score:
            return False
        
        # Check required tags
        if self._filter.required_tags:
            alert_tags = notification_context.alert.metadata.get("tags", [])
            if not all(tag in alert_tags for tag in self._filter.required_tags):
                return False
        
        # Check excluded tags
        if self._filter.excluded_tags:
            alert_tags = notification_context.alert.metadata.get("tags", [])
            if any(tag in alert_tags for tag in self._filter.excluded_tags):
                return False
        
        # Check chain IDs
        if self._filter.chain_ids:
            if notification_context.alert.chain_id not in self._filter.chain_ids:
                return False
        
        return True
    
    def _is_rate_limited(self, key: str) -> bool:
        """Check if key is rate limited"""
        now = time.time()
        if key not in self._rate_limit_cache:
            self._rate_limit_cache[key] = []
        
        # Clean old entries (older than 1 minute)
        self._rate_limit_cache[key] = [
            t for t in self._rate_limit_cache[key]
            if now - t < 60
        ]
        
        if len(self._rate_limit_cache[key]) >= self.config.rate_limit_per_minute:
            return True
        
        self._rate_limit_cache[key].append(now)
        return False
    
    @abstractmethod
    async def _send(self, notification_context: NotificationContext) -> bool:
        """
        Internal send implementation to be overridden by subclasses
        
        Returns:
            True if send succeeded, False otherwise
        """
        pass
    
    async def send(self, notification_context: NotificationContext) -> bool:
        """
        Send notification if it passes filters
        
        Returns:
            True if notification was sent, False if filtered or failed
        """
        if not self.should_notify(notification_context):
            return False
        
        try:
            return await self._send(notification_context)
        except Exception as e:
            # Log error but don't raise - notification failure shouldn't crash the system
            return False
    
    async def send_batch(self, notifications: list[NotificationContext]) -> list[bool]:
        """Send multiple notifications"""
        results = []
        for notification in notifications:
            result = await self.send(notification)
            results.append(result)
        return results


class WebhookNotifier(Notifier):
    """
    Webhook notifier - sends HTTP POST to a configurable URL
    """
    
    def __init__(self, config: NotifierConfig | None = None, webhook_url: str = ""):
        super().__init__(config)
        self.webhook_url = webhook_url
    
    @property
    def name(self) -> str:
        return "webhook"
    
    @property
    def description(self) -> str:
        return "Sends notifications via HTTP webhook"
    
    async def _send(self, notification_context: NotificationContext) -> bool:
        """Send notification via HTTP POST"""
        import aiohttp
        
        payload = self._build_payload(notification_context)
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    return response.status >= 200 and response.status < 300
        except Exception:
            return False
    
    def _build_payload(self, notification_context: NotificationContext) -> dict[str, Any]:
        """Build webhook payload"""
        alert = notification_context.alert
        return {
            "alert_id": alert.alert_id,
            "chain_id": alert.chain_id,
            "tx_hash": alert.tx_hash,
            "severity": alert.severity.value,
            "score": alert.score,
            "detections": [
                {
                    "detector_name": d.detector_name,
                    "detected": d.detected,
                    "alert_type": d.alert_type,
                    "severity": d.severity.value if d.severity else None,
                    "metadata": d.metadata
                }
                for d in notification_context.detections
            ],
            "matched_rules": alert.matched_rules,
            "timestamp": alert.timestamp.isoformat() if alert.timestamp else None,
            "context": {
                "from_address": notification_context.context.from_address,
                "to_address": notification_context.context.to_address,
                "value": notification_context.context.value,
                "gas_price": notification_context.context.gas_price,
            }
        }


class LogNotifier(Notifier):
    """
    Log notifier - logs notifications to a logger
    Useful for debugging or development
    """
    
    def __init__(self, config: NotifierConfig | None = None, log_level: str = "INFO"):
        super().__init__(config)
        self.log_level = log_level
        self._logger = None
    
    @property
    def name(self) -> str:
        return "log"
    
    @property
    def description(self) -> str:
        return "Logs notifications to console/file"
    
    async def _send(self, notification_context: NotificationContext) -> bool:
        """Send notification via logging"""
        import logging
        
        if self._logger is None:
            self._logger = logging.getLogger("alert_notifier")
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            self._logger.addHandler(handler)
            self._logger.setLevel(getattr(logging, self.log_level))
        
        alert = notification_context.alert
        log_msg = (
            f"ALERT [{alert.severity.value}] "
            f"alert_id={alert.alert_id} "
            f"chain_id={alert.chain_id} "
            f"tx_hash={alert.tx_hash} "
            f"score={alert.score:.1f} "
            f"detectors={[d.detector_name for d in notification_context.detections if d.detected]}"
        )
        
        if self.log_level == "DEBUG":
            self._logger.debug(log_msg)
        elif self.log_level == "INFO":
            self._logger.info(log_msg)
        elif self.log_level == "WARNING":
            self._logger.warning(log_msg)
        elif self.log_level == "ERROR":
            self._logger.error(log_msg)
        
        return True


class NotifierRegistry:
    """
    Registry for managing notifiers
    """
    
    _notifiers: dict[str, Notifier] = {}
    
    @classmethod
    def register(cls, notifier: Notifier):
        """Register a notifier"""
        cls._notifiers[notifier.name] = notifier
    
    @classmethod
    def get(cls, name: str) -> Notifier | None:
        """Get notifier by name"""
        return cls._notifiers.get(name)
    
    @classmethod
    def unregister(cls, name: str):
        """Unregister a notifier"""
        if name in cls._notifiers:
            del cls._notifiers[name]
    
    @classmethod
    def list_notifiers(cls) -> list[str]:
        """List all registered notifier names"""
        return list(cls._notifiers.keys())
    
    @classmethod
    def get_all_enabled(cls) -> list[Notifier]:
        """Get all enabled notifiers"""
        return [n for n in cls._notifiers.values() if n.config.enabled]
    
    @classmethod
    async def notify_all(cls, notification_context: NotificationContext) -> dict[str, bool]:
        """Send notification via all enabled notifiers"""
        results = {}
        for notifier in cls.get_all_enabled():
            results[notifier.name] = await notifier.send(notification_context)
        return results
    
    @classmethod
    def clear(cls):
        """Clear all notifiers"""
        cls._notifiers.clear()


class NotificationManager:
    """
    Manages notification sending with coordinator pattern
    
    Coordinates notification sending across multiple notifiers
    with proper error handling and async support.
    """
    
    def __init__(self, notifiers: list[Notifier] | None = None):
        self.notifiers = notifiers or []
        self._lock = asyncio.Lock()
    
    def add_notifier(self, notifier: Notifier):
        """Add a notifier to the manager"""
        self.notifiers.append(notifier)
    
    def remove_notifier(self, name: str):
        """Remove a notifier by name"""
        self.notifiers = [n for n in self.notifiers if n.name != name]
    
    async def notify(
        self,
        alert: FinalAlert,
        context: TransactionContext,
        detections: list[DetectionResult],
        rule_results: list[Any] | None = None,
        scoring_result: Any = None
    ) -> dict[str, bool]:
        """
        Send notifications to all configured notifiers
        
        Returns:
            Dict of notifier name -> success status
        """
        notification_context = NotificationContext(
            alert=alert,
            context=context,
            detections=detections,
            rule_results=rule_results or [],
            scoring_result=scoring_result
        )
        
        results = {}
        for notifier in self.notifiers:
            try:
                results[notifier.name] = await notifier.send(notification_context)
            except Exception:
                results[notifier.name] = False
        
        return results
    
    async def notify_batch(
        self,
        notifications: list[NotificationContext]
    ) -> dict[str, list[bool]]:
        """
        Send multiple notifications
        
        Returns:
            Dict of notifier name -> list of success statuses
        """
        results = {}
        for notifier in self.notifiers:
            results[notifier.name] = await notifier.send_batch(notifications)
        return results
