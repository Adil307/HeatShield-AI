from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.core.paths import backend_path
from app.providers.fortyguard import FortyGuardClient, FortyGuardError
from app.schemas.fortyguard import HeatmapRequest
from app.services.dashboard_snapshot import DashboardSnapshotError, build_dashboard_snapshot
from app.services.live_decision_readiness import LiveDecisionReadinessError, run_live_decision_readiness
from app.services.live_context_priority import (
    Day13ContextPriorityRequest,
    LiveContextPriorityError,
    run_live_context_priority,
)
from app.services.live_thermal_analysis import (
    MAX_DEMO_AOI_SQ_MILES,
    LiveThermalAnalysisError,
    run_live_thermal_analysis,
    validate_live_request,
)

router = APIRouter()
DAY44_PATH = backend_path("data/processed/day44_scenario_replay.json")
DAY5_PATH = backend_path("data/processed/day5_planning_priority.json")
DAY6_PATH = backend_path("data/processed/day6_site_evidence_layer.json")
DAY7_PATH = backend_path("data/processed/day7_explainability_guard.json")
DAY8_PATH = backend_path("data/processed/day8_controlled_recommendations.json")
CATALOG_PATH = backend_path("config/day8_action_catalog.json")
RAW_HEATMAP_PATH = backend_path("data/raw/official_heatmap_completed.json")
LIVE_CACHE_DIR = backend_path("data/cache/day11")
LIVE_ENV_CACHE_DIR = backend_path("data/cache/day12")

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


def make_live_client() -> FortyGuardClient:
    return FortyGuardClient(get_settings())


@router.get("/live-analysis/status")
async def live_analysis_status() -> dict:
    settings = get_settings()
    cache_entries = len(list(LIVE_CACHE_DIR.glob("tcm_*.json"))) if LIVE_CACHE_DIR.exists() else 0
    return {
        "status": "ready" if settings.api_key_configured else "api_key_required",
        "api_key_configured": settings.api_key_configured,
        "api_key_value_exposed": False,
        "analytic_type": "tcm",
        "max_demo_aoi_sq_miles": MAX_DEMO_AOI_SQ_MILES,
        "cache_entries": cache_entries,
        "fresh_mode_scope": "verified_thermal_evidence_only",
    }


@router.post("/live-analysis")
async def dashboard_live_analysis(request: HeatmapRequest) -> dict:
    try:
        # Validate before constructing a provider client so invalid/oversized AOIs
        # are rejected without requiring credentials or touching the network.
        validate_live_request(request)
        settings = get_settings()
        client = FortyGuardClient(settings) if settings.api_key_configured else None
        return await run_live_thermal_analysis(
            request,
            client=client,
            cache_dir=LIVE_CACHE_DIR,
        )
    except LiveThermalAnalysisError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FortyGuardError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "provider_status_code": exc.status_code,
                "provider_response": exc.response_body,
            },
        ) from exc


@router.post("/live-analysis/top-hotspot-enrichment")
async def dashboard_live_top_hotspot_enrichment(request: HeatmapRequest) -> dict:
    try:
        # Day 12 reuses the already-completed Day 11 heatmap cache. The explicit
        # enrichment action may create at most one environmental-parameters job.
        validate_live_request(request)
        settings = get_settings()
        client = FortyGuardClient(settings) if settings.api_key_configured else None
        return await run_live_decision_readiness(
            request,
            client=client,
            live_cache_dir=LIVE_CACHE_DIR,
            env_cache_dir=LIVE_ENV_CACHE_DIR,
        )
    except (LiveDecisionReadinessError, LiveThermalAnalysisError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FortyGuardError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "provider_status_code": exc.status_code,
                "provider_response": exc.response_body,
            },
        ) from exc

@router.post("/live-analysis/context-priority")
async def dashboard_live_context_priority(request: Day13ContextPriorityRequest) -> dict:
    try:
        validate_live_request(request.analysis_request)
        return await run_live_context_priority(
            request,
            live_cache_dir=LIVE_CACHE_DIR,
            env_cache_dir=LIVE_ENV_CACHE_DIR,
            catalog_path=CATALOG_PATH,
        )
    except (LiveContextPriorityError, LiveDecisionReadinessError, LiveThermalAnalysisError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
