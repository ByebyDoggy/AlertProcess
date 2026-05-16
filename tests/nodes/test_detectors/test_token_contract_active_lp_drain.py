import pytest

from nodes.base import NodeRegistry
from nodes.detectors.base import DetectorInputMixin
from nodes.detectors.token_contract_active_lp_drain import TokenContractActiveLPDrainDetector
from tests.fixtures.judao_token_active_lp_drain import (
    JUDAO,
    JUDAO_LP,
    SENDER,
    build_judao_context,
    build_normal_fee_token_context,
)


class TestTokenContractActiveLPDrainDetector:
    def test_registered(self):
        assert NodeRegistry.get("token_contract_active_lp_drain") is TokenContractActiveLPDrainDetector

    @pytest.mark.asyncio
    async def test_judao_fixture_detects_critical_token_contract_active_lp_drain(self):
        detector = TokenContractActiveLPDrainDetector(node_id="token_lp_drain")
        tx = DetectorInputMixin.from_dict(build_judao_context())

        output = await detector.process(tx)

        assert output.passed is True
        assert output.severity == "CRITICAL"
        assert output.score >= 90.0
        assert "token_contract_active_lp_drain" in output.labels
        assert "lp_top_loss" in output.labels
        assert "token_contract_top_profit" in output.labels
        assert "business_logic_anomaly" in output.labels
        assert "flash_loan_amplified" in output.labels
        assert "temporary_contract_execution" in output.labels

        evidence = output.detection["evidence"]
        assert evidence["token_contract"] == JUDAO
        assert evidence["lp_address"] == JUDAO_LP
        assert evidence["sender_profit_address"] == SENDER
        assert evidence["top_profit_address"] == JUDAO
        assert evidence["lp_loss_usd"] > 1_000_000
        assert evidence["sender_profit_usd"] > 200_000
        assert evidence["token_contract_fund_flow_count"] >= 2
        assert evidence["token_contract_call_count"] >= 3
        assert evidence["pair_swap_count"] >= 2
        assert evidence["reserve_read_count"] >= 2
        assert evidence["flash_loan_present"] is True
        assert evidence["temporary_contract_count"] == 2

    @pytest.mark.asyncio
    async def test_normal_fee_token_swap_does_not_trigger(self):
        detector = TokenContractActiveLPDrainDetector(node_id="token_lp_drain")
        tx = DetectorInputMixin.from_dict(build_normal_fee_token_context())

        output = await detector.process(tx)

        assert output.passed is False
        assert output.score < 40.0
        assert output.labels == []
        assert output.detection["reason"] in {
            "lp loss below threshold",
            "sender profit below threshold",
            "no active token contract lp drain",
        }
