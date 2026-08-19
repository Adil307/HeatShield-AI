from __future__ import annotations

import hashlib
import json
from typing import Any

from app.domain.environment import EnvironmentalEnrichment, EnvironmentalObservation


CORE_METRICS = (
    "heat_index_celsius",
    "apparent_temperature_celsius",
    "wet_bulb_temperature_celsius",
)


def request_fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def environmental_evidence_id(
    *,
    thermal_evidence_id: str,
    activity_id: str | None,
    request_hash: str,
) -> str:
    payload = f"fortyguard-env|{thermal_evidence_id}|{activity_id or 'unknown'}|{request_hash}"
    return "hs_env_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def build_environmental_enrichment(
    *,
    hotspot_rank: int,
    tile_id: int | str,
    thermal_evidence_id: str,
    request_hash: str,
    representative_latitude: float,
    representative_longitude: float,
    activity_id: str | None,
    observation: EnvironmentalObservation,
) -> EnvironmentalEnrichment:
    available = sum(
        value is not None
        for value in (
            observation.heat_index_celsius,
            observation.apparent_temperature_celsius,
            observation.wet_bulb_temperature_celsius,
        )
    )

    return EnvironmentalEnrichment(
        hotspot_rank=hotspot_rank,
        tile_id=tile_id,
        thermal_evidence_id=thermal_evidence_id,
        environmental_evidence_id=environmental_evidence_id(
            thermal_evidence_id=thermal_evidence_id,
            activity_id=activity_id,
            request_hash=request_hash,
        ),
        request_fingerprint=request_hash,
        representative_latitude=representative_latitude,
        representative_longitude=representative_longitude,
        observed=observation,
        apparent_minus_air_celsius=(
            None
            if observation.apparent_temperature_celsius is None
            else observation.apparent_temperature_celsius - observation.temperature_celsius
        ),
        heat_index_minus_air_celsius=(
            None
            if observation.heat_index_celsius is None
            else observation.heat_index_celsius - observation.temperature_celsius
        ),
        core_metric_completeness=available / len(CORE_METRICS),
    )
