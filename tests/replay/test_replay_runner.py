import pytest

from replay import ReplayCase, ReplayExpectation, ReplayRunner
from strategies import TokenContractActiveLPDrainScript
from tests.fixtures.judao_token_active_lp_drain import build_judao_context, build_normal_fee_token_context


@pytest.mark.asyncio
async def test_replay_runner_passes_judao_offline_fixture_without_network():
    case = ReplayCase(
        id="judao-token-active-lp-drain",
        context=build_judao_context(),
        scripts=[TokenContractActiveLPDrainScript()],
        expectation=ReplayExpectation(
            expected_passed_scripts=["token_contract_active_lp_drain"],
            min_score_by_script={"token_contract_active_lp_drain": 90.0},
            expected_labels_by_script={
                "token_contract_active_lp_drain": [
                    "token_contract_active_lp_drain",
                    "lp_top_loss",
                    "business_logic_anomaly",
                ],
            },
        ),
    )

    result = await ReplayRunner().run(case)

    assert result.passed is True
    assert result.runtime_result.results[0].script_id == "token_contract_active_lp_drain"
    assert result.failures == []


@pytest.mark.asyncio
async def test_replay_runner_fails_when_expected_script_does_not_pass():
    case = ReplayCase(
        id="normal-fee-token-control",
        context=build_normal_fee_token_context(),
        scripts=[TokenContractActiveLPDrainScript()],
        expectation=ReplayExpectation(expected_passed_scripts=["token_contract_active_lp_drain"]),
    )

    result = await ReplayRunner().run(case)

    assert result.passed is False
    assert "expected script token_contract_active_lp_drain to pass" in result.failures
