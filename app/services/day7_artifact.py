from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class Day7ArtifactError(ValueError):
    pass


EXPECTED_SCHEMA = "heatshield.day7.explainability_guard.v1"
EXPECTED_SCOPE = "deterministic_explainability_and_claim_grounding_not_llm_reasoning"
EXPECTED_SCENARIO_SCOPE = "historical_hazard_current_context_scenario_replay"


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
        raise Day7ArtifactError(f"Cannot read Day 7 artifact: {path}") from exc
    if not isinstance(payload, dict):
        raise Day7ArtifactError("Day 7 artifact must contain a JSON object.")
    return payload


@dataclass(frozen=True, slots=True)
class Day7Source:
    path: Path
    sha256: str
    payload: dict[str, Any]
    packets: tuple[dict[str, Any], ...]


def load_day7_source(
    path: str | Path,
    *,
    day6_path: str | Path | None = None,
    day5_path: str | Path | None = None,
    day44_path: str | Path | None = None,
) -> Day7Source:
    artifact_path = Path(path)
    payload = _read_json(artifact_path)
    if payload.get("schema_version") != EXPECTED_SCHEMA:
        raise Day7ArtifactError("Unsupported Day 7 artifact schema.")
    if payload.get("scope") != EXPECTED_SCOPE:
        raise Day7ArtifactError("Unsupported Day 7 artifact scope.")

    source = payload.get("source")
    if not isinstance(source, dict):
        raise Day7ArtifactError("Day 7 source metadata is missing.")

    checks = (
        (day6_path, "day6_artifact_sha256", "Day 7 -> Day 6"),
        (day5_path, "day5_artifact_sha256", "Day 7 -> Day 5"),
        (day44_path, "day44_artifact_sha256", "Day 7 -> Day 4.4"),
    )
    for current_path, hash_key, label in checks:
        if current_path is None:
            continue
        expected = source.get(hash_key)
        if not isinstance(expected, str) or len(expected) != 64:
            raise Day7ArtifactError(f"{label} provenance hash is missing.")
        if file_sha256(current_path) != expected:
            raise Day7ArtifactError(f"{label} SHA-256 provenance mismatch.")

    packets = payload.get("packets")
    if not isinstance(packets, list) or not packets:
        raise Day7ArtifactError("Day 7 explainability packets are missing.")

    ranks: set[int] = set()
    normalized: list[dict[str, Any]] = []
    for packet in packets:
        if not isinstance(packet, dict):
            raise Day7ArtifactError("Day 7 packets must be objects.")
        rank = packet.get("hotspot_rank")
        if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1 or rank in ranks:
            raise Day7ArtifactError("Day 7 hotspot ranks must be unique positive integers.")
        ranks.add(rank)
        if packet.get("scenario_scope") != EXPECTED_SCENARIO_SCOPE:
            raise Day7ArtifactError("Day 8 only supports the verified Day 4.4 scenario-replay scope.")
        ledger = packet.get("evidence_ledger")
        if not isinstance(ledger, list) or not ledger:
            raise Day7ArtifactError(f"Day 7 packet rank={rank} has no evidence ledger.")
        normalized.append(packet)

    return Day7Source(
        path=artifact_path,
        sha256=file_sha256(artifact_path),
        payload=payload,
        packets=tuple(normalized),
    )
