from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.ai.copilot_context import ledger_index
from app.services.day7_artifact import load_day7_source
from app.services.day8_artifact import load_day8_source


class DashboardSnapshotError(ValueError):
    pass


def _ledger_value(ledger: dict[str, dict[str, Any]], key: str) -> Any:
    entry = ledger.get(key)
    return None if entry is None else entry.get("value")


def _ledger_status(ledger: dict[str, dict[str, Any]], key: str) -> str | None:
    entry = ledger.get(key)
    if entry is None:
        return None
    classification = entry.get("classification")
    return str(classification) if classification is not None else None


def _read_json(path: str | Path) -> dict[str, Any] | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        value = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def find_feature_collection(value: Any) -> dict[str, Any] | None:
    """Find the first GeoJSON FeatureCollection in a nested provider payload."""
    if isinstance(value, dict):
        if value.get("type") == "FeatureCollection" and isinstance(value.get("features"), list):
            return value
        if isinstance(value.get("features"), list) and all(isinstance(item, dict) for item in value["features"]):
            return {"type": "FeatureCollection", "features": value["features"]}
        for child in value.values():
            found = find_feature_collection(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_feature_collection(child)
            if found is not None:
                return found
    return None


def _recommendation_view(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "recommendation_id": item.get("recommendation_id"),
        "action_id": item.get("action_id"),
        "action_type": item.get("action_type"),
        "title": item.get("title"),
        "priority_tier": item.get("priority_tier"),
        "status": item.get("status"),
        "recommendation": item.get("recommendation"),
        "guard_status": item.get("guard_status"),
    }


def build_dashboard_snapshot(
    *,
    day7_path: str | Path,
    day8_path: str | Path,
    day6_path: str | Path | None = None,
    day5_path: str | Path | None = None,
    day44_path: str | Path | None = None,
    catalog_path: str | Path | None = None,
    raw_heatmap_path: str | Path | None = None,
) -> dict[str, Any]:
    try:
        day7 = load_day7_source(day7_path, day6_path=day6_path, day5_path=day5_path, day44_path=day44_path)
        day8 = load_day8_source(day8_path, day7_path=day7_path, catalog_path=catalog_path)
    except ValueError as exc:
        raise DashboardSnapshotError(str(exc)) from exc

    packets_by_rank = {int(packet["hotspot_rank"]): packet for packet in day7.packets if isinstance(packet, dict)}
    recs_by_rank = {int(item["hotspot_rank"]): item for item in day8.hotspots if isinstance(item, dict)}
    planning_order = tuple(int(item["hotspot_rank"]) for item in day8.hotspots)
    if set(planning_order) != set(packets_by_rank):
        raise DashboardSnapshotError("Day 7 and Day 8 hotspot sets differ.")

    hotspots: list[dict[str, Any]] = []
    for rank in planning_order:
        packet = packets_by_rank[rank]
        ledger = ledger_index(packet)
        recs = recs_by_rank[rank].get("recommendations", [])
        recommendations = [_recommendation_view(item) for item in recs if isinstance(item, dict)]
        hotspots.append({
            "hotspot_rank": rank,
            "tile_id": packet.get("tile_id"),
            "planning_priority": packet.get("pre_adaptation_priority_score"),
            "planning_priority_band": packet.get("pre_adaptation_priority_band"),
            "scenario_scope": packet.get("scenario_scope"),
            "scenario_statement": packet.get("scenario_statement"),
            "contributions": packet.get("contributions") or [],
            "metrics": {
                "historical_air_temperature_celsius": _ledger_value(ledger, "historical_air_temperature_celsius"),
                "historical_heat_index_celsius": _ledger_value(ledger, "historical_heat_index_celsius"),
                "historical_apparent_temperature_celsius": _ledger_value(ledger, "historical_apparent_temperature_celsius"),
                "historical_wet_bulb_temperature_celsius": _ledger_value(ledger, "historical_wet_bulb_temperature_celsius"),
                "historical_relative_humidity_percent": _ledger_value(ledger, "historical_relative_humidity_percent"),
                "hazard_planning_ordinal": _ledger_value(ledger, "hazard_planning_ordinal"),
                "mapped_exposure_proxy": _ledger_value(ledger, "mapped_exposure_proxy"),
                "context_sensitivity_proxy": _ledger_value(ledger, "context_sensitivity_proxy"),
                "verified_operational_vulnerability": _ledger_value(ledger, "verified_operational_vulnerability"),
                "verified_adaptive_capacity": _ledger_value(ledger, "verified_adaptive_capacity"),
                "evidence_adjusted_planning_priority": _ledger_value(ledger, "evidence_adjusted_planning_priority"),
            },
            "evidence_status": {
                "verified_operational_vulnerability": _ledger_status(ledger, "verified_operational_vulnerability"),
                "verified_adaptive_capacity": _ledger_status(ledger, "verified_adaptive_capacity"),
                "evidence_adjusted_planning_priority": _ledger_status(ledger, "evidence_adjusted_planning_priority"),
                "medical_risk_probability": _ledger_status(ledger, "medical_risk_probability"),
            },
            "recommendations": recommendations,
        })

    raw_payload = _read_json(raw_heatmap_path) if raw_heatmap_path else None
    geojson = find_feature_collection(raw_payload) if raw_payload else None
    first = hotspots[0] if hotspots else {}
    max_historical_air = max(
        (float(item["metrics"]["historical_air_temperature_celsius"]) for item in hotspots
         if isinstance(item["metrics"]["historical_air_temperature_celsius"], (int, float))),
        default=None,
    )

    return {
        "schema_version": "heatshield.day10.dashboard_snapshot.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "project": {
            "name": "HeatShield AI",
            "tagline": "From temperature evidence to explainable heat-priority decisions.",
            "competition_mode": True,
        },
        "scenario": {
            "mode": "scenario_replay",
            "statement": first.get("scenario_statement"),
            "thermal_evidence_source": "FortyGuard",
            "context_source": "OpenStreetMap",
            "scope_warning": (
                "Historical thermal evidence is evaluated against current mapped urban context. "
                "Planning priority is not a medical-risk probability and mapped objects are not people."
            ),
        },
        "planning_order": list(planning_order),
        "summary": {
            "hotspot_count": len(hotspots),
            "highest_priority_rank": planning_order[0] if planning_order else None,
            "highest_priority_score": hotspots[0].get("planning_priority") if hotspots else None,
            "max_historical_air_temperature_celsius": max_historical_air,
            "heatmap_feature_count": len(geojson.get("features", [])) if geojson else 0,
        },
        "hotspots": hotspots,
        "heatmap_geojson": geojson,
        "provenance": {
            "day7_artifact_sha256": day7.sha256,
            "day8_artifact_sha256": day8.sha256,
            "new_fortyguard_calls_for_dashboard_snapshot": 0,
            "new_overpass_calls_for_dashboard_snapshot": 0,
        },
        "safety": {
            "medical_probability_supported": False,
            "historical_hazard_is_current_heat": False,
            "mapped_objects_are_people": False,
            "free_form_action_invention_allowed": False,
        },
    }
