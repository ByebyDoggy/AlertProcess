import pytest

from nodes.base import NodeRegistry
from nodes.detectors.base import DetectorInputMixin
from nodes.detectors.callback_third_party_drain import CallbackThirdPartyDrainDetector
from tests.fixtures.ekubo_callback_drain import (
    ATTACKER,
    EKUBO_CORE,
    REPEAT_COUNT,
    TOTAL_RAW_AMOUNT,
    VICTIM,
    WBTC,
    build_ekubo_context,
    build_normal_router_swap_context,
)


class TestCallbackThirdPartyDrainDetector:
    def test_registered(self):
        assert NodeRegistry.get("callback_third_party_drain") is CallbackThirdPartyDrainDetector

    @pytest.mark.asyncio
    async def test_ekubo_fixture_detects_critical_third_party_callback_drain(self):
        detector = CallbackThirdPartyDrainDetector(node_id="callback_drain")
        tx = DetectorInputMixin.from_dict(build_ekubo_context())

        output = await detector.process(tx)

        assert output.passed is True
        assert output.severity == "CRITICAL"
        assert output.score >= 90.0
        assert "third_party_transfer_from" in output.labels
        assert "protocol_pass_through" in output.labels
        assert "callback_drain" in output.labels
        assert "access_control_anomaly" in output.labels

        evidence = output.detection["evidence"]
        assert evidence["victim"] == VICTIM
        assert evidence["profit_address"] == ATTACKER
        assert evidence["protocol"] == EKUBO_CORE
        assert evidence["token"] == WBTC
        assert evidence["repeat_count"] == REPEAT_COUNT
        assert evidence["amount_raw"] == str(TOTAL_RAW_AMOUNT)
        assert evidence["matched_ratio"] == 1.0
        assert evidence["callback_loop_count"] >= 80
        assert evidence["usd_value"] > 1_000_000

    @pytest.mark.asyncio
    async def test_normal_router_swap_does_not_trigger(self):
        detector = CallbackThirdPartyDrainDetector(node_id="callback_drain")
        tx = DetectorInputMixin.from_dict(build_normal_router_swap_context())

        output = await detector.process(tx)

        assert output.passed is False
        assert output.score < 40.0
        assert output.labels == []
        assert output.detection["reason"] == "no matching third-party callback drain"
