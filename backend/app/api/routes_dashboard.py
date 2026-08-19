from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.paths import backend_path
from app.services.dashboard_snapshot import DashboardSnapshotError, build_dashboard_snapshot

router = APIRouter()
DAY44_PATH = backend_path("data/processed/day44_scenario_replay.json")
DAY5_PATH = backend_path("data/processed/day5_planning_priority.json")
DAY6_PATH = backend_path("data/processed/day6_site_evidence_layer.json")
DAY7_PATH = backend_path("data/processed/day7_explainability_guard.json")
DAY8_PATH = backend_path("data/processed/day8_controlled_recommendations.json")
CATALOG_PATH = backend_path("config/day8_action_catalog.json")
RAW_HEATMAP_PATH = backend_path("data/raw/official_heatmap_completed.json")

@router.get("/overview")
async def dashboard_overview() -> dict:
    try:
        return build_dashboard_snapshot(
            day7_path=DAY7_PATH,
            day8_path=DAY8_PATH,
            day6_path=DAY6_PATH,
            day5_path=DAY5_PATH,
            day44_path=DAY44_PATH,
            catalog_path=CATALOG_PATH,
            raw_heatmap_path=RAW_HEATMAP_PATH,
        )
    except DashboardSnapshotError as exc:
        raise HTTPException(status_code=500, detail=f"Dashboard evidence chain invalid: {exc}") from exc

@router.get("/health")
async def dashboard_health() -> dict:
    required = {"day7": DAY7_PATH.exists(), "day8": DAY8_PATH.exists(), "catalog": CATALOG_PATH.exists()}
    return {
        "status": "ready" if all(required.values()) else "missing_artifacts",
        "required_artifacts": required,
        "raw_heatmap_available": RAW_HEATMAP_PATH.exists(),
        "network_calls_per_health_check": 0,
    }
