from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

DetectionSeverity = Literal["UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"]


def _clamp_score(score: float) -> float:
    return max(0.0, min(100.0, float(score)))


def score_to_severity(score: float) -> DetectionSeverity:
    score = _clamp_score(score)
    if score <= 0:
        return "UNKNOWN"
    if score < 40:
        return "LOW"
    if score < 70:
        return "MEDIUM"
    if score < 90:
        return "HIGH"
    return "CRITICAL"


@dataclass
class DetectionEvidence:
    kind: str
    description: str = ""
    weight: float = 0.0
    data: dict[str, Any] = field(default_factory=dict)
    source: str = "script"

    def __post_init__(self) -> None:
        self.weight = _clamp_score(self.weight)


@dataclass
class DetectionResult:
    script_id: str
    strategy_id: str = ""
    score: float = 0.0
    passed: bool = False
    severity: DetectionSeverity = "UNKNOWN"
    attack_type: str = ""
    labels: list[str] = field(default_factory=list)
    evidence: list[DetectionEvidence] = field(default_factory=list)
    entities: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.score = _clamp_score(self.score)

    @classmethod
    def no_match(cls, script_id: str, reason: str, attack_type: str = "") -> "DetectionResult":
        return cls(
            script_id=script_id,
            score=0.0,
            passed=False,
            severity="UNKNOWN",
            attack_type=attack_type,
            summary=reason,
            details={"reason": reason},
        )

    @classmethod
    def from_score(
        cls,
        script_id: str,
        score: float,
        threshold: float,
        attack_type: str,
        strategy_id: str = "",
        labels: list[str] | None = None,
        evidence: list[DetectionEvidence] | None = None,
        entities: dict[str, Any] | None = None,
        summary: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> "DetectionResult":
        clamped_score = _clamp_score(score)
        return cls(
            script_id=script_id,
            strategy_id=strategy_id,
            score=clamped_score,
            passed=clamped_score >= threshold,
            severity=score_to_severity(clamped_score),
            attack_type=attack_type,
            labels=labels or [],
            evidence=evidence or [],
            entities=entities or {},
            summary=summary if summary is not None else f"{attack_type} detected by {script_id}",
            details=details or {},
        )
