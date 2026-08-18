from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class EvidenceObservation:
    factor_id: str
    status: str
    level: str | None
    score: float | None
    source_type: str | None
    source_ref: str | None
    observed_at: str | None
    notes: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SiteEvidenceResult:
    hotspot_rank: int
    tile_id: int | str
    priority_evidence_id: str
    evidence_bundle_id: str
    vulnerability_score: float | None
    adaptive_capacity_score: float | None
    vulnerability_completeness: float
    adaptive_capacity_completeness: float
    evidence_complete: bool
    evidence_adjusted_priority_score: float | None
    evidence_adjusted_priority_band: str | None
    adjustment_points: float | None
    medical_risk_score: None
    vulnerability_factors: tuple[EvidenceObservation, ...]
    adaptive_capacity_factors: tuple[EvidenceObservation, ...]
    evidence_status: dict[str, str]
    explanations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "hotspot_rank": self.hotspot_rank,
            "tile_id": self.tile_id,
            "priority_evidence_id": self.priority_evidence_id,
            "evidence_bundle_id": self.evidence_bundle_id,
            "vulnerability_score": self.vulnerability_score,
            "adaptive_capacity_score": self.adaptive_capacity_score,
            "vulnerability_completeness": self.vulnerability_completeness,
            "adaptive_capacity_completeness": self.adaptive_capacity_completeness,
            "evidence_complete": self.evidence_complete,
            "evidence_adjusted_priority_score": self.evidence_adjusted_priority_score,
            "evidence_adjusted_priority_band": self.evidence_adjusted_priority_band,
            "adjustment_points": self.adjustment_points,
            "medical_risk_score": None,
            "vulnerability_factors": [item.to_dict() for item in self.vulnerability_factors],
            "adaptive_capacity_factors": [item.to_dict() for item in self.adaptive_capacity_factors],
            "evidence_status": dict(self.evidence_status),
            "explanations": list(self.explanations),
        }
