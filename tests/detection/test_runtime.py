import pytest

from detection import DetectionContext, DetectionResult, DetectionRuntime, DetectionScript, StrategyPack


class PassingScript(DetectionScript):
    id = "passing_script"
    version = "1.0.0"
    name = "Passing Script"
    description = "Test script that always passes"
    required_inputs = ["transfers"]
    default_threshold = 40.0

    async def detect(self, ctx: DetectionContext) -> DetectionResult:
        return DetectionResult.from_score(
            script_id=self.id,
            score=80.0,
            threshold=self.default_threshold,
            attack_type="test_attack",
            labels=["test_pass"],
        )


class MissingInputScript(DetectionScript):
    id = "missing_input_script"
    version = "1.0.0"
    required_inputs = ["trace_calls"]

    async def detect(self, ctx: DetectionContext) -> DetectionResult:
        return DetectionResult.from_score(self.id, 100.0, 40.0, "should_not_run")


class FailingScript(DetectionScript):
    id = "failing_script"
    version = "1.0.0"
    required_inputs = []

    async def detect(self, ctx: DetectionContext) -> DetectionResult:
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_runtime_executes_one_script_and_returns_result():
    runtime = DetectionRuntime([PassingScript()])
    ctx = DetectionContext.from_dict({"chain_id": 56, "tx_hash": "0xabc", "transfers": [{"amount_raw": "1"}]})

    result = await runtime.run(ctx)

    assert result.success is True
    assert len(result.results) == 1
    assert result.results[0].script_id == "passing_script"
    assert result.results[0].passed is True
    assert result.alert_candidates == [result.results[0]]


@pytest.mark.asyncio
async def test_runtime_skips_script_when_required_input_is_missing():
    runtime = DetectionRuntime([MissingInputScript()])
    ctx = DetectionContext.from_dict({"chain_id": 56, "tx_hash": "0xabc"})

    result = await runtime.run(ctx)

    assert result.success is False
    assert result.results == []
    assert result.errors[0]["script_id"] == "missing_input_script"
    assert result.errors[0]["missing_inputs"] == ["trace_calls"]


@pytest.mark.asyncio
async def test_runtime_isolates_script_failures_and_keeps_successful_results():
    runtime = DetectionRuntime([FailingScript(), PassingScript()])
    ctx = DetectionContext.from_dict({"chain_id": 56, "tx_hash": "0xabc", "transfers": [{"amount_raw": "1"}]})

    result = await runtime.run(ctx)

    assert result.success is False
    assert [item.script_id for item in result.results] == ["passing_script"]
    assert result.errors[0]["script_id"] == "failing_script"
    assert "boom" in result.errors[0]["error"]


@pytest.mark.asyncio
async def test_runtime_runs_strategy_pack_and_sets_strategy_id():
    pack = StrategyPack(id="test_pack", version="1.0.0", scripts=[PassingScript()])
    ctx = DetectionContext.from_dict({"chain_id": 56, "tx_hash": "0xabc", "transfers": [{"amount_raw": "1"}]})

    result = await DetectionRuntime.from_pack(pack).run(ctx)

    assert result.strategy_id == "test_pack"
    assert result.results[0].strategy_id == "test_pack"
