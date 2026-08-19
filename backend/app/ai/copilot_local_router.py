from __future__ import annotations

from app.ai.copilot_context import CopilotContext
from app.domain.copilot import CopilotPlan


WHY_PRIORITY_METRICS = (
    "hazard_planning_ordinal",
    "mapped_exposure_proxy",
    "context_sensitivity_proxy",
    "pre_adaptation_planning_priority",
)

MISSING_EVIDENCE_METRICS = (
    "verified_operational_vulnerability",
    "verified_adaptive_capacity",
)

# Deterministic parsing is already strong for these explicit/safety-sensitive
# intents. A small local model may enrich ambiguous requests, but it cannot
# downgrade or redirect a deterministic match.
_DETERMINISTIC_AUTHORITATIVE_INTENTS = {
    "scenario_scope",
    "why_priority",
    "recommendations",
    "missing_evidence",
    "compare_hotspots",
    "metric_lookup",
}


def materialize_local_route(
    *,
    route: CopilotPlan,
    deterministic_fallback: CopilotPlan,
    context: CopilotContext,
) -> tuple[CopilotPlan, tuple[str, ...]]:
    """Convert a small-model semantic route into a fully grounded CopilotPlan.

    Qwen is intentionally not trusted to copy evidence IDs or recommendation
    IDs. Exact identifiers, hotspot scope, and safety-sensitive intent routing
    are resolved deterministically from verified HeatShield artifacts.
    """
    corrections: list[str] = []

    if deterministic_fallback.intent in _DETERMINISTIC_AUTHORITATIVE_INTENTS:
        intent = deterministic_fallback.intent
        if route.intent != intent:
            reason = (
                "scenario_scope_safety_override"
                if intent == "scenario_scope"
                else "deterministic_intent_override"
            )
            corrections.append(reason)
    else:
        intent = route.intent

    # Explicit hotspot/tile resolution remains deterministic so the local model
    # cannot silently move a user's request to a different hotspot.
    rank = deterministic_fallback.primary_hotspot_rank
    if route.primary_hotspot_rank != rank:
        corrections.append("primary_rank_resolved_deterministically")

    planner = "ollama_qwen_intent_router+deterministic_materializer"

    if intent == "summary":
        return (
            CopilotPlan(intent="summary", primary_hotspot_rank=rank, planner=planner),
            tuple(corrections),
        )

    if intent == "why_priority":
        return (
            CopilotPlan(
                intent="why_priority",
                primary_hotspot_rank=rank,
                metric_keys=WHY_PRIORITY_METRICS,
                planner=planner,
            ),
            tuple(corrections),
        )

    if intent == "recommendations":
        if rank is None:
            return (
                CopilotPlan(intent="unsupported", planner=planner),
                tuple(corrections + ["missing_target_rank"]),
            )
        recs = context.recommendations_by_rank[rank].get("recommendations", [])
        rec_ids = tuple(
            rec["recommendation_id"]
            for rec in recs
            if isinstance(rec, dict) and isinstance(rec.get("recommendation_id"), str)
        )
        return (
            CopilotPlan(
                intent="recommendations",
                primary_hotspot_rank=rank,
                recommendation_ids=rec_ids,
                planner=planner,
            ),
            tuple(corrections),
        )

    if intent == "missing_evidence":
        return (
            CopilotPlan(
                intent="missing_evidence",
                primary_hotspot_rank=rank,
                metric_keys=MISSING_EVIDENCE_METRICS,
                planner=planner,
            ),
            tuple(corrections),
        )

    if intent == "compare_hotspots":
        return (
            CopilotPlan(
                intent="compare_hotspots",
                primary_hotspot_rank=rank,
                comparison_hotspot_ranks=context.planning_order,
                planner=planner,
            ),
            tuple(corrections),
        )

    if intent == "metric_lookup":
        # Metric identity is never delegated to Qwen. The deterministic alias
        # resolver must have recognized the exact evidence key.
        if (
            deterministic_fallback.intent == "metric_lookup"
            and deterministic_fallback.metric_keys
        ):
            return (
                CopilotPlan(
                    intent="metric_lookup",
                    primary_hotspot_rank=rank,
                    metric_keys=deterministic_fallback.metric_keys,
                    planner=planner,
                ),
                tuple(corrections),
            )
        corrections.append("metric_identity_not_grounded")
        return (
            CopilotPlan(intent="unsupported", primary_hotspot_rank=rank, planner=planner),
            tuple(corrections),
        )

    if intent == "scenario_scope":
        return (
            CopilotPlan(intent="scenario_scope", primary_hotspot_rank=rank, planner=planner),
            tuple(corrections),
        )

    return (
        CopilotPlan(intent="unsupported", primary_hotspot_rank=rank, planner=planner),
        tuple(corrections),
    )
