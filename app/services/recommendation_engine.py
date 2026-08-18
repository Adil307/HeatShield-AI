from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from app.domain.recommendation import ControlledRecommendation, TriggerEvidence
from app.services.day7_artifact import Day7ArtifactError, file_sha256, load_day7_source
from app.services.recommendation_guard import RecommendationGuardError, validate_controlled_recommendation


class RecommendationEngineError(ValueError):
    pass


CATALOG_SCHEMA = "heatshield.day8.action_catalog.v1"
OUTPUT_SCHEMA = "heatshield.day8.controlled_recommendations.v1"
OUTPUT_SCOPE = "controlled_evidence_triggered_scenario_planning_actions_not_medical_advice"
TIER_ORDER = {"P1": 0, "P2": 1, "P3": 2}


def _read_json(path: str | Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecommendationEngineError(f"Cannot read {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise RecommendationEngineError(f"{label} must contain a JSON object.")
    return payload


def _catalog(path: str | Path) -> dict[str, Any]:
    payload = _read_json(path, "Day 8 action catalog")
    if payload.get("schema_version") != CATALOG_SCHEMA:
        raise RecommendationEngineError("Unsupported Day 8 action-catalog schema.")
    sources = payload.get("source_registry")
    actions = payload.get("actions")
    if not isinstance(sources, dict) or not sources:
        raise RecommendationEngineError("Day 8 source registry is missing.")
    if not isinstance(actions, list) or not actions:
        raise RecommendationEngineError("Day 8 action catalog is empty.")

    action_ids: set[str] = set()
    for action in actions:
        if not isinstance(action, dict):
            raise RecommendationEngineError("Action-catalog entries must be objects.")
        action_id = action.get("action_id")
        if not isinstance(action_id, str) or not action_id or action_id in action_ids:
            raise RecommendationEngineError("Action IDs must be unique non-empty strings.")
        action_ids.add(action_id)
        if action.get("priority_tier") not in TIER_ORDER:
            raise RecommendationEngineError(f"Unsupported priority tier for {action_id}.")
        basis = action.get("authoritative_basis")
        if not isinstance(basis, list) or not basis:
            raise RecommendationEngineError(f"Action {action_id} must cite authoritative basis.")
        if any(source_id not in sources for source_id in basis):
            raise RecommendationEngineError(f"Action {action_id} cites an unknown source.")
        if not isinstance(action.get("trigger"), dict):
            raise RecommendationEngineError(f"Action {action_id} trigger is missing.")
    return payload


def _ledger(packet: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    raw = packet.get("evidence_ledger")
    if not isinstance(raw, list):
        raise RecommendationEngineError("Explainability packet evidence ledger is missing.")
    index: dict[str, Mapping[str, Any]] = {}
    for item in raw:
        if not isinstance(item, Mapping):
            raise RecommendationEngineError("Evidence ledger entries must be objects.")
        key = item.get("key")
        if not isinstance(key, str) or not key or key in index:
            raise RecommendationEngineError("Evidence ledger keys must be unique non-empty strings.")
        index[key] = item
    return index


def _numeric(entry: Mapping[str, Any], key: str) -> float:
    value = entry.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RecommendationEngineError(f"Trigger metric {key} is not numeric.")
    number = float(value)
    if not math.isfinite(number):
        raise RecommendationEngineError(f"Trigger metric {key} is not finite.")
    return number


def _condition(condition: Mapping[str, Any], ledger: Mapping[str, Mapping[str, Any]]) -> tuple[bool, tuple[str, ...]]:
    kind = condition.get("type")
    if kind == "classification_is":
        key = condition.get("key")
        expected = condition.get("classification")
        entry = ledger.get(key) if isinstance(key, str) else None
        if entry is None:
            raise RecommendationEngineError(f"Trigger evidence key is missing: {key}")
        return entry.get("classification") == expected, (key,)

    if kind == "numeric_at_least":
        key = condition.get("key")
        threshold = condition.get("threshold")
        entry = ledger.get(key) if isinstance(key, str) else None
        if entry is None:
            raise RecommendationEngineError(f"Trigger evidence key is missing: {key}")
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
            raise RecommendationEngineError("numeric_at_least threshold must be numeric.")
        return _numeric(entry, key) >= float(threshold), (key,)

    if kind == "any_numeric_positive":
        keys = condition.get("keys")
        if not isinstance(keys, list) or not keys:
            raise RecommendationEngineError("any_numeric_positive requires non-empty keys.")
        matched = False
        used: list[str] = []
        for key in keys:
            if not isinstance(key, str) or key not in ledger:
                raise RecommendationEngineError(f"Trigger evidence key is missing: {key}")
            used.append(key)
            if _numeric(ledger[key], key) > 0:
                matched = True
        return matched, tuple(used)

    raise RecommendationEngineError(f"Unsupported action trigger condition: {kind}")


def _trigger_matches(action: Mapping[str, Any], ledger: Mapping[str, Mapping[str, Any]]) -> tuple[bool, tuple[str, ...]]:
    trigger = action.get("trigger")
    if not isinstance(trigger, Mapping):
        raise RecommendationEngineError("Action trigger must be an object.")
    conditions = trigger.get("all")
    if not isinstance(conditions, list) or not conditions:
        raise RecommendationEngineError("Action trigger must contain a non-empty 'all' list.")
    keys: list[str] = []
    for condition in conditions:
        if not isinstance(condition, Mapping):
            raise RecommendationEngineError("Action trigger conditions must be objects.")
        matched, used = _condition(condition, ledger)
        keys.extend(used)
        if not matched:
            return False, tuple(dict.fromkeys(keys))
    return True, tuple(dict.fromkeys(keys))


def _trigger_evidence(keys: tuple[str, ...], ledger: Mapping[str, Mapping[str, Any]]) -> tuple[TriggerEvidence, ...]:
    result: list[TriggerEvidence] = []
    for key in keys:
        entry = ledger[key]
        classification = entry.get("classification")
        if not isinstance(classification, str):
            raise RecommendationEngineError(f"Evidence classification missing for {key}.")
        unit = entry.get("unit") if isinstance(entry.get("unit"), str) else None
        result.append(
            TriggerEvidence(
                key=key,
                classification=classification,
                value=entry.get("value"),
                unit=unit,
            )
        )
    return tuple(result)


def _recommendation_id(day7_sha: str, packet_id: str, action_id: str, trigger_evidence: tuple[TriggerEvidence, ...]) -> str:
    canonical = json.dumps(
        {
            "day7_sha256": day7_sha,
            "packet_id": packet_id,
            "action_id": action_id,
            "triggers": [item.to_dict() for item in trigger_evidence],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return "hs_action_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]


class _EvidenceFormatMap(dict[str, Any]):
    def __missing__(self, key: str) -> Any:
        raise RecommendationEngineError(f"Recommendation why_template references missing evidence key: {key}")


def _render_why(template: Any, ledger: Mapping[str, Mapping[str, Any]]) -> str:
    if not isinstance(template, str) or not template.strip():
        raise RecommendationEngineError("Action why_template must be a non-empty string.")
    values = _EvidenceFormatMap({key: entry.get("value") for key, entry in ledger.items()})
    try:
        return template.format_map(values)
    except (KeyError, ValueError) as exc:
        raise RecommendationEngineError(f"Cannot render recommendation why_template: {exc}") from exc


def _build_action(
    *,
    action: Mapping[str, Any],
    packet: Mapping[str, Any],
    day7_sha: str,
    ledger: Mapping[str, Mapping[str, Any]],
    trigger_keys: tuple[str, ...],
    source_registry: Mapping[str, Any],
) -> ControlledRecommendation:
    packet_id = packet.get("packet_id")
    if not isinstance(packet_id, str) or not packet_id:
        raise RecommendationEngineError("Explainability packet_id is missing.")
    trigger_evidence = _trigger_evidence(trigger_keys, ledger)
    item = ControlledRecommendation(
        recommendation_id=_recommendation_id(day7_sha, packet_id, str(action["action_id"]), trigger_evidence),
        action_id=str(action["action_id"]),
        title=str(action["title"]),
        action_type=str(action["action_type"]),
        priority_tier=str(action["priority_tier"]),
        status=str(action["status"]),
        recommendation=str(action["recommendation"]),
        why=_render_why(action.get("why_template"), ledger),
        trigger_evidence=trigger_evidence,
        required_verification=tuple(str(x) for x in action.get("required_verification", [])),
        limitations=tuple(str(x) for x in action.get("limitations", [])),
        authoritative_basis=tuple(str(x) for x in action.get("authoritative_basis", [])),
        guard_status="approved_controlled_catalog_action",
    )
    item_dict = item.to_dict()
    try:
        validate_controlled_recommendation(item_dict, catalog_action=action, source_registry=source_registry)
    except RecommendationGuardError as exc:
        raise RecommendationEngineError(str(exc)) from exc
    return item


def build_recommendations(
    *,
    day7_path: str | Path,
    catalog_path: str | Path,
    day6_path: str | Path | None = None,
    day5_path: str | Path | None = None,
    day44_path: str | Path | None = None,
) -> dict[str, Any]:
    try:
        day7 = load_day7_source(day7_path, day6_path=day6_path, day5_path=day5_path, day44_path=day44_path)
    except Day7ArtifactError as exc:
        raise RecommendationEngineError(str(exc)) from exc

    catalog = _catalog(catalog_path)
    source_registry = catalog["source_registry"]
    actions = catalog["actions"]
    catalog_sha = file_sha256(catalog_path)

    hotspot_results: list[dict[str, Any]] = []
    action_status_counts: dict[str, int] = {}
    action_type_counts: dict[str, int] = {}

    for packet in day7.packets:
        ledger = _ledger(packet)
        recs: list[ControlledRecommendation] = []
        for action in actions:
            matched, keys = _trigger_matches(action, ledger)
            if not matched:
                continue
            rec = _build_action(
                action=action,
                packet=packet,
                day7_sha=day7.sha256,
                ledger=ledger,
                trigger_keys=keys,
                source_registry=source_registry,
            )
            recs.append(rec)
            action_status_counts[rec.status] = action_status_counts.get(rec.status, 0) + 1
            action_type_counts[rec.action_type] = action_type_counts.get(rec.action_type, 0) + 1

        recs.sort(key=lambda item: (TIER_ORDER[item.priority_tier], item.action_id))
        hotspot_results.append(
            {
                "hotspot_rank": packet["hotspot_rank"],
                "tile_id": packet.get("tile_id"),
                "packet_id": packet.get("packet_id"),
                "pre_adaptation_priority_score": packet.get("pre_adaptation_priority_score"),
                "pre_adaptation_priority_band": packet.get("pre_adaptation_priority_band"),
                "evidence_adjusted_priority_score": packet.get("evidence_adjusted_priority_score"),
                "evidence_complete": packet.get("evidence_complete"),
                "recommendation_count": len(recs),
                "recommendations": [item.to_dict() for item in recs],
            }
        )

    hotspot_results.sort(
        key=lambda item: (
            -(float(item["pre_adaptation_priority_score"]) if isinstance(item.get("pre_adaptation_priority_score"), (int, float)) else -1.0),
            int(item["hotspot_rank"]),
        )
    )

    return {
        "schema_version": OUTPUT_SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": OUTPUT_SCOPE,
        "source": {
            "day7_artifact_path": str(Path(day7_path)),
            "day7_artifact_sha256": day7.sha256,
            "action_catalog_path": str(Path(catalog_path)),
            "action_catalog_sha256": catalog_sha,
        },
        "policy": {
            "deterministic_catalog_only": True,
            "llm_generated_actions": False,
            "medical_or_clinical_advice": False,
            "scenario_semantics": "Historical thermal evidence is replayed against current mapped context; recommendations are planning assessments, verification steps, or explicitly conditional operational reviews.",
            "missing_evidence": "Unknown evidence triggers verification; it is never treated as zero or absence.",
            "intervention_effects": "No site-specific temperature reduction or health-effect estimate is produced without a validated intervention model.",
        },
        "source_registry": source_registry,
        "summary": {
            "hotspots_processed": len(hotspot_results),
            "recommendations_generated": sum(item["recommendation_count"] for item in hotspot_results),
            "status_counts": dict(sorted(action_status_counts.items())),
            "action_type_counts": dict(sorted(action_type_counts.items())),
            "new_provider_api_calls": 0,
            "new_llm_calls": 0,
        },
        "hotspots": hotspot_results,
    }


def save_recommendations(payload: Mapping[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
