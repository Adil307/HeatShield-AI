from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class Day44ArtifactError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Day44HotspotInput:
    hotspot_rank: int
    tile_id: int | str
    thermal_evidence_id: str
    environmental_evidence_id: str
    context_evidence_id: str
    heat_index_celsius: float | None
    apparent_temperature_celsius: float | None
    wet_bulb_temperature_celsius: float | None
    temperature_celsius: float
    relative_humidity_percent: float | None
    category_counts: dict[str, int]
    category_status: dict[str, str]
    radius_meters: float


@dataclass(frozen=True, slots=True)
class Day44PrioritySource:
    schema_version: str
    artifact_path: str
    mode: str
    scenario_statement: str
    context_coverage_status: str
    hazard_timestamp_utc: str
    context_timestamp_utc: str
    temporal_gap_days: float
    hotspots: tuple[Day44HotspotInput, ...]


def _finite_number(value: Any, field: str, *, nullable: bool = False) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Day44ArtifactError(f"{field} must be numeric{' or null' if nullable else ''}.")
    number = float(value)
    if not math.isfinite(number):
        raise Day44ArtifactError(f"{field} must be finite.")
    return number


def load_day44_priority_source(path: str | Path) -> Day44PrioritySource:
    artifact_path = Path(path)
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Day44ArtifactError(f"Cannot read Day 4.4 artifact: {artifact_path}") from exc

    if not isinstance(payload, dict) or payload.get("schema_version") != "heatshield.day4_4.scenario_replay.v1":
        raise Day44ArtifactError("Unsupported Day 4.4 scenario-replay artifact schema.")

    mode = payload.get("mode")
    statement = payload.get("scenario_statement")
    provenance = payload.get("provenance")
    context = payload.get("context")
    hotspots_raw = payload.get("hotspots")

    if mode != "historical_hazard_current_context_scenario_replay":
        raise Day44ArtifactError("Day 5 only accepts the explicit Day 4.4 scenario-replay mode.")
    if not isinstance(statement, str) or not statement.strip():
        raise Day44ArtifactError("Scenario statement is missing.")
    if not isinstance(provenance, dict) or not isinstance(context, dict) or not isinstance(hotspots_raw, list):
        raise Day44ArtifactError("Day 4.4 artifact is missing provenance, context, or hotspots.")

    coverage = context.get("coverage_status")
    if coverage != "complete":
        raise Day44ArtifactError(
            "Day 5 requires complete mapped-context coverage. Partial/unavailable context must not be scored as zero."
        )

    hazard_ts = provenance.get("hazard_observed_timestamp_utc")
    context_ts = provenance.get("current_context_fetched_at_utc")
    gap = _finite_number(provenance.get("temporal_gap_days"), "temporal_gap_days")
    if not isinstance(hazard_ts, str) or not hazard_ts or not isinstance(context_ts, str) or not context_ts:
        raise Day44ArtifactError("Scenario provenance timestamps are incomplete.")
    assert gap is not None
    if gap < 0:
        raise Day44ArtifactError("Scenario temporal gap cannot be negative.")

    category_status_global = context.get("category_status")
    if not isinstance(category_status_global, dict):
        raise Day44ArtifactError("Global context category status is missing.")
    if any(value != "observed" for value in category_status_global.values()):
        raise Day44ArtifactError("All Day 4.4 context categories must be observed before priority scoring.")

    hotspots: list[Day44HotspotInput] = []
    seen_ranks: set[int] = set()
    for item in hotspots_raw:
        if not isinstance(item, dict):
            raise Day44ArtifactError("Invalid hotspot entry.")
        rank = item.get("hotspot_rank")
        if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1 or rank in seen_ranks:
            raise Day44ArtifactError("Hotspot ranks must be unique positive integers.")
        seen_ranks.add(rank)

        tile_id = item.get("tile_id")
        thermal_id = item.get("thermal_evidence_id")
        env_id = item.get("environmental_evidence_id")
        ctx_id = item.get("context_evidence_id")
        if tile_id is None or not all(isinstance(v, str) and v for v in (thermal_id, env_id, ctx_id)):
            raise Day44ArtifactError("Hotspot evidence linkage is incomplete.")

        hazard = item.get("historical_hazard")
        current_context = item.get("current_context")
        if not isinstance(hazard, dict) or not isinstance(current_context, dict):
            raise Day44ArtifactError("Hotspot hazard/context sections are missing.")

        counts_raw = current_context.get("category_counts")
        statuses_raw = current_context.get("category_status")
        if not isinstance(counts_raw, dict) or not isinstance(statuses_raw, dict):
            raise Day44ArtifactError("Hotspot category counts/status are missing.")

        counts: dict[str, int] = {}
        statuses: dict[str, str] = {}
        for category, status in statuses_raw.items():
            if not isinstance(category, str) or not isinstance(status, str):
                raise Day44ArtifactError("Invalid category status entry.")
            statuses[category] = status
            count = counts_raw.get(category)
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise Day44ArtifactError(f"Invalid count for category {category!r}.")
            if status != "observed":
                raise Day44ArtifactError(
                    f"Category {category!r} is {status!r}; unknown context must never be treated as zero."
                )
            counts[category] = count

        radius = _finite_number(current_context.get("radius_meters"), "radius_meters")
        temp = _finite_number(hazard.get("temperature_celsius"), "temperature_celsius")
        assert radius is not None and temp is not None
        if radius <= 0:
            raise Day44ArtifactError("Context radius must be positive.")

        hotspots.append(
            Day44HotspotInput(
                hotspot_rank=rank,
                tile_id=tile_id,
                thermal_evidence_id=thermal_id,
                environmental_evidence_id=env_id,
                context_evidence_id=ctx_id,
                heat_index_celsius=_finite_number(hazard.get("heat_index_celsius"), "heat_index_celsius", nullable=True),
                apparent_temperature_celsius=_finite_number(
                    hazard.get("apparent_temperature_celsius"), "apparent_temperature_celsius", nullable=True
                ),
                wet_bulb_temperature_celsius=_finite_number(
                    hazard.get("wet_bulb_temperature_celsius"), "wet_bulb_temperature_celsius", nullable=True
                ),
                temperature_celsius=temp,
                relative_humidity_percent=_finite_number(
                    hazard.get("relative_humidity_percent"), "relative_humidity_percent", nullable=True
                ),
                category_counts=counts,
                category_status=statuses,
                radius_meters=radius,
            )
        )

    if not hotspots:
        raise Day44ArtifactError("Day 4.4 artifact contains no hotspots.")

    return Day44PrioritySource(
        schema_version="heatshield.day5.priority_source.v1",
        artifact_path=str(artifact_path),
        mode=mode,
        scenario_statement=statement,
        context_coverage_status=coverage,
        hazard_timestamp_utc=hazard_ts,
        context_timestamp_utc=context_ts,
        temporal_gap_days=gap,
        hotspots=tuple(sorted(hotspots, key=lambda h: h.hotspot_rank)),
    )
