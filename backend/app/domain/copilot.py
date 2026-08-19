from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ALLOWED_INTENTS = {
    "summary",
    "why_priority",
    "recommendations",
    "missing_evidence",
    "compare_hotspots",
    "metric_lookup",
    "scenario_scope",
    "unsupported",
}


@dataclass(frozen=True, slots=True)
class CopilotPlan:
    intent: str
    primary_hotspot_rank: int | None = None
    comparison_hotspot_ranks: tuple[int, ...] = ()
    metric_keys: tuple[str, ...] = ()
    recommendation_ids: tuple[str, ...] = ()
    planner: str = "deterministic"

    def to_dict(self) -> dict[str, Any]:
        if self.intent not in ALLOWED_INTENTS:
            raise ValueError(f"Unsupported copilot intent: {self.intent}")
        return {
            "intent": self.intent,
            "primary_hotspot_rank": self.primary_hotspot_rank,
            "comparison_hotspot_ranks": list(self.comparison_hotspot_ranks),
            "metric_keys": list(self.metric_keys),
            "recommendation_ids": list(self.recommendation_ids),
            "planner": self.planner,
        }


@dataclass(frozen=True, slots=True)
class GroundedClaim:
    hotspot_rank: int
    claim_type: str
    metric_key: str | None
    claimed_value: Any
    status: str | None
    statement: str | None
    guard_reason_code: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "hotspot_rank": self.hotspot_rank,
            "claim_type": self.claim_type,
            "metric_key": self.metric_key,
            "claimed_value": self.claimed_value,
            "status": self.status,
            "statement": self.statement,
            "guard_reason_code": self.guard_reason_code,
        }
