import pytest

from backend.detection import DetectionScript
from backend.replay import ReplayCase, ReplayExpectation, ReplayRunner
from backend.strategies import TokenContractActiveLPDrainScript
from tests.fixtures.judao_token_active_lp_drain import build_judao_context, build_normal_fee_token_context


class RuntimeErrorScript(DetectionScript):
    id = "runtime_error_script"

    async def detect(self, ctx):
        raise RuntimeError("intentional replay failure")


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


@pytest.mark.asyncio
async def test_replay_runner_fails_when_script_raises_runtime_error():
    case = ReplayCase(
        id="runtime-error-case",
        context={},
        scripts=[RuntimeErrorScript()],
        expectation=ReplayExpectation(),
    )

    result = await ReplayRunner().run(case)

    assert result.passed is False
    assert any("runtime_error_script" in failure for failure in result.failures)
    assert any("intentional replay failure" in failure for failure in result.failures)


@pytest.mark.asyncio
async def test_replay_runner_fails_when_script_score_is_below_minimum():
    case = ReplayCase(
        id="judao-min-score-control",
        context=build_judao_context(),
        scripts=[TokenContractActiveLPDrainScript()],
        expectation=ReplayExpectation(
            min_score_by_script={"token_contract_active_lp_drain": 101.0},
        ),
    )

    result = await ReplayRunner().run(case)

    assert result.passed is False
    assert any("score" in failure.lower() for failure in result.failures)
    assert any("token_contract_active_lp_drain" in failure for failure in result.failures)


@pytest.mark.asyncio
async def test_replay_runner_fails_when_expected_label_is_missing():
    case = ReplayCase(
        id="judao-missing-label-control",
        context=build_judao_context(),
        scripts=[TokenContractActiveLPDrainScript()],
        expectation=ReplayExpectation(
            expected_labels_by_script={"token_contract_active_lp_drain": ["missing_expected_label"]},
        ),
    )

    result = await ReplayRunner().run(case)

    assert result.passed is False
    assert any("label" in failure.lower() for failure in result.failures)
    assert any("missing_expected_label" in failure for failure in result.failures)
