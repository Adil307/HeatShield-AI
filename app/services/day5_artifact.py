from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class Day5ArtifactError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Day5PriorityInput:
    hotspot_rank: int
    tile_id: int | str
    priority_evidence_id: str
    pre_adaptation_priority_score: float
    pre_adaptation_priority_band: str


@dataclass(frozen=True, slots=True)
class Day5EvidenceSource:
    schema_version: str
    artifact_path: str
    scope: str
    day44_sha256: str
    priority_results: tuple[Day5PriorityInput, ...]


def _finite_0_100(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Day5ArtifactError(f"{field} must be numeric.")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 100.0:
        raise Day5ArtifactError(f"{field} must be finite and in [0, 100].")
    return number


def load_day5_evidence_source(path: str | Path) -> Day5EvidenceSource:
    artifact_path = Path(path)
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Day5ArtifactError(f"Cannot read Day 5 artifact: {artifact_path}") from exc

    if not isinstance(payload, dict) or payload.get("schema_version") != "heatshield.day5.planning_priority.v1":
        raise Day5ArtifactError("Unsupported Day 5 planning-priority artifact schema.")
    scope = payload.get("scope")
    if scope != "scenario_planning_priority_not_medical_risk":
        raise Day5ArtifactError("Day 6 only accepts the explicit non-medical Day 5 planning-priority scope.")

    source = payload.get("source")
    results_raw = payload.get("priority_results")
    if not isinstance(source, dict) or not isinstance(results_raw, list) or not results_raw:
        raise Day5ArtifactError("Day 5 artifact is missing source metadata or priority results.")

    day44_sha = source.get("day44_artifact_sha256")
    if not isinstance(day44_sha, str) or len(day44_sha) != 64:
        raise Day5ArtifactError("Day 5 source provenance SHA-256 is missing or invalid.")

    parsed: list[Day5PriorityInput] = []
    seen_ranks: set[int] = set()
    seen_tiles: set[str] = set()
    for index, item in enumerate(results_raw):
        if not isinstance(item, dict):
            raise Day5ArtifactError(f"priority_results[{index}] must be an object.")
        rank = item.get("hotspot_rank")
        tile = item.get("tile_id")
        evidence_id = item.get("priority_evidence_id")
        band = item.get("pre_adaptation_priority_band")
        if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
            raise Day5ArtifactError(f"priority_results[{index}].hotspot_rank is invalid.")
        if tile is None or isinstance(tile, bool):
            raise Day5ArtifactError(f"priority_results[{index}].tile_id is invalid.")
        if not isinstance(evidence_id, str) or not evidence_id.startswith("hs_priority_"):
            raise Day5ArtifactError(f"priority_results[{index}].priority_evidence_id is invalid.")
        if not isinstance(band, str) or not band:
            raise Day5ArtifactError(f"priority_results[{index}].pre_adaptation_priority_band is invalid.")
        if rank in seen_ranks or str(tile) in seen_tiles:
            raise Day5ArtifactError("Duplicate hotspot rank or tile ID found in Day 5 artifact.")
        seen_ranks.add(rank)
        seen_tiles.add(str(tile))
        parsed.append(
            Day5PriorityInput(
                hotspot_rank=rank,
                tile_id=tile,
                priority_evidence_id=evidence_id,
                pre_adaptation_priority_score=_finite_0_100(
                    item.get("pre_adaptation_priority_score"),
                    f"priority_results[{index}].pre_adaptation_priority_score",
                ),
                pre_adaptation_priority_band=band,
            )
        )

    return Day5EvidenceSource(
        schema_version=payload["schema_version"],
        artifact_path=str(artifact_path),
        scope=scope,
        day44_sha256=day44_sha,
        priority_results=tuple(parsed),
    )
