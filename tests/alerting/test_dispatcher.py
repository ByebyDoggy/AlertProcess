import pytest

from backend.alerting import AlertChannel, AlertDispatcher, AlertPayload, DeliveryResult, TelegramChannel, WebhookChannel
from backend.detection import DetectionResult


class RecordingChannel(AlertChannel):
    name = "recording"

    def __init__(self):
        self.sent = []

    async def send(self, payload: AlertPayload) -> DeliveryResult:
        self.sent.append(payload)
        return DeliveryResult(channel=self.name, sent=True, dry_run=False, detail="sent")


class RaisingChannel(AlertChannel):
    name = "raising"

    async def send(self, payload: AlertPayload) -> DeliveryResult:
        raise RuntimeError("delivery unavailable")


@pytest.mark.asyncio
async def test_alert_dispatcher_dry_run_does_not_call_channel_send():
    channel = RecordingChannel()
    dispatcher = AlertDispatcher([channel], dry_run=True)
    payload = AlertPayload.from_detection_result(
        tx_hash="0xabc",
        result=DetectionResult.from_score("script", 90.0, 40.0, "attack", labels=["x"]),
    )

    results = await dispatcher.dispatch(payload)

    assert channel.sent == []
    assert results == [DeliveryResult(channel="recording", sent=False, dry_run=True, detail="dry-run skipped")]


@pytest.mark.asyncio
async def test_alert_dispatcher_sends_when_not_dry_run():
    channel = RecordingChannel()
    dispatcher = AlertDispatcher([channel], dry_run=False)
    payload = AlertPayload.from_detection_result(
        tx_hash="0xabc",
        result=DetectionResult.from_score("script", 90.0, 40.0, "attack", labels=["x"]),
    )

    results = await dispatcher.dispatch(payload)

    assert channel.sent == [payload]
    assert results[0].sent is True
    assert results[0].dry_run is False


@pytest.mark.asyncio
async def test_alert_dispatcher_isolates_channel_failures():
    recording = RecordingChannel()
    dispatcher = AlertDispatcher([RaisingChannel(), recording], dry_run=False)
    payload = AlertPayload.from_detection_result(
        tx_hash="0xabc",
        result=DetectionResult.from_score("script", 90.0, 40.0, "attack", labels=["x"]),
    )

    results = await dispatcher.dispatch(payload)

    assert recording.sent == [payload]
    assert results[0].channel == "raising"
    assert results[0].sent is False
    assert results[0].dry_run is False
    assert "send failed: delivery unavailable" in results[0].detail
    assert results[1].sent is True


def test_webhook_and_telegram_channels_are_safe_placeholders_until_transport_is_added():
    assert WebhookChannel(url="https://example.invalid/hook").name == "webhook"
    assert TelegramChannel(bot_token="token", chat_id="chat").name == "telegram"
