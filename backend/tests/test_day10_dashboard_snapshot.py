from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_dashboard import router
from app.services.dashboard_snapshot import build_dashboard_snapshot, find_feature_collection

ROOT = Path(__file__).resolve().parents[1]
DAY44 = ROOT / "data/processed/day44_scenario_replay.json"
DAY5 = ROOT / "data/processed/day5_planning_priority.json"
DAY6 = ROOT / "data/processed/day6_site_evidence_layer.json"
DAY7 = ROOT / "data/processed/day7_explainability_guard.json"
DAY8 = ROOT / "data/processed/day8_controlled_recommendations.json"
CATALOG = ROOT / "config/day8_action_catalog.json"
RAW = ROOT / "data/raw/official_heatmap_completed.json"

def _snapshot():
    return build_dashboard_snapshot(day7_path=DAY7, day8_path=DAY8, day6_path=DAY6, day5_path=DAY5, day44_path=DAY44, catalog_path=CATALOG, raw_heatmap_path=RAW)

def test_snapshot_schema_and_hotspot_count() -> None:
    snapshot = _snapshot()
    assert snapshot["schema_version"] == "heatshield.day10.dashboard_snapshot.v1"
    assert snapshot["summary"]["hotspot_count"] == 3

def test_snapshot_preserves_verified_planning_order() -> None:
    assert _snapshot()["planning_order"] == [2, 3, 1]

def test_snapshot_highest_priority_is_not_assumed_hottest_tile() -> None:
    snapshot = _snapshot()
    assert snapshot["summary"]["highest_priority_rank"] == 2
    assert round(float(snapshot["summary"]["highest_priority_score"]), 2) == 70.29

def test_snapshot_preserves_known_historical_heat_index() -> None:
    hotspot2 = next(item for item in _snapshot()["hotspots"] if item["hotspot_rank"] == 2)
    assert hotspot2["metrics"]["historical_heat_index_celsius"] == 38.2

def test_snapshot_preserves_unknown_and_withheld_evidence() -> None:
    hotspot2 = next(item for item in _snapshot()["hotspots"] if item["hotspot_rank"] == 2)
    assert hotspot2["evidence_status"]["verified_operational_vulnerability"] == "unknown"
    assert hotspot2["evidence_status"]["verified_adaptive_capacity"] == "unknown"
    assert hotspot2["evidence_status"]["medical_risk_probability"] == "withheld"

def test_snapshot_exposes_only_controlled_recommendations() -> None:
    hotspot2 = next(item for item in _snapshot()["hotspots"] if item["hotspot_rank"] == 2)
    assert len(hotspot2["recommendations"]) == 5
    assert all(item["recommendation_id"] for item in hotspot2["recommendations"])

def test_snapshot_has_explicit_fortyguard_and_safety_provenance() -> None:
    snapshot = _snapshot()
    assert snapshot["scenario"]["thermal_evidence_source"] == "FortyGuard"
    assert snapshot["provenance"]["new_fortyguard_calls_for_dashboard_snapshot"] == 0
    assert snapshot["safety"]["medical_probability_supported"] is False

def test_feature_collection_finder_handles_nested_provider_payload() -> None:
    payload = {"result": {"map_data": {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": None}]}}}
    found = find_feature_collection(payload)
    assert found is not None
    assert len(found["features"]) == 1

def test_dashboard_router_returns_overview() -> None:
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1/dashboard")
    response = TestClient(test_app).get("/api/v1/dashboard/overview")
    assert response.status_code == 200
    assert response.json()["scenario"]["thermal_evidence_source"] == "FortyGuard"
