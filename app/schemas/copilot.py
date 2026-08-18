from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CopilotAskRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    mode: Literal["auto", "deterministic", "openai"] = "auto"
    hotspot_rank: int | None = Field(default=None, ge=1)
