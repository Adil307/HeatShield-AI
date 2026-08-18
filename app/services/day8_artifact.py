from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class Day8ArtifactError(ValueError):
    pass


EXPECTED_SCHEMA = "heatshield.day8.controlled_recommendations.v1"
EXPECTED_SCOPE = "controlled_evidence_triggered_scenario_planning_actions_not_medical_advice"


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Day8ArtifactError(f"Cannot read Day 8 artifact: {path}") from exc
    if not isinstance(payload, dict):
        raise Day8ArtifactError("Day 8 artifact must contain a JSON object.")
    return payload


@dataclass(frozen=True, slots=True)
class Day8Source:
    path: Path
    sha256: str
    payload: dict[str, Any]
    hotspots: tuple[dict[str, Any], ...]
    recommendation_ids: frozenset[str]


def load_day8_source(
    path: str | Path,
    *,
    day7_path: str | Path | None = None,
    catalog_path: str | Path | None = None,
) -> Day8Source:
    artifact_path = Path(path)
    payload = _read_json(artifact_path)
    if payload.get("schema_version") != EXPECTED_SCHEMA:
        raise Day8ArtifactError("Unsupported Day 8 artifact schema.")
    if payload.get("scope") != EXPECTED_SCOPE:
        raise Day8ArtifactError("Unsupported Day 8 artifact scope.")

    source = payload.get("source")
    if not isinstance(source, dict):
        raise Day8ArtifactError("Day 8 source metadata is missing.")

    checks = (
        (day7_path, "day7_artifact_sha256", "Day 8 -> Day 7"),
        (catalog_path, "action_catalog_sha256", "Day 8 -> action catalog"),
    )
    for current_path, hash_key, label in checks:
        if current_path is None:
            continue
        expected = source.get(hash_key)
        if not isinstance(expected, str) or len(expected) != 64:
            raise Day8ArtifactError(f"{label} provenance hash is missing.")
        if file_sha256(current_path) != expected:
            raise Day8ArtifactError(f"{label} SHA-256 provenance mismatch.")

    hotspots = payload.get("hotspots")
    if not isinstance(hotspots, list) or not hotspots:
        raise Day8ArtifactError("Day 8 recommendation hotspots are missing.")

    ranks: set[int] = set()
    rec_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for hotspot in hotspots:
        if not isinstance(hotspot, dict):
            raise Day8ArtifactError("Day 8 hotspots must be objects.")
        rank = hotspot.get("hotspot_rank")
        if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1 or rank in ranks:
            raise Day8ArtifactError("Day 8 hotspot ranks must be unique positive integers.")
        ranks.add(rank)
        recommendations = hotspot.get("recommendations")
        if not isinstance(recommendations, list):
            raise Day8ArtifactError(f"Recommendations missing for hotspot_rank={rank}.")
        for rec in recommendations:
            if not isinstance(rec, dict):
                raise Day8ArtifactError("Recommendations must be objects.")
            rec_id = rec.get("recommendation_id")
            if not isinstance(rec_id, str) or not rec_id or rec_id in rec_ids:
                raise Day8ArtifactError("Recommendation IDs must be unique non-empty strings.")
            if rec.get("guard_status") != "approved_controlled_catalog_action":
                raise Day8ArtifactError(f"Recommendation {rec_id} is not guard-approved.")
            rec_ids.add(rec_id)
        normalized.append(hotspot)

    return Day8Source(
        path=artifact_path,
        sha256=file_sha256(artifact_path),
        payload=payload,
        hotspots=tuple(normalized),
        recommendation_ids=frozenset(rec_ids),
    )
