from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from detection.context import DetectionContext
from detection.result import DetectionResult
from detection.script import DetectionScript


@dataclass
class StrategyPack:
    id: str
    version: str
    scripts: list[DetectionScript]
    name: str = ""
    description: str = ""


@dataclass
class RuntimeResult:
    strategy_id: str = ""
    results: list[DetectionResult] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.errors

    @property
    def alert_candidates(self) -> list[DetectionResult]:
        return [result for result in self.results if result.passed]


class DetectionRuntime:
    def __init__(self, scripts: list[DetectionScript], strategy_id: str = "") -> None:
        self.scripts = scripts
        self.strategy_id = strategy_id

    @classmethod
    def from_pack(cls, pack: StrategyPack) -> "DetectionRuntime":
        return cls(pack.scripts, strategy_id=pack.id)

    async def run(self, ctx: DetectionContext) -> RuntimeResult:
        runtime_result = RuntimeResult(strategy_id=self.strategy_id)
        for script in self.scripts:
            result, error = await self._run_script(script, ctx)
            if result is not None:
                runtime_result.results.append(result)
            if error is not None:
                runtime_result.errors.append(error)
        return runtime_result

    async def _run_script(
        self,
        script: DetectionScript,
        ctx: DetectionContext,
    ) -> tuple[DetectionResult | None, dict[str, Any] | None]:
        missing_inputs = script.missing_inputs(ctx)
        if missing_inputs:
            return None, {
                "script_id": script.id,
                "missing_inputs": missing_inputs,
                "error": "Missing required inputs",
            }

        try:
            result = await script.detect(ctx)
        except Exception as exc:
            return None, {"script_id": script.id, "error": str(exc)}

        result.strategy_id = self.strategy_id
        return result, None
