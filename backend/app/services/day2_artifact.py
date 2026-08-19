from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class Day2ArtifactError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Day2Hotspot:
    rank: int
    tile_id: int | str
    average_temperature: float
    evidence_id: str
    geometry: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Day2Artifact:
    source_artifact_path: str
    source_artifact_sha256: str
    hotspots: tuple[Day2Hotspot, ...]


def load_day2_artifact(path: str | Path) -> Day2Artifact:
    artifact_path = Path(path)
    if not artifact_path.exists():
        raise Day2ArtifactError(f"Day 2 artifact not found: {artifact_path}")

    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Day2ArtifactError(f"Invalid Day 2 JSON: {artifact_path}") from exc

    if not isinstance(payload, dict) or payload.get("schema_version") != "heatshield.day2.hotspot.v1":
        raise Day2ArtifactError("Unsupported or missing Day 2 schema_version.")

    source = payload.get("source")
    analysis = payload.get("hotspot_analysis")
    if not isinstance(source, dict) or not isinstance(analysis, dict):
        raise Day2ArtifactError("Day 2 artifact is missing source/hotspot_analysis objects.")

    source_path = source.get("artifact_path")
    source_hash = source.get("artifact_sha256")
    if not isinstance(source_path, str) or not isinstance(source_hash, str) or len(source_hash) != 64:
        raise Day2ArtifactError("Day 2 source provenance is incomplete.")

    candidates = analysis.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise Day2ArtifactError("Day 2 artifact contains no hotspot candidates.")

    hotspots: list[Day2Hotspot] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise Day2ArtifactError("Invalid hotspot candidate entry.")
        geometry = candidate.get("geometry")
        if not isinstance(geometry, dict):
            raise Day2ArtifactError("Hotspot candidate has no geometry object.")
        hotspots.append(
            Day2Hotspot(
                rank=int(candidate["rank"]),
                tile_id=candidate["tile_id"],
                average_temperature=float(candidate["average_temperature"]),
                evidence_id=str(candidate["evidence_id"]),
                geometry=geometry,
            )
        )

    hotspots.sort(key=lambda item: item.rank)
    return Day2Artifact(
        source_artifact_path=source_path,
        source_artifact_sha256=source_hash,
        hotspots=tuple(hotspots),
    )
