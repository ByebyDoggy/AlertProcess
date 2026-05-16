import pytest

from alerting import AlertChannel, AlertDispatcher, AlertPayload, DeliveryResult, TelegramChannel, WebhookChannel
from detection import DetectionResult


class RecordingChannel(AlertChannel):
    name = "recording"

    def __init__(self):
        self.sent = []

    async def send(self, payload: AlertPayload) -> DeliveryResult:
        self.sent.append(payload)
        return DeliveryResult(channel=self.name, sent=True, dry_run=False, detail="sent")


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


def test_webhook_and_telegram_channels_are_safe_placeholders_until_transport_is_added():
    assert WebhookChannel(url="https://example.invalid/hook").name == "webhook"
    assert TelegramChannel(bot_token="token", chat_id="chat").name == "telegram"
