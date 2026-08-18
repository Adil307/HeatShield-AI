from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PriorityComponents:
    hazard_score: float
    mapped_exposure_score: float
    context_sensitivity_proxy: float
    verified_vulnerability_score: float | None = None
    verified_adaptive_capacity_score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PriorityResult:
    hotspot_rank: int
    tile_id: int | str
    priority_evidence_id: str
    heat_index_band: str
    pre_adaptation_priority_score: float
    pre_adaptation_priority_band: str
    final_priority_score: float | None
    final_priority_band: str | None
    components: PriorityComponents
    evidence_status: dict[str, str]
    factor_explanations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "hotspot_rank": self.hotspot_rank,
            "tile_id": self.tile_id,
            "priority_evidence_id": self.priority_evidence_id,
            "heat_index_band": self.heat_index_band,
            "pre_adaptation_priority_score": self.pre_adaptation_priority_score,
            "pre_adaptation_priority_band": self.pre_adaptation_priority_band,
            "final_priority_score": self.final_priority_score,
            "final_priority_band": self.final_priority_band,
            "components": self.components.to_dict(),
            "evidence_status": dict(self.evidence_status),
            "factor_explanations": list(self.factor_explanations),
        }
