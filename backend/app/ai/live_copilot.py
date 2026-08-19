from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.config import Settings
from app.providers.live_copilot_ollama import LiveOllamaRouterError, ollama_live_intent
from app.services.live_context_priority import (
    Day13ContextPriorityRequest,
    LiveContextPriorityError,
    run_live_context_priority,
)
from app.services.live_decision_readiness import LiveDecisionReadinessError, run_live_decision_readiness
from app.services.live_thermal_analysis import LiveThermalAnalysisError, run_live_thermal_analysis


class LiveCopilotError(ValueError):
    """Raised when the Day 14 live copilot cannot build a grounded answer."""


class Day14LiveCopilotRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    mode: Literal["auto", "deterministic", "ollama"] = "auto"
    context_request: Day13ContextPriorityRequest


_METRIC_ALIASES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("heat index",), "heat_index_celsius"),
    (("apparent temperature", "feels like"), "apparent_temperature_celsius"),
    (("wet bulb", "wet-bulb"), "wet_bulb_temperature_celsius"),
    (("humidity", "relative humidity"), "relative_humidity_percent"),
    (("air temperature", "temperature", "temp"), "air_temperature_celsius"),
    (("hazard ordinal", "hazard score", "thermal hazard"), "hazard_planning_ordinal"),
    (("pre-adaptation", "pre adaptation"), "pre_adaptation_priority_score"),
    (("planning priority", "priority score", "final priority", "evidence-adjusted priority"), "evidence_adjusted_priority_score"),
    (("exposure score", "exposure context"), "verified_exposure_score"),
    (("vulnerability score", "operational vulnerability"), "verified_operational_vulnerability_score"),
    (("adaptive capacity", "protection score"), "verified_adaptive_capacity_score"),
    (("operational adjustment", "adjustment"), "operational_adjustment_points"),
)

_MEDICAL = re.compile(
    r"\b(?:medical|clinical|illness|mortality|diagnosis|diagnostic|health)\b.{0,40}\b(?:risk|probability|chance|percentage|diagnosis)\b",
    re.I,
)
_PEOPLE = re.compile(r"\b(?:how many|number of|count of)\s+(?:people|persons|students|patients|workers|children)\b", re.I)
_INDIVIDUAL = re.compile(r"\b(?:this person|this worker|individual|patient)\b.{0,35}\b(?:safe|danger|risk|ill|sick|heatstroke)\b", re.I)


def _metric_key(query: str) -> str | None:
    normalized = " ".join(query.lower().split())
    for aliases, key in _METRIC_ALIASES:
        if any(alias in normalized for alias in aliases):
            return key
    return None


def deterministic_live_intent(query: str) -> tuple[str, str | None]:
    normalized = " ".join(query.lower().split())
    metric_key = _metric_key(normalized)

    if _MEDICAL.search(normalized) or _PEOPLE.search(normalized) or _INDIVIDUAL.search(normalized):
        return "scope_boundary", metric_key
    if any(token in normalized for token in ("compare", "difference", "which tile", "which hotspot", "rank the", "ranking")):
        return "compare_scope", metric_key
    if any(token in normalized for token in ("recommend", "action", "what should", "what can we do", "next step", "intervention")):
        return "recommendations", metric_key
    if any(token in normalized for token in ("source", "evidence", "provenance", "trace", "activity id", "where did", "where from")):
        return "evidence", metric_key
    if any(token in normalized for token in ("missing", "verified", "supported", "withheld", "ready", "readiness", "can we conclude", "confidence")):
        return "decision_readiness", metric_key
    if any(token in normalized for token in ("why", "priority", "contribution", "factor", "decompose", "composition")):
        return "why_priority", metric_key
    if metric_key is not None:
        return "metric_lookup", metric_key
    return "summary", None


def _fmt_number(value: Any, digits: int = 1) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "unavailable"
    return f"{float(value):.{digits}f}".rstrip("0").rstrip(".")


def _humanize(value: Any) -> str:
    text = str(value or "").replace("_", " ").replace("-", " ").strip()
    return " ".join(part.capitalize() for part in text.split()) if text else "Unavailable"


def _refs(readiness: dict[str, Any], priority: dict[str, Any]) -> list[dict[str, str]]:
    prov = priority.get("provenance") or {}
    selected = readiness.get("selected_hotspot") or {}
    refs: list[dict[str, str]] = []
    candidates = [
        ("thermal", selected.get("thermal_evidence_id") or prov.get("thermal_evidence_id"), "FortyGuard thermal evidence"),
        ("environmental", prov.get("environmental_evidence_id"), "FortyGuard environmental evidence"),
        ("context", prov.get("context_evidence_id"), "Authorized operational context"),
    ]
    for kind, ref, label in candidates:
        if isinstance(ref, str) and ref:
            refs.append({"kind": kind, "evidence_id": ref, "label": label})
    return refs


def _ledger(readiness: dict[str, Any], priority_result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    selected = readiness.get("selected_hotspot") or {}
    observed = readiness.get("environmental_observed") or {}
    derived = readiness.get("environmental_derived") or {}
    priority = priority_result.get("priority") or {}
    context = priority_result.get("verified_context") or {}
    refs = _refs(readiness, priority_result)
    thermal_ref = [r for r in refs if r["kind"] == "thermal"]
    env_ref = [r for r in refs if r["kind"] == "environmental"]
    context_ref = [r for r in refs if r["kind"] == "context"]
    all_refs = refs

    return {
        "air_temperature_celsius": {
            "label": "Fresh air temperature",
            "value": selected.get("temperature_celsius"),
            "unit": "C",
            "classification": "OBSERVED",
            "evidence_refs": thermal_ref,
        },
        "heat_index_celsius": {
            "label": "Fresh heat index",
            "value": observed.get("heat_index_celsius"),
            "unit": "C",
            "classification": "OBSERVED",
            "evidence_refs": env_ref,
        },
        "apparent_temperature_celsius": {
            "label": "Fresh apparent temperature",
            "value": observed.get("apparent_temperature_celsius"),
            "unit": "C",
            "classification": "OBSERVED",
            "evidence_refs": env_ref,
        },
        "wet_bulb_temperature_celsius": {
            "label": "Fresh wet-bulb temperature",
            "value": observed.get("wet_bulb_temperature_celsius"),
            "unit": "C",
            "classification": "OBSERVED",
            "evidence_refs": env_ref,
        },
        "relative_humidity_percent": {
            "label": "Fresh relative humidity",
            "value": observed.get("relative_humidity_percent"),
            "unit": "percent",
            "classification": "OBSERVED",
            "evidence_refs": env_ref,
        },
        "hazard_planning_ordinal": {
            "label": "Hazard planning ordinal",
            "value": priority.get("hazard_planning_ordinal"),
            "unit": "score_0_100",
            "classification": "DERIVED",
            "evidence_refs": env_ref,
        },
        "pre_adaptation_priority_score": {
            "label": "Pre-adaptation planning priority",
            "value": priority.get("pre_adaptation_priority_score"),
            "unit": "score_0_100",
            "classification": "DERIVED",
            "evidence_refs": all_refs,
        },
        "evidence_adjusted_priority_score": {
            "label": "Evidence-adjusted planning priority",
            "value": priority.get("evidence_adjusted_priority_score"),
            "unit": "score_0_100",
            "classification": "DERIVED",
            "evidence_refs": all_refs,
        },
        "operational_adjustment_points": {
            "label": "Operational adjustment",
            "value": priority.get("operational_adjustment_points"),
            "unit": "points",
            "classification": "DERIVED",
            "evidence_refs": context_ref,
        },
        "verified_exposure_score": {
            "label": "Verified exposure score",
            "value": context.get("verified_exposure_score"),
            "unit": "score_0_100",
            "classification": "OBSERVED_CONTEXT",
            "evidence_refs": context_ref,
        },
        "verified_operational_vulnerability_score": {
            "label": "Verified operational vulnerability score",
            "value": context.get("verified_operational_vulnerability_score"),
            "unit": "score_0_100",
            "classification": "OBSERVED_CONTEXT",
            "evidence_refs": context_ref,
        },
        "verified_adaptive_capacity_score": {
            "label": "Verified adaptive-capacity score",
            "value": context.get("verified_adaptive_capacity_score"),
            "unit": "score_0_100",
            "classification": "OBSERVED_CONTEXT",
            "evidence_refs": context_ref,
        },
    }


def _metric_text(entry: dict[str, Any]) -> str:
    value = entry.get("value")
    unit = entry.get("unit")
    if value is None:
        return "unavailable"
    digits = 2 if unit == "C" else 1
    text = _fmt_number(value, digits)
    if unit == "C":
        return f"{text} C"
    if unit == "percent":
        return f"{text}%"
    if unit == "score_0_100":
        return f"{text}/100"
    if unit == "points":
        sign = "+" if isinstance(value, (int, float)) and value > 0 else ""
        return f"{sign}{text} points"
    return text


def _claim(key: str, ledger: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if key not in ledger:
        raise LiveCopilotError(f"Live renderer requested unsupported metric key: {key}")
    entry = ledger[key]
    return {
        "metric_key": key,
        "label": entry.get("label"),
        "value": entry.get("value"),
        "unit": entry.get("unit"),
        "classification": entry.get("classification"),
        "evidence_ids": [ref["evidence_id"] for ref in entry.get("evidence_refs", [])],
        "guard_status": "approved_from_verified_live_ledger",
    }


def _render(
    *,
    intent: str,
    metric_key: str | None,
    thermal: dict[str, Any],
    readiness: dict[str, Any],
    priority_result: dict[str, Any],
    ledger: dict[str, dict[str, Any]],
) -> tuple[str, list[dict[str, Any]], list[str]]:
    selected = readiness.get("selected_hotspot") or {}
    priority = priority_result.get("priority") or {}
    context = priority_result.get("verified_context") or {}
    recommendations = priority_result.get("recommendations") or []
    claims: list[dict[str, Any]] = []
    recommendation_ids: list[str] = []
    tile_id = selected.get("tile_id")

    if intent == "scope_boundary":
        return (
            "This live evidence supports an operational planning priority, not an individual medical-risk probability, diagnosis, or people/occupancy count. "
            "I can explain the verified temperature and thermal-stress evidence, the transparent planning score, the authorized operational context, or the controlled action catalog.",
            claims,
            recommendation_ids,
        )

    if intent == "metric_lookup" and metric_key:
        entry = ledger.get(metric_key)
        if entry is None:
            raise LiveCopilotError("Requested live metric is not in the verified ledger.")
        claims.append(_claim(metric_key, ledger))
        return (
            f"{entry['label']} for the current verified hottest tile {tile_id} is {_metric_text(entry)}. "
            f"This value is classified as {str(entry.get('classification')).replace('_', ' ').lower()} evidence in the Day 14 live packet.",
            claims,
            recommendation_ids,
        )

    if intent == "why_priority":
        for key in (
            "hazard_planning_ordinal",
            "pre_adaptation_priority_score",
            "evidence_adjusted_priority_score",
            "verified_exposure_score",
            "verified_operational_vulnerability_score",
            "verified_adaptive_capacity_score",
        ):
            claims.append(_claim(key, ledger))
        contributions = priority.get("contributions") or {}
        hazard = float(contributions.get("hazard_points") or 0.0)
        exposure = float(contributions.get("exposure_points") or 0.0)
        sensitive = float(contributions.get("sensitive_use_points") or 0.0)
        vulnerability = float(contributions.get("vulnerability_adjustment_points") or 0.0)
        adaptive = float(contributions.get("adaptive_capacity_reduction_points") or 0.0)
        adjusted = float(priority.get("evidence_adjusted_priority_score"))
        pre = float(priority.get("pre_adaptation_priority_score"))
        return (
            f"The current live hottest tile {tile_id} has an evidence-adjusted planning priority of {adjusted:.2f}/100. "
            f"The pre-adaptation score is {pre:.2f}/100: thermal hazard contributes {hazard:.2f} points, verified exposure {exposure:.2f}, and sensitive-use context {sensitive:.2f}. "
            f"Verified operational vulnerability then contributes {vulnerability:+.2f} points and adaptive capacity contributes {adaptive:+.2f} points, producing the final score. "
            "This is a transparent operational planning index, not a medical-risk probability.",
            claims,
            recommendation_ids,
        )

    if intent == "recommendations":
        if recommendations:
            lines = ["The current live evidence triggers only these controlled catalog actions:"]
            for action in recommendations[:5]:
                action_id = str(action.get("action_id") or "")
                recommendation_ids.append(action_id)
                lines.append(f"- {action.get('title')}: {action.get('recommendation')}")
            lines.append("The assistant did not invent these actions; they come from the Day 8 controlled catalog and are shown only when their documented trigger is satisfied.")
            return "\n".join(lines), claims, recommendation_ids
        policy = priority_result.get("recommendation_policy") or {}
        return (
            str(policy.get("no_trigger_message") or "No controlled catalog action is triggered by the current verified live evidence."),
            claims,
            recommendation_ids,
        )

    if intent == "evidence":
        prov = priority_result.get("provenance") or {}
        thermal_activity = prov.get("thermal_activity_id") or "unavailable"
        environmental_activity = prov.get("environmental_activity_id") or "unavailable"
        source_ref = context.get("source_ref") or "unavailable"
        model = priority.get("model_version") or "unavailable"
        return (
            f"The live decision chain is traceable to FortyGuard thermal activity {thermal_activity}, FortyGuard environmental activity {environmental_activity}, "
            f"authorized operational context source '{source_ref}', and transparent priority model {model}. "
            "The Day 14 assistant reconstructs this packet from verified caches and context; it makes no new FortyGuard request while answering.",
            claims,
            recommendation_ids,
        )

    if intent == "decision_readiness":
        return (
            "For this live hottest tile, thermal evidence, thermal-stress enrichment, exposure context, operational vulnerability, and adaptive capacity are all verified, so the operational planning priority is supported. "
            "Individual medical-risk probability and people/occupancy counts remain unsupported. A full priority comparison with the other live tiles is also not supported until each comparison tile receives equivalent thermal-stress enrichment and authorized context.",
            claims,
            recommendation_ids,
        )

    if intent == "compare_scope":
        hottest = thermal.get("hottest_tiles") or []
        pieces = []
        for item in hottest[:3]:
            if not isinstance(item, dict):
                continue
            pieces.append(
                f"tile {item.get('tile_id')} at {_fmt_number(item.get('temperature_celsius'), 2)} C"
            )
        thermal_text = "; ".join(pieces) if pieces else "no comparable hottest-tile temperatures are available"
        return (
            f"The live thermal layer can compare relative hottest-tile temperatures: {thermal_text}. "
            f"However, only tile {tile_id} has the Day 12 thermal-stress enrichment and Day 13 authorized context needed for a full planning priority. "
            "HeatShield therefore does not rank the other live tiles by full decision priority yet.",
            claims,
            recommendation_ids,
        )

    # summary fallback
    for key in ("air_temperature_celsius", "heat_index_celsius", "evidence_adjusted_priority_score"):
        claims.append(_claim(key, ledger))
    band = _humanize(priority.get("evidence_adjusted_priority_band"))
    return (
        f"This is a fresh provider-backed analysis of the current selected area. The verified hottest tile {tile_id} has air temperature {_metric_text(ledger['air_temperature_celsius'])} "
        f"and heat index {_metric_text(ledger['heat_index_celsius'])}. After the authorized operational context is applied, the evidence-adjusted planning priority is "
        f"{_metric_text(ledger['evidence_adjusted_priority_score'])}, classified as {band}. The score is for operational planning only, not medical-risk prediction.",
        claims,
        recommendation_ids,
    )


async def answer_live_copilot(
    request: Day14LiveCopilotRequest,
    *,
    settings: Settings,
    live_cache_dir: str | Path,
    env_cache_dir: str | Path,
    catalog_path: str | Path,
) -> dict[str, Any]:
    """Answer a question over the exact Day 11/12/13 live evidence packet.

    The factual answer is deterministic. Local Qwen may route an ambiguous query,
    but it never receives numeric evidence and never writes the final answer.
    """
    try:
        thermal = await run_live_thermal_analysis(
            request.context_request.analysis_request,
            client=None,
            cache_dir=live_cache_dir,
        )
        readiness = await run_live_decision_readiness(
            request.context_request.analysis_request,
            client=None,
            live_cache_dir=live_cache_dir,
            env_cache_dir=env_cache_dir,
        )
        priority_result = await run_live_context_priority(
            request.context_request,
            live_cache_dir=live_cache_dir,
            env_cache_dir=env_cache_dir,
            catalog_path=catalog_path,
        )
    except (LiveThermalAnalysisError, LiveDecisionReadinessError, LiveContextPriorityError) as exc:
        raise LiveCopilotError(
            "Complete the Day 11 thermal analysis, Day 12 hottest-tile enrichment, and Day 13 context verification before using the live copilot."
        ) from exc

    ledger = _ledger(readiness, priority_result)
    deterministic_intent, metric_key = deterministic_live_intent(request.query)
    selected_intent = deterministic_intent
    planner = "deterministic_live_router"
    llm_calls = 0
    llm_fallback = False
    provider_error: str | None = None
    route_corrections: list[str] = []

    authoritative = {
        "scope_boundary",
        "compare_scope",
        "recommendations",
        "evidence",
        "decision_readiness",
        "why_priority",
        "metric_lookup",
    }

    provider = settings.copilot_provider.strip().lower()
    should_try_ollama = request.mode == "ollama" or (request.mode == "auto" and provider == "ollama")
    if should_try_ollama:
        llm_calls = 1
        try:
            qwen_intent = await ollama_live_intent(
                query=request.query,
                compact_context={
                    "planning_priority_supported": True,
                    "controlled_actions_available": bool(priority_result.get("recommendations")),
                    "available_metric_keys": sorted(ledger),
                },
                base_url=settings.ollama_base_url,
                model=settings.ollama_model,
                timeout_seconds=settings.ollama_timeout_seconds,
                max_output_tokens=settings.copilot_max_output_tokens,
                keep_alive=settings.ollama_keep_alive,
            )
            if deterministic_intent in authoritative:
                selected_intent = deterministic_intent
                if qwen_intent != deterministic_intent:
                    route_corrections.append("deterministic_safety_or_exact_intent_override")
            else:
                selected_intent = qwen_intent
            if selected_intent == "metric_lookup" and metric_key is None:
                selected_intent = "summary"
                route_corrections.append("metric_identity_not_grounded")
            planner = "ollama_qwen_live_intent_router+deterministic_renderer"
        except LiveOllamaRouterError as exc:
            if request.mode == "ollama":
                raise LiveCopilotError(f"Local Qwen live routing failed: {exc}") from exc
            llm_fallback = True
            provider_error = str(exc)
            selected_intent = deterministic_intent
            planner = "deterministic_live_router_fallback"

    answer, claims, recommendation_ids = _render(
        intent=selected_intent,
        metric_key=metric_key,
        thermal=thermal,
        readiness=readiness,
        priority_result=priority_result,
        ledger=ledger,
    )
    evidence_refs = _refs(readiness, priority_result)

    return {
        "schema_version": "heatshield.day14.live_grounded_copilot.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "fresh_verified_live_analysis",
        "query": request.query,
        "intent": selected_intent,
        "answer": answer,
        "evidence_refs": evidence_refs,
        "grounding": {
            "guard_status": "approved_live_evidence_guard",
            "claims": claims,
            "approved_claim_count": len(claims),
            "controlled_recommendation_ids": recommendation_ids,
            "context_evidence_id": (priority_result.get("provenance") or {}).get("context_evidence_id"),
            "final_answer_renderer": "deterministic_live_evidence_renderer",
        },
        "runtime": {
            "planner": planner,
            "llm_calls": llm_calls,
            "llm_fallback_used": llm_fallback,
            "provider_error": provider_error,
            "local_inference": planner.startswith("ollama_qwen_"),
            "route_corrections": route_corrections,
            "new_fortyguard_calls": 0,
            "new_environmental_calls": 0,
            "new_overpass_calls": 0,
        },
        "safety": {
            "live_evidence_mode": True,
            "llm_writes_final_factual_answer": False,
            "medical_probability_supported": False,
            "people_or_occupancy_inference_supported": False,
            "free_form_action_invention_allowed": False,
            "full_priority_comparison_requires_equivalent_context_per_tile": True,
        },
    }
