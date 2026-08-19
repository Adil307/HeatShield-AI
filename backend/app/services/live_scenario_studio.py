from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.live_context_priority import (
    Day13ContextPriorityRequest,
    Day13ContextProfile,
    LiveContextPriorityError,
    _context_scores,
    run_live_context_priority,
)
from app.services.priority_engine import priority_band, weighted_pre_adaptation_score
from app.services.site_evidence_engine import evidence_adjusted_score


class LiveScenarioStudioError(ValueError):
    """Raised when a Day 15 scenario cannot be evaluated safely."""


class Day15ScenarioChanges(BaseModel):
    """Explicit hypothetical overrides for operational planning factors.

    Every populated field is an assumption for scenario comparison. None of these
    fields are reclassified as observed or verified evidence.
    """

    exposure_level: Literal["none", "low", "moderate", "high"] | None = None
    sensitive_use_context: Literal[
        "none", "education", "healthcare", "education_and_healthcare"
    ] | None = None
    physical_exertion: Literal["low", "moderate", "high"] | None = None
    acclimatization_gap: Literal["none", "partial", "substantial"] | None = None
    heat_trapping_ppe_or_clothing: Literal["none", "some", "substantial"] | None = None
    potable_water_access: Literal["absent", "partial", "adequate"] | None = None
    shaded_or_cooled_recovery: Literal["absent", "partial", "adequate"] | None = None
    work_rest_controls: Literal["absent", "partial", "adequate"] | None = None
    heat_training_and_monitoring: Literal["absent", "partial", "adequate"] | None = None

    @model_validator(mode="after")
    def require_at_least_one_change(self):
        if not any(value is not None for value in self.model_dump().values()):
            raise ValueError("At least one explicit scenario change is required.")
        return self


class Day15ScenarioRequest(BaseModel):
    context_request: Day13ContextPriorityRequest
    scenario_label: str = Field(min_length=3, max_length=120)
    scenario_changes: Day15ScenarioChanges

    @field_validator("scenario_label")
    @classmethod
    def clean_label(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 3:
            raise ValueError("scenario_label must describe the hypothetical change.")
        return cleaned


_FIELD_LABELS = {
    "exposure_level": "Meaningful exposure level",
    "sensitive_use_context": "Sensitive-use context",
    "physical_exertion": "Physical exertion",
    "acclimatization_gap": "Acclimatization gap",
    "heat_trapping_ppe_or_clothing": "Heat-trapping PPE or clothing",
    "potable_water_access": "Potable water access",
    "shaded_or_cooled_recovery": "Shaded / cooled recovery",
    "work_rest_controls": "Work-rest controls",
    "heat_training_and_monitoring": "Heat training and monitoring",
}


def _scenario_assumption_id(
    *,
    context_evidence_id: str,
    label: str,
    changes: Day15ScenarioChanges,
) -> str:
    canonical = json.dumps(
        {
            "context_evidence_id": context_evidence_id,
            "scenario_label": label,
            "scenario_changes": changes.model_dump(mode="json", exclude_none=True),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return "hs_live_scenario_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]


def _apply_changes(
    base_profile: Day13ContextProfile,
    changes: Day15ScenarioChanges,
) -> tuple[Day13ContextProfile, list[dict[str, str]]]:
    payload = base_profile.model_dump(mode="json")
    applied: list[dict[str, str]] = []

    for field, after in changes.model_dump(mode="json", exclude_none=True).items():
        before = payload.get(field)
        if before == after:
            continue
        payload[field] = after
        applied.append(
            {
                "field": field,
                "label": _FIELD_LABELS[field],
                "before": str(before),
                "after": str(after),
                "classification": "ASSUMED",
            }
        )

    if not applied:
        raise LiveScenarioStudioError(
            "The selected scenario does not change the verified baseline context. Choose a different scenario assumption."
        )

    # Reuse Day 13 validation for categorical domains/timestamps, while keeping the
    # resulting profile inside this service classified as hypothetical scenario input.
    return Day13ContextProfile.model_validate(payload), applied


def _contributions(*, hazard: float, scores: dict[str, float]) -> dict[str, float]:
    return {
        "hazard_points": round(0.60 * hazard, 4),
        "exposure_points": round(0.30 * scores["verified_exposure_score"], 4),
        "sensitive_use_points": round(0.10 * scores["verified_sensitive_use_proxy"], 4),
        "vulnerability_adjustment_points": round(
            0.15 * scores["verified_operational_vulnerability_score"], 4
        ),
        "adaptive_capacity_reduction_points": round(
            -0.15 * scores["verified_adaptive_capacity_score"], 4
        ),
    }


async def run_live_scenario_studio(
    request: Day15ScenarioRequest,
    *,
    live_cache_dir: str | Path,
    env_cache_dir: str | Path,
    catalog_path: str | Path,
) -> dict[str, Any]:
    """Compare a verified live baseline with explicit hypothetical context changes.

    Day 15 v1 intentionally holds the verified thermal hazard constant. It performs
    zero provider calls, predicts no temperature reduction, and labels changed
    operational factors as assumptions rather than observations.
    """

    try:
        baseline = await run_live_context_priority(
            request.context_request,
            live_cache_dir=live_cache_dir,
            env_cache_dir=env_cache_dir,
            catalog_path=catalog_path,
        )
    except LiveContextPriorityError as exc:
        raise LiveScenarioStudioError(
            "Complete Day 13 context verification first. Scenario Studio requires a fully grounded live baseline."
        ) from exc

    baseline_priority = baseline.get("priority") or {}
    baseline_context = baseline.get("verified_context") or {}
    hazard = baseline_priority.get("hazard_planning_ordinal")
    baseline_adjusted = baseline_priority.get("evidence_adjusted_priority_score")
    if isinstance(hazard, bool) or not isinstance(hazard, (int, float)):
        raise LiveScenarioStudioError("Verified live hazard is missing from the Day 13 baseline.")
    if isinstance(baseline_adjusted, bool) or not isinstance(baseline_adjusted, (int, float)):
        raise LiveScenarioStudioError("Verified live planning priority is missing from the Day 13 baseline.")

    scenario_profile, applied_changes = _apply_changes(
        request.context_request.context_profile,
        request.scenario_changes,
    )
    scenario_scores = _context_scores(scenario_profile)

    scenario_pre = weighted_pre_adaptation_score(
        hazard_score=float(hazard),
        exposure_score=scenario_scores["verified_exposure_score"],
        sensitivity_proxy=scenario_scores["verified_sensitive_use_proxy"],
        weight_set="baseline_v1",
    )
    scenario_adjusted, scenario_adjustment = evidence_adjusted_score(
        pre_adaptation_priority_score=scenario_pre,
        vulnerability_score=scenario_scores["verified_operational_vulnerability_score"],
        adaptive_capacity_score=scenario_scores["verified_adaptive_capacity_score"],
        modifier_strength=0.15,
    )
    scenario_band = priority_band(scenario_adjusted)

    delta = round(float(scenario_adjusted) - float(baseline_adjusted), 4)
    direction = "lower" if delta < 0 else "higher" if delta > 0 else "unchanged"

    context_evidence_id = baseline_context.get("context_evidence_id")
    if not isinstance(context_evidence_id, str):
        raise LiveScenarioStudioError("Baseline context provenance is incomplete.")
    assumption_id = _scenario_assumption_id(
        context_evidence_id=context_evidence_id,
        label=request.scenario_label,
        changes=request.scenario_changes,
    )

    selected = baseline.get("selected_hotspot") or {}
    baseline_recommendations = baseline.get("recommendations") or []
    baseline_action_ids = [
        str(item.get("action_id"))
        for item in baseline_recommendations
        if isinstance(item, dict) and item.get("action_id")
    ]

    return {
        "schema_version": "heatshield.day15.live_scenario_studio.v1",
        "mode": "live_verified_baseline_plus_explicit_scenario_assumptions",
        "scenario_label": request.scenario_label,
        "selected_hotspot": selected,
        "baseline": {
            "classification": "VERIFIED_BASELINE",
            "evidence_adjusted_priority_score": float(baseline_adjusted),
            "evidence_adjusted_priority_band": baseline_priority.get(
                "evidence_adjusted_priority_band"
            ),
            "pre_adaptation_priority_score": baseline_priority.get(
                "pre_adaptation_priority_score"
            ),
            "operational_adjustment_points": baseline_priority.get(
                "operational_adjustment_points"
            ),
            "hazard_planning_ordinal": float(hazard),
            "context_evidence_id": context_evidence_id,
            "context_source_ref": baseline_context.get("source_ref"),
        },
        "scenario": {
            "classification": "SCENARIO_ESTIMATE",
            "scenario_assumption_id": assumption_id,
            "thermal_hazard_treatment": "held_constant_from_verified_day12_evidence",
            "temperature_change_celsius": None,
            "pre_adaptation_priority_score": scenario_pre,
            "pre_adaptation_priority_band": priority_band(scenario_pre),
            "operational_adjustment_points": scenario_adjustment,
            "evidence_adjusted_priority_score": scenario_adjusted,
            "evidence_adjusted_priority_band": scenario_band,
            "context_scores": scenario_scores,
            "contributions": _contributions(hazard=float(hazard), scores=scenario_scores),
        },
        "comparison": {
            "priority_delta_points": delta,
            "direction": direction,
            "band_changed": baseline_priority.get("evidence_adjusted_priority_band") != scenario_band,
            "interpretation": (
                f"Under the stated scenario assumptions and with verified thermal hazard held constant, "
                f"the planning priority is {direction} by {abs(delta):.2f} points compared with the verified baseline."
            ),
        },
        "assumptions": {
            "classification": "ASSUMED",
            "changes": applied_changes,
            "thermal_hazard_assumption": "The current verified Day 12 thermal-stress hazard is held constant; Day 15 v1 does not model physical cooling or a future weather state.",
            "time_shift_supported": False,
            "temperature_reduction_model_available": False,
        },
        "controlled_action_comparison": {
            "baseline_action_ids": baseline_action_ids,
            "scenario_action_ids": baseline_action_ids,
            "status": "unchanged_hazard_trigger_set",
            "reason": "Day 15 v1 changes operational context assumptions only. The reused Day 8 live worksite action is triggered by verified thermal hazard, which is held constant in this scenario.",
        },
        "provenance": {
            **(baseline.get("provenance") or {}),
            "scenario_assumption_id": assumption_id,
            "scenario_model_version": "heatshield.live_scenario.day15.v1",
            "baseline_priority_model_version": baseline_priority.get("model_version"),
            "new_heatmap_jobs_for_this_request": 0,
            "new_environmental_jobs_for_this_request": 0,
            "new_llm_calls_for_this_request": 0,
        },
        "classification": {
            "OBSERVED": "The baseline thermal/environmental evidence and authorized Day 13 operational context remain the verified source state.",
            "ASSUMED": "Only the explicitly selected scenario factor changes are hypothetical.",
            "DERIVED": "The scenario planning score is recomputed with the existing transparent Day 13 formulas while thermal hazard is held constant.",
            "RECOMMENDED": "No guaranteed outcome is claimed; the scenario is a comparison for evaluation, not a prediction of physical cooling or health outcome.",
        },
        "safety": {
            "scenario_estimate_only": True,
            "measured_future_outcome": False,
            "temperature_reduction_estimated": False,
            "medical_probability_supported": False,
            "individual_health_outcome_inferred": False,
            "provider_calls_for_scenario_step": 0,
            "llm_calls_for_scenario_step": 0,
            "time_shift_requires_fresh_provider_evidence": True,
            "scope_note": "Day 15 v1 supports transparent operational what-if comparisons only. It never relabels scenario assumptions as observations.",
        },
    }
