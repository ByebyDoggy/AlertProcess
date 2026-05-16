from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from detection.context import DetectionContext
from detection.runtime import DetectionRuntime, RuntimeResult
from detection.script import DetectionScript


@dataclass
class ReplayExpectation:
    expected_passed_scripts: list[str] = field(default_factory=list)
    min_score_by_script: dict[str, float] = field(default_factory=dict)
    expected_labels_by_script: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class ReplayCase:
    id: str
    context: dict[str, Any]
    scripts: list[DetectionScript]
    expectation: ReplayExpectation


@dataclass
class ReplayResult:
    case_id: str
    runtime_result: RuntimeResult
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures


class ReplayRunner:
    async def run(self, case: ReplayCase) -> ReplayResult:
        ctx = DetectionContext.from_dict(case.context)
        runtime_result = await DetectionRuntime(case.scripts).run(ctx)
        failures = self._check_expectations(runtime_result, case.expectation)
        return ReplayResult(case_id=case.id, runtime_result=runtime_result, failures=failures)

    def _check_expectations(
        self,
        runtime_result: RuntimeResult,
        expectation: ReplayExpectation,
    ) -> list[str]:
        failures: list[str] = []
        results_by_script = {result.script_id: result for result in runtime_result.results}

        for script_id in expectation.expected_passed_scripts:
            result = results_by_script.get(script_id)
            if result is None or not result.passed:
                failures.append(f"expected script {script_id} to pass")

        for script_id, min_score in expectation.min_score_by_script.items():
            result = results_by_script.get(script_id)
            if result is None:
                failures.append(f"expected script {script_id} to have score at least {min_score}, but it did not run")
            elif result.score < min_score:
                failures.append(
                    f"expected script {script_id} to have score at least {min_score}, got {result.score}"
                )

        for script_id, expected_labels in expectation.expected_labels_by_script.items():
            result = results_by_script.get(script_id)
            if result is None:
                failures.append(f"expected script {script_id} to include labels {expected_labels}, but it did not run")
                continue
            missing_labels = [label for label in expected_labels if label not in result.labels]
            if missing_labels:
                failures.append(f"expected script {script_id} to include labels {missing_labels}")

        return failures
