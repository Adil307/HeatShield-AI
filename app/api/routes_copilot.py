from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.schemas.copilot import CopilotAskRequest
from app.services.copilot_engine import CopilotEngineError, answer_copilot


router = APIRouter()
DAY44_PATH = Path("data/processed/day44_scenario_replay.json")
DAY5_PATH = Path("data/processed/day5_planning_priority.json")
DAY6_PATH = Path("data/processed/day6_site_evidence_layer.json")
DAY7_PATH = Path("data/processed/day7_explainability_guard.json")
DAY8_PATH = Path("data/processed/day8_controlled_recommendations.json")
CATALOG_PATH = Path("config/day8_action_catalog.json")


@router.get("/status")
async def copilot_status() -> dict:
    settings = get_settings()
    return {
        "status": "ready" if DAY7_PATH.exists() and DAY8_PATH.exists() else "missing_artifacts",
        "default_provider": settings.copilot_provider,
        "openai_key_configured": settings.openai_api_key_configured,
        "model": settings.copilot_model if settings.copilot_provider.lower() == "openai" else None,
        "final_answer_policy": "deterministic renderer over guard-approved evidence/action IDs",
    }


@router.get("/capabilities")
async def copilot_capabilities() -> dict:
    return {
        "supported_intents": [
            "summary",
            "why_priority",
            "recommendations",
            "missing_evidence",
            "compare_hotspots",
            "metric_lookup",
            "scenario_scope",
        ],
        "unsupported_claims": [
            "medical/clinical risk probability",
            "historical hazard described as current heat",
            "mapped objects converted to people/occupancy",
            "uncatalogued intervention claims",
        ],
    }


@router.post("/ask")
async def copilot_ask(request: CopilotAskRequest) -> dict:
    try:
        return await answer_copilot(
            query=request.query,
            settings=get_settings(),
            day7_path=DAY7_PATH,
            day8_path=DAY8_PATH,
            day6_path=DAY6_PATH,
            day5_path=DAY5_PATH,
            day44_path=DAY44_PATH,
            catalog_path=CATALOG_PATH,
            mode=request.mode,
            preferred_hotspot_rank=request.hotspot_rank,
        )
    except CopilotEngineError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=f"Copilot evidence chain invalid: {exc}") from exc
