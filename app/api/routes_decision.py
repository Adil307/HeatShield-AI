from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.schemas.decision import NaturalLanguageScreenRequest, StructuredClaimRequest
from app.services.claim_guard import evaluate_structured_claim, screen_natural_language


router = APIRouter()
DAY7_PATH = Path("data/processed/day7_explainability_guard.json")


def _artifact() -> dict:
    if not DAY7_PATH.exists():
        raise HTTPException(status_code=404, detail="Day 7 explainability artifact has not been generated yet.")
    try:
        payload = json.loads(DAY7_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail="Day 7 explainability artifact is unreadable.") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != "heatshield.day7.explainability_guard.v1":
        raise HTTPException(status_code=500, detail="Day 7 explainability artifact schema is invalid.")
    return payload


def _packet(payload: dict, hotspot_rank: int) -> dict:
    packets = payload.get("packets")
    if not isinstance(packets, list):
        raise HTTPException(status_code=500, detail="Day 7 packets are missing.")
    for packet in packets:
        if isinstance(packet, dict) and packet.get("hotspot_rank") == hotspot_rank:
            return packet
    raise HTTPException(status_code=404, detail=f"No explainability packet for hotspot_rank={hotspot_rank}.")


@router.get("/explainability")
async def explainability_artifact() -> dict:
    return _artifact()


@router.get("/explainability/{hotspot_rank}")
async def explainability_packet(hotspot_rank: int) -> dict:
    return _packet(_artifact(), hotspot_rank)


@router.post("/claim-guard/evaluate")
async def claim_guard_evaluate(request: StructuredClaimRequest) -> dict:
    packet = _packet(_artifact(), request.hotspot_rank)
    return evaluate_structured_claim(packet, request.model_dump()).to_dict()


@router.post("/claim-guard/screen-text")
async def claim_guard_screen_text(request: NaturalLanguageScreenRequest) -> dict:
    return screen_natural_language(request.text).to_dict()
