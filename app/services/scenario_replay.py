from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.services.context_intelligence import (
    BoundingBox,
    ContextQueryPlan,
    expanded_bbox,
    query_bundle_fingerprint,
    query_fingerprint,
)
from app.services.context_taxonomy import CATEGORY_ORDER, overpass_filters_for_category
from app.services.day3_artifact import Day3ContextInput


class ScenarioReplayError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ScenarioHotspot:
    context_input: Day3ContextInput
    temperature_celsius: float
    heat_index_celsius: float | None
    apparent_temperature_celsius: float | None
    wet_bulb_temperature_celsius: float | None
    relative_humidity_percent: float | None


@dataclass(frozen=True, slots=True)
class ScenarioReplaySource:
    schema_version: str
    heatmap_artifact_path: str
    heatmap_artifact_sha256: str
    hazard_timestamp: str
    hotspots: tuple[ScenarioHotspot, ...]


def _finite(value: Any, field: str, *, nullable: bool = False) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScenarioReplayError(f"{field} must be numeric{' or null' if nullable else ''}.")
    number = float(value)
    if not math.isfinite(number):
        raise ScenarioReplayError(f"{field} must be finite.")
    return number


def load_scenario_replay_source(path: str | Path, *, hotspot_limit: int = 3) -> ScenarioReplaySource:
    if not 1 <= hotspot_limit <= 10:
        raise ScenarioReplayError("hotspot_limit must be between 1 and 10.")

    artifact_path = Path(path)
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScenarioReplayError(f"Cannot read Day 3 artifact: {artifact_path}") from exc

    if not isinstance(payload, dict) or payload.get("schema_version") != "heatshield.day3.environment.v1":
        raise ScenarioReplayError("Unsupported Day 3 artifact schema.")

    source = payload.get("source")
    enrichments = payload.get("environmental_enrichments")
    if not isinstance(source, dict) or not isinstance(enrichments, list) or not enrichments:
        raise ScenarioReplayError("Day 3 artifact is missing source or enrichments.")

    heatmap_path = source.get("heatmap_artifact_path")
    heatmap_sha = source.get("heatmap_artifact_sha256")
    if not isinstance(heatmap_path, str) or not isinstance(heatmap_sha, str) or len(heatmap_sha) != 64:
        raise ScenarioReplayError("Day 3 heatmap provenance is incomplete.")

    selected = sorted(enrichments, key=lambda item: int(item.get("hotspot_rank", 10**9)))[:hotspot_limit]
    hotspots: list[ScenarioHotspot] = []
    timestamps: list[str] = []
    seen_ranks: set[int] = set()

    for item in selected:
        if not isinstance(item, dict):
            raise ScenarioReplayError("Invalid Day 3 enrichment entry.")
        rank = int(item.get("hotspot_rank"))
        if rank < 1 or rank in seen_ranks:
            raise ScenarioReplayError("Hotspot ranks must be unique positive integers.")
        seen_ranks.add(rank)

        tile_id = item.get("tile_id")
        thermal_id = item.get("thermal_evidence_id")
        environmental_id = item.get("environmental_evidence_id")
        if tile_id is None or not isinstance(thermal_id, str) or not thermal_id or not isinstance(environmental_id, str) or not environmental_id:
            raise ScenarioReplayError("Day 3 enrichment evidence linkage is incomplete.")

        lat = _finite(item.get("representative_latitude"), "representative_latitude")
        lon = _finite(item.get("representative_longitude"), "representative_longitude")
        assert lat is not None and lon is not None
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ScenarioReplayError("Representative coordinate is outside valid range.")

        observed = item.get("observed")
        if not isinstance(observed, dict):
            raise ScenarioReplayError("Day 3 enrichment has no observed environmental object.")
        timestamp = observed.get("timestamp")
        if not isinstance(timestamp, str) or not timestamp:
            raise ScenarioReplayError("Day 3 enrichment has no observed timestamp.")
        try:
            parsed_ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ScenarioReplayError(f"Invalid Day 3 observed timestamp: {timestamp!r}") from exc
        if parsed_ts.tzinfo is None:
            raise ScenarioReplayError("Day 3 observed timestamp must be timezone-aware.")
        timestamps.append(parsed_ts.astimezone(timezone.utc).isoformat())

        hotspots.append(
            ScenarioHotspot(
                context_input=Day3ContextInput(
                    rank=rank,
                    tile_id=tile_id,
                    thermal_evidence_id=thermal_id,
                    environmental_evidence_id=environmental_id,
                    latitude=lat,
                    longitude=lon,
                    observed_timestamp=timestamp,
                ),
                temperature_celsius=float(_finite(observed.get("temperature_celsius"), "temperature_celsius")),
                heat_index_celsius=_finite(observed.get("heat_index_celsius"), "heat_index_celsius", nullable=True),
                apparent_temperature_celsius=_finite(observed.get("apparent_temperature_celsius"), "apparent_temperature_celsius", nullable=True),
                wet_bulb_temperature_celsius=_finite(observed.get("wet_bulb_temperature_celsius"), "wet_bulb_temperature_celsius", nullable=True),
                relative_humidity_percent=_finite(observed.get("relative_humidity_percent"), "relative_humidity_percent", nullable=True),
            )
        )

    if len(set(timestamps)) != 1:
        raise ScenarioReplayError("Selected Day 3 hotspots are not time-aligned.")

    return ScenarioReplaySource(
        schema_version="heatshield.scenario_replay.source.v1",
        heatmap_artifact_path=heatmap_path,
        heatmap_artifact_sha256=heatmap_sha,
        hazard_timestamp=timestamps[0],
        hotspots=tuple(hotspots),
    )


def build_current_context_query_bundle(
    hotspots: Iterable[Day3ContextInput],
    *,
    radius_meters: float,
    timeout_seconds: int = 20,
) -> tuple[tuple[ContextQueryPlan, ...], BoundingBox]:
    """Build five small current-OSM queries without an attic/history date clause."""
    selected = tuple(hotspots)
    if not selected:
        raise ScenarioReplayError("At least one hotspot is required.")
    if not 10 <= timeout_seconds <= 120:
        raise ScenarioReplayError("timeout_seconds must be between 10 and 120.")

    bbox = expanded_bbox(((item.latitude, item.longitude) for item in selected), radius_meters)
    plans: list[ContextQueryPlan] = []
    for category in CATEGORY_ORDER:
        filters = "\n  ".join(overpass_filters_for_category(category))
        query = (
            f'[out:json][timeout:{timeout_seconds}][bbox:{bbox.as_overpass()}];\n'
            "(\n"
            f"  {filters}\n"
            ");\n"
            "out center tags qt;"
        )
        plans.append(ContextQueryPlan(category=category, query=query, query_sha256=query_fingerprint(query)))
    return tuple(plans), bbox


def scenario_query_bundle_sha256(plans: Iterable[ContextQueryPlan]) -> str:
    return query_bundle_fingerprint(plans)


def coverage_status(category_status: dict[str, str]) -> str:
    observed = sum(1 for category in CATEGORY_ORDER if category_status.get(category) == "observed")
    if observed == len(CATEGORY_ORDER):
        return "complete"
    if observed == 0:
        return "unavailable"
    return "partial"


def temporal_gap_days(*, hazard_timestamp: str, context_timestamp_utc: str) -> float:
    try:
        hazard = datetime.fromisoformat(hazard_timestamp.replace("Z", "+00:00"))
        context = datetime.fromisoformat(context_timestamp_utc.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ScenarioReplayError("Invalid scenario timestamp.") from exc
    if hazard.tzinfo is None or context.tzinfo is None:
        raise ScenarioReplayError("Scenario timestamps must be timezone-aware.")
    return round((context.astimezone(timezone.utc) - hazard.astimezone(timezone.utc)).total_seconds() / 86400.0, 3)
