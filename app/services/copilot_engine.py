from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.domain.copilot import CopilotPlan
from app.providers.copilot_openai import CopilotProviderError, openai_plan
from app.services.copilot_context import CopilotContext, compact_llm_context, load_copilot_context
from app.services.copilot_planner import deterministic_plan, validate_plan
from app.services.copilot_renderer import render_plan


class CopilotEngineError(ValueError):
    pass


async def answer_copilot(
    *,
    query: str,
    settings: Settings,
    day7_path: str | Path,
    day8_path: str | Path,
    day6_path: str | Path | None = None,
    day5_path: str | Path | None = None,
    day44_path: str | Path | None = None,
    catalog_path: str | Path | None = None,
    mode: str = "auto",
    preferred_hotspot_rank: int | None = None,
) -> dict[str, Any]:
    if not isinstance(query, str) or not query.strip():
        raise CopilotEngineError("Copilot query must be non-empty.")
    if mode not in {"auto", "deterministic", "openai"}:
        raise CopilotEngineError("Copilot mode must be auto, deterministic, or openai.")

    context: CopilotContext = load_copilot_context(
        day7_path=day7_path,
        day8_path=day8_path,
        day6_path=day6_path,
        day5_path=day5_path,
        day44_path=day44_path,
        catalog_path=catalog_path,
    )
    fallback_plan = deterministic_plan(query, context, preferred_hotspot_rank=preferred_hotspot_rank)
    selected_plan: CopilotPlan = validate_plan(fallback_plan, context)

    provider = "deterministic_guarded_planner"
    llm_calls = 0
    llm_fallback = False
    provider_error: str | None = None
    openai_enabled = settings.copilot_provider.lower() == "openai" and settings.openai_api_key_configured
    should_try_openai = mode == "openai" or (mode == "auto" and openai_enabled)

    if should_try_openai:
        if not settings.openai_api_key_configured:
            if mode == "openai":
                raise CopilotEngineError("OpenAI mode requested but OPENAI_API_KEY is not configured.")
        else:
            llm_calls = 1
            try:
                llm_plan = await openai_plan(
                    query=query,
                    compact_context=compact_llm_context(context),
                    api_key=settings.openai_api_key,
                    model=settings.copilot_model,
                    timeout_seconds=settings.copilot_timeout_seconds,
                    max_output_tokens=settings.copilot_max_output_tokens,
                )
                selected_plan = validate_plan(llm_plan, context)
                provider = "openai_responses_structured_planner"
            except (CopilotProviderError, ValueError) as exc:
                if mode == "openai":
                    raise CopilotEngineError(f"OpenAI copilot planning failed: {exc}") from exc
                llm_fallback = True
                provider_error = str(exc)
                selected_plan = validate_plan(fallback_plan, context)

    rendered = render_plan(selected_plan, context)
    return {
        "schema_version": "heatshield.day9.copilot_response.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "mode_requested": mode,
        "planner": provider,
        "plan": selected_plan.to_dict(),
        "answer": rendered["answer"],
        "grounding": {
            "guard_status": rendered["guard_status"],
            "structured_claims": rendered["claims"],
            "approved_structured_claim_count": len(rendered["claims"]),
            "controlled_recommendation_ids": rendered["recommendation_ids"],
            "day7_artifact_sha256": context.day7_sha256,
            "day8_artifact_sha256": context.day8_sha256,
        },
        "safety": {
            "llm_writes_final_factual_answer": False,
            "final_answer_renderer": "deterministic_evidence_renderer",
            "medical_probability_supported": False,
            "historical_hazard_is_current_heat": False,
            "mapped_objects_are_people": False,
            "free_form_action_invention_allowed": False,
        },
        "runtime": {
            "llm_calls": llm_calls,
            "llm_fallback_used": llm_fallback,
            "provider_error": provider_error,
            "new_fortyguard_calls": 0,
            "new_overpass_calls": 0,
        },
    }
