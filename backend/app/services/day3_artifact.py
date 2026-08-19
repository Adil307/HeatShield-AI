from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


class Day3ArtifactError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Day3ContextInput:
    rank: int
    tile_id: int | str
    thermal_evidence_id: str
    environmental_evidence_id: str
    latitude: float
    longitude: float
    observed_timestamp: str | None


@dataclass(frozen=True, slots=True)
class Day3Artifact:
    heatmap_artifact_path: str
    heatmap_artifact_sha256: str
    source_start_date: str | None
    source_start_time: str | None
    hotspots: tuple[Day3ContextInput, ...]


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Day3ArtifactError(f"{field} must be numeric.")
    number = float(value)
    if not math.isfinite(number):
        raise Day3ArtifactError(f"{field} must be finite.")
    return number


def load_day3_artifact(path: str | Path) -> Day3Artifact:
    artifact_path = Path(path)
    if not artifact_path.exists():
        raise Day3ArtifactError(f"Day 3 artifact not found: {artifact_path}")

    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Day3ArtifactError(f"Invalid Day 3 JSON: {artifact_path}") from exc

    if not isinstance(payload, dict) or payload.get("schema_version") != "heatshield.day3.environment.v1":
        raise Day3ArtifactError("Unsupported or missing Day 3 schema_version.")

    source = payload.get("source")
    items = payload.get("environmental_enrichments")
    if not isinstance(source, dict) or not isinstance(items, list) or not items:
        raise Day3ArtifactError("Day 3 artifact is missing source/environmental_enrichments.")

    heatmap_path = source.get("heatmap_artifact_path")
    heatmap_hash = source.get("heatmap_artifact_sha256")
    if not isinstance(heatmap_path, str) or not isinstance(heatmap_hash, str) or len(heatmap_hash) != 64:
        raise Day3ArtifactError("Day 3 heatmap provenance is incomplete.")

    source_date_time = source.get("date_time")
    start_date = source_date_time.get("start_date") if isinstance(source_date_time, dict) else None
    start_time = source_date_time.get("start_time") if isinstance(source_date_time, dict) else None

    hotspots: list[Day3ContextInput] = []
    seen_ranks: set[int] = set()
    seen_tiles: set[str] = set()

    for item in items:
        if not isinstance(item, dict):
            raise Day3ArtifactError("Invalid environmental enrichment entry.")

        rank = int(item.get("hotspot_rank"))
        tile_id = item.get("tile_id")
        tile_key = str(tile_id)
        if rank < 1 or rank in seen_ranks:
            raise Day3ArtifactError("Day 3 hotspot ranks must be unique positive integers.")
        if tile_id is None or tile_key in seen_tiles:
            raise Day3ArtifactError("Day 3 tile IDs must be present and unique.")
        seen_ranks.add(rank)
        seen_tiles.add(tile_key)

        thermal_id = item.get("thermal_evidence_id")
        environmental_id = item.get("environmental_evidence_id")
        if not isinstance(thermal_id, str) or not thermal_id:
            raise Day3ArtifactError("Missing thermal evidence ID.")
        if not isinstance(environmental_id, str) or not environmental_id:
            raise Day3ArtifactError("Missing environmental evidence ID.")

        lat = _finite(item.get("representative_latitude"), "representative_latitude")
        lon = _finite(item.get("representative_longitude"), "representative_longitude")
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise Day3ArtifactError("Representative coordinates are outside valid ranges.")

        observed = item.get("observed")
        timestamp = observed.get("timestamp") if isinstance(observed, dict) else None
        if timestamp is not None and not isinstance(timestamp, str):
            raise Day3ArtifactError("Observed timestamp must be a string or null.")

        hotspots.append(
            Day3ContextInput(
                rank=rank,
                tile_id=tile_id,
                thermal_evidence_id=thermal_id,
                environmental_evidence_id=environmental_id,
                latitude=lat,
                longitude=lon,
                observed_timestamp=timestamp,
            )
        )

    hotspots.sort(key=lambda item: item.rank)
    return Day3Artifact(
        heatmap_artifact_path=heatmap_path,
        heatmap_artifact_sha256=heatmap_hash,
        source_start_date=start_date if isinstance(start_date, str) else None,
        source_start_time=start_time if isinstance(start_time, str) else None,
        hotspots=tuple(hotspots),
    )


def resolve_osm_snapshot_utc(artifact: Day3Artifact) -> tuple[datetime, str]:
    parsed: list[datetime] = []
    for hotspot in artifact.hotspots:
        if not hotspot.observed_timestamp:
            continue
        try:
            value = datetime.fromisoformat(hotspot.observed_timestamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        if value.tzinfo is None:
            continue
        parsed.append(value.astimezone(timezone.utc))

    if parsed:
        spread = (max(parsed) - min(parsed)).total_seconds()
        if spread <= 300:
            return min(parsed), "provider_observed_timestamp"

    if artifact.source_start_date and artifact.source_start_time:
        try:
            fallback = datetime.fromisoformat(
                f"{artifact.source_start_date}T{artifact.source_start_time}:00+00:00"
            )
        except ValueError as exc:
            raise Day3ArtifactError("Cannot resolve a valid Day 3 source timestamp.") from exc
        return fallback.astimezone(timezone.utc), "source_date_time_assumed_utc"

    raise Day3ArtifactError("Day 3 contains no usable timestamp for historical OSM alignment.")
