from __future__ import annotations

import re
from typing import Any

from app.domain.copilot import CopilotPlan
from app.ai.copilot_context import CopilotContext, ledger_index


_RANK = re.compile(r"\b(?:hotspot|rank)\s*#?\s*(\d+)\b", re.I)
_TILE = re.compile(r"\btile\s*#?\s*(\d+)\b", re.I)
_MEDICAL = re.compile(r"\b(?:medical|clinical|mortality|illness|health)\s+(?:risk|probability|chance|percentage)\b", re.I)
_CURRENT = re.compile(r"\b(?:current|currently|live|right now|today)\b.{0,30}\b(?:heat|temperature|heat index|hotspot)\b", re.I)
_PEOPLE = re.compile(r"\b(?:how many|number of)\s+(?:people|persons|students|patients|workers)\b", re.I)


METRIC_ALIASES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("heat index",), "historical_heat_index_celsius"),
    (("apparent temperature", "feels like"), "historical_apparent_temperature_celsius"),
    (("wet bulb", "wet-bulb"), "historical_wet_bulb_temperature_celsius"),
    (("humidity", "relative humidity"), "historical_relative_humidity_percent"),
    (("air temperature", "temperature"), "historical_air_temperature_celsius"),
    (("planning priority", "priority score"), "pre_adaptation_planning_priority"),
    (("healthcare", "hospital", "clinic"), "current_mapped_healthcare_objects_within_radius"),
    (("education", "school", "university", "college"), "current_mapped_education_objects_within_radius"),
    (("transit", "bus stop", "station"), "current_mapped_transit_waiting_objects_within_radius"),
    (("outdoor public", "park", "garden"), "current_mapped_outdoor_public_objects_within_radius"),
    (("civic", "library", "community centre", "community center"), "current_mapped_civic_public_objects_within_radius"),
)


def _rank_from_query(query: str, context: CopilotContext) -> int | None:
    match = _RANK.search(query)
    if match:
        rank = int(match.group(1))
        return rank if rank in context.packets_by_rank else None
    tile = _TILE.search(query)
    if tile:
        tile_id = int(tile.group(1))
        for rank, packet in context.packets_by_rank.items():
            if packet.get("tile_id") == tile_id:
                return rank
    return None


def _default_rank(context: CopilotContext) -> int:
    if not context.planning_order:
        raise ValueError("Copilot context has no planning-order hotspots.")
    return context.planning_order[0]


def deterministic_plan(query: str, context: CopilotContext, *, preferred_hotspot_rank: int | None = None) -> CopilotPlan:
    normalized = " ".join(query.lower().split())
    rank = preferred_hotspot_rank if preferred_hotspot_rank in context.packets_by_rank else _rank_from_query(query, context)
    rank = rank or _default_rank(context)

    if _MEDICAL.search(normalized) or _CURRENT.search(normalized) or _PEOPLE.search(normalized):
        return CopilotPlan(intent="scenario_scope", primary_hotspot_rank=rank)

    if any(token in normalized for token in ("compare", "difference", "which hotspot", "highest priority", "lowest priority")):
        return CopilotPlan(
            intent="compare_hotspots",
            primary_hotspot_rank=rank,
            comparison_hotspot_ranks=context.planning_order,
        )

    if any(token in normalized for token in ("recommend", "action", "what should", "what can we do", "next step")):
        recs = context.recommendations_by_rank[rank].get("recommendations", [])
        rec_ids = tuple(
            rec["recommendation_id"]
            for rec in recs
            if isinstance(rec, dict) and isinstance(rec.get("recommendation_id"), str)
        )
        return CopilotPlan(intent="recommendations", primary_hotspot_rank=rank, recommendation_ids=rec_ids)

    if any(token in normalized for token in ("missing", "unknown", "need to verify", "evidence needed", "incomplete")):
        return CopilotPlan(
            intent="missing_evidence",
            primary_hotspot_rank=rank,
            metric_keys=("verified_operational_vulnerability", "verified_adaptive_capacity"),
        )

    if any(token in normalized for token in ("why", "priority", "reason", "contribution")):
        return CopilotPlan(
            intent="why_priority",
            primary_hotspot_rank=rank,
            metric_keys=(
                "hazard_planning_ordinal",
                "mapped_exposure_proxy",
                "context_sensitivity_proxy",
                "pre_adaptation_planning_priority",
            ),
        )

    for aliases, key in METRIC_ALIASES:
        if any(alias in normalized for alias in aliases):
            if key in ledger_index(context.packets_by_rank[rank]):
                return CopilotPlan(intent="metric_lookup", primary_hotspot_rank=rank, metric_keys=(key,))

    if any(token in normalized for token in ("summary", "overview", "tell me about", "status")):
        return CopilotPlan(intent="summary", primary_hotspot_rank=rank)

    return CopilotPlan(intent="summary", primary_hotspot_rank=rank)


def validate_plan(plan: CopilotPlan, context: CopilotContext) -> CopilotPlan:
    if plan.intent not in {
        "summary",
        "why_priority",
        "recommendations",
        "missing_evidence",
        "compare_hotspots",
        "metric_lookup",
        "scenario_scope",
        "unsupported",
    }:
        raise ValueError("Copilot plan intent is not supported.")

    if plan.primary_hotspot_rank is not None and plan.primary_hotspot_rank not in context.packets_by_rank:
        raise ValueError("Copilot plan references an unknown primary hotspot rank.")

    for rank in plan.comparison_hotspot_ranks:
        if rank not in context.packets_by_rank:
            raise ValueError("Copilot plan references an unknown comparison hotspot rank.")

    target_rank = plan.primary_hotspot_rank
    if target_rank is not None:
        ledger = ledger_index(context.packets_by_rank[target_rank])
        for key in plan.metric_keys:
            if key not in ledger:
                raise ValueError(f"Copilot plan references unsupported evidence key: {key}")
        allowed_rec_ids = {
            rec.get("recommendation_id")
            for rec in context.recommendations_by_rank[target_rank].get("recommendations", [])
            if isinstance(rec, dict)
        }
        for rec_id in plan.recommendation_ids:
            if rec_id not in allowed_rec_ids:
                raise ValueError(f"Copilot plan references unsupported recommendation ID: {rec_id}")

    if len(plan.metric_keys) > 12 or len(plan.recommendation_ids) > 8 or len(plan.comparison_hotspot_ranks) > 6:
        raise ValueError("Copilot plan exceeds bounded evidence-selection limits.")
    return plan
