from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ALLOWED_PRIORITY_TIERS = {"P1", "P2", "P3"}
ALLOWED_STATUSES = {
    "ready_for_verification",
    "ready_for_assessment",
    "conditional_requires_operator_scope",
}


@dataclass(frozen=True, slots=True)
class TriggerEvidence:
    key: str
    classification: str
    value: Any
    unit: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "classification": self.classification,
            "value": self.value,
            "unit": self.unit,
        }


@dataclass(frozen=True, slots=True)
class ControlledRecommendation:
    recommendation_id: str
    action_id: str
    title: str
    action_type: str
    priority_tier: str
    status: str
    recommendation: str
    why: str
    trigger_evidence: tuple[TriggerEvidence, ...]
    required_verification: tuple[str, ...]
    limitations: tuple[str, ...]
    authoritative_basis: tuple[str, ...]
    guard_status: str

    def to_dict(self) -> dict[str, Any]:
        if self.priority_tier not in ALLOWED_PRIORITY_TIERS:
            raise ValueError(f"Unsupported recommendation priority tier: {self.priority_tier}")
        if self.status not in ALLOWED_STATUSES:
            raise ValueError(f"Unsupported recommendation status: {self.status}")
        return {
            "recommendation_id": self.recommendation_id,
            "action_id": self.action_id,
            "title": self.title,
            "action_type": self.action_type,
            "priority_tier": self.priority_tier,
            "status": self.status,
            "recommendation": self.recommendation,
            "why": self.why,
            "trigger_evidence": [item.to_dict() for item in self.trigger_evidence],
            "required_verification": list(self.required_verification),
            "limitations": list(self.limitations),
            "authoritative_basis": list(self.authoritative_basis),
            "guard_status": self.guard_status,
        }
