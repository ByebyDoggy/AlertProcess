from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from detection.context import DetectionContext
from detection.result import DetectionResult


class DetectionScript(ABC):
    id: str = ""
    version: str = ""
    name: str = ""
    description: str = ""
    required_inputs: Sequence[str] = ()
    default_threshold: float = 40.0

    def missing_inputs(self, ctx: DetectionContext) -> list[str]:
        return ctx.missing_inputs(self.required_inputs)

    @abstractmethod
    async def detect(self, ctx: DetectionContext) -> DetectionResult:
        raise NotImplementedError
