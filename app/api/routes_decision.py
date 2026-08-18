from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.schemas.decision import NaturalLanguageScreenRequest, StructuredClaimRequest
from app.services.claim_guard import evaluate_structured_claim, screen_natural_language


router = APIRouter()
DAY7_PATH = Path("data/processed/day7_explainability_guard.json")
DAY8_PATH = Path("data/processed/day8_controlled_recommendations.json")


def _artifact(path: Path, schema_version: str, label: str) -> dict:
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{label} artifact has not been generated yet.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=f"{label} artifact is unreadable.") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != schema_version:
        raise HTTPException(status_code=500, detail=f"{label} artifact schema is invalid.")
    return payload


def _day7() -> dict:
    return _artifact(DAY7_PATH, "heatshield.day7.explainability_guard.v1", "Day 7 explainability")


def _day8() -> dict:
    return _artifact(DAY8_PATH, "heatshield.day8.controlled_recommendations.v1", "Day 8 recommendation")


def _packet(payload: dict, hotspot_rank: int) -> dict:
    packets = payload.get("packets")
    if not isinstance(packets, list):
        raise HTTPException(status_code=500, detail="Day 7 packets are missing.")
    for packet in packets:
        if isinstance(packet, dict) and packet.get("hotspot_rank") == hotspot_rank:
            return packet
    raise HTTPException(status_code=404, detail=f"No explainability packet for hotspot_rank={hotspot_rank}.")


def _recommendation_hotspot(payload: dict, hotspot_rank: int) -> dict:
    hotspots = payload.get("hotspots")
    if not isinstance(hotspots, list):
        raise HTTPException(status_code=500, detail="Day 8 recommendation hotspots are missing.")
    for item in hotspots:
        if isinstance(item, dict) and item.get("hotspot_rank") == hotspot_rank:
            return item
    raise HTTPException(status_code=404, detail=f"No recommendation set for hotspot_rank={hotspot_rank}.")


@router.get("/explainability")
async def explainability_artifact() -> dict:
    return _day7()


@router.get("/explainability/{hotspot_rank}")
async def explainability_packet(hotspot_rank: int) -> dict:
    return _packet(_day7(), hotspot_rank)


@router.post("/claim-guard/evaluate")
async def claim_guard_evaluate(request: StructuredClaimRequest) -> dict:
    packet = _packet(_day7(), request.hotspot_rank)
    return evaluate_structured_claim(packet, request.model_dump()).to_dict()


@router.post("/claim-guard/screen-text")
async def claim_guard_screen_text(request: NaturalLanguageScreenRequest) -> dict:
    return screen_natural_language(request.text).to_dict()


@router.get("/recommendations")
async def recommendations_artifact() -> dict:
    return _day8()


@router.get("/recommendations/{hotspot_rank}")
async def recommendations_for_hotspot(hotspot_rank: int) -> dict:
    return _recommendation_hotspot(_day8(), hotspot_rank)
