from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from backend.detection import DetectionResult


@dataclass(frozen=True)
class AlertPayload:
    tx_hash: str
    script_id: str
    attack_type: str
    score: float
    severity: str
    labels: list[str] = field(default_factory=list)
    summary: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_detection_result(cls, tx_hash: str, result: DetectionResult) -> "AlertPayload":
        return cls(
            tx_hash=tx_hash,
            script_id=result.script_id,
            attack_type=result.attack_type,
            score=result.score,
            severity=result.severity,
            labels=list(result.labels),
            summary=result.summary,
            details=dict(result.details),
        )


@dataclass(frozen=True)
class DeliveryResult:
    channel: str
    sent: bool
    dry_run: bool
    detail: str


class AlertChannel(ABC):
    name: str

    @abstractmethod
    async def send(self, payload: AlertPayload) -> DeliveryResult:
        raise NotImplementedError


@dataclass(frozen=True)
class WebhookChannel(AlertChannel):
    url: str
    name: str = "webhook"

    async def send(self, payload: AlertPayload) -> DeliveryResult:
        return DeliveryResult(channel=self.name, sent=False, dry_run=False, detail="transport not configured")


@dataclass(frozen=True)
class TelegramChannel(AlertChannel):
    bot_token: str
    chat_id: str
    name: str = "telegram"

    async def send(self, payload: AlertPayload) -> DeliveryResult:
        return DeliveryResult(channel=self.name, sent=False, dry_run=False, detail="transport not configured")


class AlertDispatcher:
    def __init__(self, channels: list[AlertChannel], dry_run: bool = False) -> None:
        self.channels = channels
        self.dry_run = dry_run

    async def dispatch(self, payload: AlertPayload) -> list[DeliveryResult]:
        results: list[DeliveryResult] = []
        for channel in self.channels:
            if self.dry_run:
                results.append(
                    DeliveryResult(channel=channel.name, sent=False, dry_run=True, detail="dry-run skipped")
                )
                continue
            try:
                results.append(await channel.send(payload))
            except Exception as exc:
                results.append(
                    DeliveryResult(
                        channel=channel.name,
                        sent=False,
                        dry_run=False,
                        detail=f"send failed: {exc}",
                    )
                )
        return results
