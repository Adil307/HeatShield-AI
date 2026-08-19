from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ALLOWED_CLASSIFICATIONS = {"observed", "derived", "unknown", "withheld"}


@dataclass(frozen=True, slots=True)
class EvidenceLedgerEntry:
    key: str
    label: str
    classification: str
    value: Any
    unit: str | None
    source_artifact: str
    source_evidence_id: str | None
    status: str
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        if self.classification not in ALLOWED_CLASSIFICATIONS:
            raise ValueError(f"Unsupported evidence classification: {self.classification}")
        return {
            "key": self.key,
            "label": self.label,
            "classification": self.classification,
            "value": self.value,
            "unit": self.unit,
            "source_artifact": self.source_artifact,
            "source_evidence_id": self.source_evidence_id,
            "status": self.status,
            "explanation": self.explanation,
        }


@dataclass(frozen=True, slots=True)
class Contribution:
    component: str
    raw_score: float
    weight: float
    weighted_points: float

    def to_dict(self) -> dict[str, float | str]:
        return {
            "component": self.component,
            "raw_score": self.raw_score,
            "weight": self.weight,
            "weighted_points": self.weighted_points,
        }


@dataclass(frozen=True, slots=True)
class ExplainabilityPacket:
    packet_id: str
    hotspot_rank: int
    tile_id: int | str
    scenario_scope: str
    scenario_statement: str
    temporal_gap_days: float
    pre_adaptation_priority_score: float
    pre_adaptation_priority_band: str
    evidence_adjusted_priority_score: float | None
    evidence_adjusted_priority_band: str | None
    evidence_complete: bool
    contributions: tuple[Contribution, ...]
    evidence_ledger: tuple[EvidenceLedgerEntry, ...]
    unknowns: tuple[str, ...]
    withheld: tuple[str, ...]
    explanation: tuple[str, ...]
    guardrails: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "packet_id": self.packet_id,
            "hotspot_rank": self.hotspot_rank,
            "tile_id": self.tile_id,
            "scenario_scope": self.scenario_scope,
            "scenario_statement": self.scenario_statement,
            "temporal_gap_days": self.temporal_gap_days,
            "pre_adaptation_priority_score": self.pre_adaptation_priority_score,
            "pre_adaptation_priority_band": self.pre_adaptation_priority_band,
            "evidence_adjusted_priority_score": self.evidence_adjusted_priority_score,
            "evidence_adjusted_priority_band": self.evidence_adjusted_priority_band,
            "evidence_complete": self.evidence_complete,
            "contributions": [item.to_dict() for item in self.contributions],
            "evidence_ledger": [item.to_dict() for item in self.evidence_ledger],
            "unknowns": list(self.unknowns),
            "withheld": list(self.withheld),
            "explanation": list(self.explanation),
            "guardrails": list(self.guardrails),
        }
