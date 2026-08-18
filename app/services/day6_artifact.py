from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class Day6ArtifactError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Day6ResultInput:
    hotspot_rank: int
    tile_id: int | str
    priority_evidence_id: str
    evidence_bundle_id: str
    vulnerability_score: float | None
    adaptive_capacity_score: float | None
    vulnerability_completeness: float
    adaptive_capacity_completeness: float
    evidence_complete: bool
    evidence_adjusted_priority_score: float | None
    evidence_adjusted_priority_band: str | None
    medical_risk_score: None


@dataclass(frozen=True, slots=True)
class Day6EvidenceSource:
    artifact_path: str
    artifact_sha256: str
    day5_artifact_path: str
    day5_artifact_sha256: str
    day44_artifact_sha256: str
    scope: str
    all_required_evidence_complete: bool
    results: tuple[Day6ResultInput, ...]


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _optional_0_100(value: Any, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Day6ArtifactError(f"{field} must be numeric or null.")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 100.0:
        raise Day6ArtifactError(f"{field} must be finite and in [0, 100].")
    return number


def _completeness(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Day6ArtifactError(f"{field} must be numeric.")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise Day6ArtifactError(f"{field} must be finite and in [0, 1].")
    return number


def load_day6_evidence_source(path: str | Path) -> Day6EvidenceSource:
    artifact_path = Path(path)
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Day6ArtifactError(f"Cannot read Day 6 artifact: {artifact_path}") from exc

    if not isinstance(payload, dict) or payload.get("schema_version") != "heatshield.day6.evidence_layer.v1":
        raise Day6ArtifactError("Unsupported Day 6 evidence-layer artifact schema.")
    if payload.get("scope") != "verified_operational_evidence_layer_not_medical_risk":
        raise Day6ArtifactError("Day 7 only accepts the explicit non-medical Day 6 evidence scope.")

    source = payload.get("source")
    results_raw = payload.get("results")
    all_complete = payload.get("all_required_evidence_complete")
    if not isinstance(source, dict) or not isinstance(results_raw, list) or not results_raw:
        raise Day6ArtifactError("Day 6 source metadata or results are missing.")
    if not isinstance(all_complete, bool):
        raise Day6ArtifactError("Day 6 all_required_evidence_complete must be boolean.")

    day5_path = source.get("day5_artifact_path")
    day5_sha = source.get("day5_artifact_sha256")
    day44_sha = source.get("day5_source_day44_sha256")
    if not isinstance(day5_path, str) or not day5_path:
        raise Day6ArtifactError("Day 6 source Day 5 path is missing.")
    if not isinstance(day5_sha, str) or len(day5_sha) != 64:
        raise Day6ArtifactError("Day 6 source Day 5 SHA-256 is invalid.")
    if not isinstance(day44_sha, str) or len(day44_sha) != 64:
        raise Day6ArtifactError("Day 6 source Day 4.4 SHA-256 is invalid.")

    parsed: list[Day6ResultInput] = []
    seen_ranks: set[int] = set()
    for index, item in enumerate(results_raw):
        if not isinstance(item, dict):
            raise Day6ArtifactError(f"results[{index}] must be an object.")
        rank = item.get("hotspot_rank")
        tile = item.get("tile_id")
        priority_id = item.get("priority_evidence_id")
        bundle_id = item.get("evidence_bundle_id")
        evidence_complete = item.get("evidence_complete")
        medical = item.get("medical_risk_score")
        if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1 or rank in seen_ranks:
            raise Day6ArtifactError("Day 6 hotspot ranks must be unique positive integers.")
        seen_ranks.add(rank)
        if tile is None or isinstance(tile, bool):
            raise Day6ArtifactError(f"results[{index}].tile_id is invalid.")
        if not isinstance(priority_id, str) or not priority_id.startswith("hs_priority_"):
            raise Day6ArtifactError(f"results[{index}].priority_evidence_id is invalid.")
        if not isinstance(bundle_id, str) or not bundle_id.startswith("hs_site_evidence_"):
            raise Day6ArtifactError(f"results[{index}].evidence_bundle_id is invalid.")
        if not isinstance(evidence_complete, bool):
            raise Day6ArtifactError(f"results[{index}].evidence_complete must be boolean.")
        if medical is not None:
            raise Day6ArtifactError("Day 7 refuses a Day 6 artifact that contains a medical risk score.")

        adjusted_score = _optional_0_100(
            item.get("evidence_adjusted_priority_score"),
            f"results[{index}].evidence_adjusted_priority_score",
        )
        adjusted_band = item.get("evidence_adjusted_priority_band")
        if adjusted_score is None and adjusted_band is not None:
            raise Day6ArtifactError("Adjusted priority band cannot exist when adjusted priority is withheld.")
        if adjusted_score is not None and (not isinstance(adjusted_band, str) or not adjusted_band):
            raise Day6ArtifactError("Adjusted priority band is required when adjusted priority is available.")
        if evidence_complete != (adjusted_score is not None):
            raise Day6ArtifactError("Day 6 evidence_complete is inconsistent with adjusted-priority availability.")

        parsed.append(
            Day6ResultInput(
                hotspot_rank=rank,
                tile_id=tile,
                priority_evidence_id=priority_id,
                evidence_bundle_id=bundle_id,
                vulnerability_score=_optional_0_100(item.get("vulnerability_score"), "vulnerability_score"),
                adaptive_capacity_score=_optional_0_100(item.get("adaptive_capacity_score"), "adaptive_capacity_score"),
                vulnerability_completeness=_completeness(
                    item.get("vulnerability_completeness"), "vulnerability_completeness"
                ),
                adaptive_capacity_completeness=_completeness(
                    item.get("adaptive_capacity_completeness"), "adaptive_capacity_completeness"
                ),
                evidence_complete=evidence_complete,
                evidence_adjusted_priority_score=adjusted_score,
                evidence_adjusted_priority_band=adjusted_band,
                medical_risk_score=None,
            )
        )

    if all_complete != all(item.evidence_complete for item in parsed):
        raise Day6ArtifactError("Day 6 global evidence-completeness flag is inconsistent with results.")

    return Day6EvidenceSource(
        artifact_path=str(artifact_path),
        artifact_sha256=file_sha256(artifact_path),
        day5_artifact_path=day5_path,
        day5_artifact_sha256=day5_sha,
        day44_artifact_sha256=day44_sha,
        scope=payload["scope"],
        all_required_evidence_complete=all_complete,
        results=tuple(parsed),
    )
