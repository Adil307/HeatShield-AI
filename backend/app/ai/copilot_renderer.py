from __future__ import annotations

from typing import Any

from app.domain.copilot import CopilotPlan, GroundedClaim
from app.ai.claim_guard import evaluate_structured_claim
from app.ai.copilot_context import CopilotContext, ledger_index


class CopilotRenderError(ValueError):
    pass


def _fmt_value(entry: dict[str, Any]) -> str:
    value = entry.get("value")
    unit = entry.get("unit")
    if isinstance(value, float):
        text = f"{value:.2f}".rstrip("0").rstrip(".")
    else:
        text = str(value)
    if unit == "C":
        return f"{text} C"
    if unit == "percent":
        return f"{text}%"
    if unit == "mapped_objects":
        return f"{text} mapped objects"
    if unit and value is not None:
        return f"{text} {unit}"
    return text


def _claim(packet: dict[str, Any], rank: int, key: str) -> GroundedClaim:
    ledger = ledger_index(packet)
    entry = ledger[key]
    classification = entry.get("classification")
    if classification in {"observed", "derived"}:
        raw = {
            "claim_type": "metric_assertion",
            "metric_key": key,
            "claimed_value": entry.get("value"),
        }
    else:
        raw = {
            "claim_type": "status_assertion",
            "metric_key": key,
            "status": classification,
        }
    decision = evaluate_structured_claim(packet, raw)
    if not decision.approved:
        raise CopilotRenderError(f"Renderer attempted an ungrounded claim for {key}: {decision.reason_code}")
    return GroundedClaim(
        hotspot_rank=rank,
        claim_type=str(raw["claim_type"]),
        metric_key=key,
        claimed_value=raw.get("claimed_value"),
        status=raw.get("status"),
        statement=None,
        guard_reason_code=decision.reason_code,
    )


def _scenario_claim(packet: dict[str, Any], rank: int) -> GroundedClaim:
    raw = {"claim_type": "scenario_statement", "statement": packet.get("scenario_statement")}
    decision = evaluate_structured_claim(packet, raw)
    if not decision.approved:
        raise CopilotRenderError("Scenario statement failed exact grounding.")
    return GroundedClaim(
        hotspot_rank=rank,
        claim_type="scenario_statement",
        metric_key=None,
        claimed_value=None,
        status=None,
        statement=str(packet.get("scenario_statement")),
        guard_reason_code=decision.reason_code,
    )


def render_plan(plan: CopilotPlan, context: CopilotContext) -> dict[str, Any]:
    rank = plan.primary_hotspot_rank or context.planning_order[0]
    packet = context.packets_by_rank[rank]
    ledger = ledger_index(packet)
    claims: list[GroundedClaim] = []
    used_recommendations: list[str] = []

    scenario_claim = _scenario_claim(packet, rank)

    if plan.intent == "scenario_scope":
        text = (
            "HeatShield cannot answer that as current/live heat, a medical risk probability, or a people-exposure count. "
            "This demo is a scenario replay: verified historical FortyGuard thermal evidence is evaluated against current mapped urban context. "
            "I can explain the planning priority, show the historical thermal metrics, list mapped context evidence, or surface controlled recommendations."
        )
        return {
            "answer": text,
            "claims": [scenario_claim.to_dict()],
            "recommendation_ids": [],
            "guard_status": "approved_structured_grounding",
        }

    if plan.intent == "metric_lookup":
        key = plan.metric_keys[0]
        entry = ledger[key]
        claims.append(_claim(packet, rank, key))
        if entry.get("classification") in {"unknown", "withheld"}:
            text = f"{entry.get('label')} for hotspot rank {rank} is {str(entry.get('classification')).upper()}; HeatShield does not invent a value."
        else:
            label = str(entry.get("label"))
            if key.startswith("historical_") and not label.lower().startswith("historical "):
                label = "Historical " + label.lower()
            text = f"{label} for hotspot rank {rank} is {_fmt_value(entry)}."
            if entry.get("unit") == "mapped_objects":
                text += " These are mapped objects, not people or occupancy."
        return {"answer": text, "claims": [item.to_dict() for item in claims], "recommendation_ids": [], "guard_status": "approved_structured_grounding"}

    if plan.intent == "why_priority":
        keys = (
            "hazard_planning_ordinal",
            "mapped_exposure_proxy",
            "context_sensitivity_proxy",
            "pre_adaptation_planning_priority",
        )
        for key in keys:
            claims.append(_claim(packet, rank, key))
        contributions = packet.get("contributions") or []
        by_component = {item.get("component"): item for item in contributions if isinstance(item, dict)}
        text = (
            f"Hotspot rank {rank} has a pre-adaptation planning priority of {float(ledger['pre_adaptation_planning_priority']['value']):.2f}/100. "
            f"Its score decomposes into hazard {float(by_component['hazard']['weighted_points']):.2f} points, "
            f"mapped-exposure {float(by_component['mapped_exposure']['weighted_points']):.2f} points, and "
            f"context-sensitivity {float(by_component['context_sensitivity_proxy']['weighted_points']):.2f} points. "
            "This is a planning priority, not a medical-risk probability."
        )
        return {"answer": text, "claims": [item.to_dict() for item in claims], "recommendation_ids": [], "guard_status": "approved_structured_grounding"}

    if plan.intent == "missing_evidence":
        for key in ("verified_operational_vulnerability", "verified_adaptive_capacity"):
            claims.append(_claim(packet, rank, key))
        text = (
            f"Hotspot rank {rank} still has two required evidence dimensions unverified: operational vulnerability and adaptive capacity. "
            "Because both remain UNKNOWN, the evidence-adjusted priority is withheld. The controlled actions ask an operator to verify workload/acclimatization/PPE and protective controls such as water, recovery, work-rest, and training or monitoring."
        )
        recs = context.recommendations_by_rank[rank].get("recommendations", [])
        used_recommendations = [
            rec["recommendation_id"]
            for rec in recs
            if isinstance(rec, dict) and rec.get("action_type") == "evidence_verification"
        ]
        return {"answer": text, "claims": [item.to_dict() for item in claims], "recommendation_ids": used_recommendations, "guard_status": "approved_structured_grounding"}

    if plan.intent == "recommendations":
        recs = context.recommendations_by_rank[rank].get("recommendations", [])
        selected = set(plan.recommendation_ids)
        chosen = [rec for rec in recs if isinstance(rec, dict) and rec.get("recommendation_id") in selected]
        if not chosen:
            chosen = [rec for rec in recs if isinstance(rec, dict)][:5]
        lines = [f"Controlled actions for hotspot rank {rank}:"]
        for rec in chosen[:5]:
            lines.append(f"{rec.get('priority_tier')} - {rec.get('title')}: {rec.get('recommendation')}")
            used_recommendations.append(str(rec.get("recommendation_id")))
        lines.append("These are catalog-controlled verification/assessment actions, not medical advice or guaranteed intervention effects.")
        return {"answer": "\n".join(lines), "claims": [], "recommendation_ids": used_recommendations, "guard_status": "approved_controlled_recommendations"}

    if plan.intent == "compare_hotspots":
        ranks = plan.comparison_hotspot_ranks or context.planning_order
        pieces: list[str] = []
        for candidate_rank in ranks:
            candidate = context.packets_by_rank[candidate_rank]
            candidate_ledger = ledger_index(candidate)
            claims.append(_claim(candidate, candidate_rank, "pre_adaptation_planning_priority"))
            claims.append(_claim(candidate, candidate_rank, "historical_air_temperature_celsius"))
            pieces.append(
                f"rank {candidate_rank}: priority {float(candidate_ledger['pre_adaptation_planning_priority']['value']):.2f}/100, "
                f"historical air temperature {float(candidate_ledger['historical_air_temperature_celsius']['value']):.4f} C"
            )
        top = context.planning_order[0]
        text = "Comparison - " + "; ".join(pieces) + f". By the verified Day-8 planning order, hotspot rank {top} is the highest planning priority. This ordering is not the same thing as simply choosing the hottest tile."
        return {"answer": text, "claims": [item.to_dict() for item in claims], "recommendation_ids": [], "guard_status": "approved_structured_grounding"}

    # summary / unsupported fallback
    summary_keys = (
        "historical_heat_index_celsius",
        "pre_adaptation_planning_priority",
        "verified_operational_vulnerability",
        "verified_adaptive_capacity",
    )
    for key in summary_keys:
        claims.append(_claim(packet, rank, key))
    recs = context.recommendations_by_rank[rank].get("recommendations", [])
    top_actions = [rec for rec in recs if isinstance(rec, dict)][:2]
    used_recommendations = [str(rec.get("recommendation_id")) for rec in top_actions]
    text = (
        f"Hotspot rank {rank} has a pre-adaptation planning priority of {float(ledger['pre_adaptation_planning_priority']['value']):.2f}/100 "
        f"under a scenario replay using a historical heat index of {float(ledger['historical_heat_index_celsius']['value']):.1f} C. "
        "Verified operational vulnerability and adaptive capacity are still UNKNOWN, so the adjusted priority remains withheld. "
        "The first controlled actions are to verify protective heat controls and verify operational vulnerability factors."
    )
    return {"answer": text, "claims": [item.to_dict() for item in claims], "recommendation_ids": used_recommendations, "guard_status": "approved_structured_grounding"}
