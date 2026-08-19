from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class StructuredClaimRequest(BaseModel):
    hotspot_rank: int = Field(ge=1)
    claim_type: Literal["metric_assertion", "status_assertion", "scenario_statement"]
    metric_key: str | None = None
    claimed_value: Any = None
    status: Literal["observed", "derived", "unknown", "withheld"] | None = None
    statement: str | None = None


class NaturalLanguageScreenRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
