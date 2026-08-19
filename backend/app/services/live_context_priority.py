from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.fortyguard import HeatmapRequest
from app.services.live_decision_readiness import LiveDecisionReadinessError, run_live_decision_readiness
from app.services.priority_engine import priority_band, weighted_pre_adaptation_score
from app.services.site_evidence_engine import (
    ADAPTIVE_CAPACITY_LEVELS,
    VULNERABILITY_LEVELS,
    evidence_adjusted_score,
)


class LiveContextPriorityError(ValueError):
    """Raised when Day 13 cannot calculate a fully grounded live priority."""


EXPOSURE_LEVELS: dict[str, float] = {
    "none": 0.0,
    "low": 25.0,
    "moderate": 50.0,
    "high": 100.0,
}

SENSITIVE_USE_LEVELS: dict[str, float] = {
    "none": 0.0,
    "education": 50.0,
    "healthcare": 50.0,
    "education_and_healthcare": 100.0,
}

LIVE_PRIORITY_WEIGHT_SET = "baseline_v1"
LIVE_SITE_MODIFIER_SET = "baseline_15pt"
LIVE_SITE_MODIFIER_STRENGTH = 0.15


class Day13ContextProfile(BaseModel):
    """Explicit, authorized operational context for one live hottest tile.

    No field is inferred from the map, temperature, or an LLM. The operator must
    choose every categorical value and attach one auditable source reference.
    """

    profile_type: Literal["operational_worksite_v1"] = "operational_worksite_v1"
    source_type: Literal[
        "site_assessment",
        "organization_record",
        "sensor_or_system_record",
        "authorized_operator_input",
    ] = "authorized_operator_input"
    source_ref: str = Field(min_length=3, max_length=240)
    observed_at: str = Field(min_length=10, max_length=64)

    exposure_level: Literal["none", "low", "moderate", "high"]
    sensitive_use_context: Literal[
        "none",
        "education",
        "healthcare",
        "education_and_healthcare",
    ]

    physical_exertion: Literal["low", "moderate", "high"]
    acclimatization_gap: Literal["none", "partial", "substantial"]
    heat_trapping_ppe_or_clothing: Literal["none", "some", "substantial"]

    potable_water_access: Literal["absent", "partial", "adequate"]
    shaded_or_cooled_recovery: Literal["absent", "partial", "adequate"]
    work_rest_controls: Literal["absent", "partial", "adequate"]
    heat_training_and_monitoring: Literal["absent", "partial", "adequate"]

    @field_validator("source_ref")
    @classmethod
    def clean_source_ref(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 3:
            raise ValueError("source_ref must identify the authorized evidence source.")
        return cleaned

    @field_validator("observed_at")
    @classmethod
    def require_aware_timestamp(cls, value: str) -> str:
        raw = value.strip()
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("observed_at must be a valid ISO-8601 timestamp.") from exc
        if parsed.tzinfo is None:
            raise ValueError("observed_at must include a timezone offset.")
        return raw


class Day13ContextPriorityRequest(BaseModel):
    analysis_request: HeatmapRequest
    context_profile: Day13ContextProfile

    @model_validator(mode="after")
    def keep_live_scope_single_hour_tcm(self):
        request = self.analysis_request
        if request.analytic_type != "tcm" or request.date_time.filter_type != 1:
            raise ValueError("Day 13 context priority requires the Day 11/12 single-hour TCM live analysis.")
        return self


def _average(values: list[float]) -> float:
    if not values or any(not math.isfinite(value) for value in values):
        raise LiveContextPriorityError("Context score inputs must be finite.")
    return round(sum(values) / len(values), 4)


def _context_scores(profile: Day13ContextProfile) -> dict[str, float]:
    exposure = EXPOSURE_LEVELS[profile.exposure_level]
    sensitivity = SENSITIVE_USE_LEVELS[profile.sensitive_use_context]
    vulnerability = _average(
        [
            VULNERABILITY_LEVELS["physical_exertion"][profile.physical_exertion],
            VULNERABILITY_LEVELS["acclimatization_gap"][profile.acclimatization_gap],
            VULNERABILITY_LEVELS["heat_trapping_ppe_or_clothing"][profile.heat_trapping_ppe_or_clothing],
        ]
    )
    adaptive = _average(
        [
            ADAPTIVE_CAPACITY_LEVELS["potable_water_access"][profile.potable_water_access],
            ADAPTIVE_CAPACITY_LEVELS["shaded_or_cooled_recovery"][profile.shaded_or_cooled_recovery],
            ADAPTIVE_CAPACITY_LEVELS["work_rest_controls"][profile.work_rest_controls],
            ADAPTIVE_CAPACITY_LEVELS["heat_training_and_monitoring"][profile.heat_training_and_monitoring],
        ]
    )
    return {
        "verified_exposure_score": exposure,
        "verified_sensitive_use_proxy": sensitivity,
        "verified_operational_vulnerability_score": vulnerability,
        "verified_adaptive_capacity_score": adaptive,
    }


def _context_evidence_id(*, request_hash: str, environmental_evidence_id: str, profile: Day13ContextProfile) -> str:
    canonical = json.dumps(
        {
            "request_hash": request_hash,
            "environmental_evidence_id": environmental_evidence_id,
            "context_profile": profile.model_dump(mode="json"),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return "hs_live_context_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]


def _load_worker_action(catalog_path: str | Path, *, hazard_score: float) -> list[dict[str, Any]]:
    """Return only controlled Day 8 catalog actions whose documented trigger is met.

    For Day 13 v1 the only action reusable without inventing mapped public-use
    context is the worksite review action, and its catalog trigger is hazard >= 60.
    """
    if hazard_score < 60.0:
        return []
    try:
        catalog = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LiveContextPriorityError(f"Controlled action catalog could not be loaded: {exc}") from exc
    actions = catalog.get("actions") if isinstance(catalog, dict) else None
    if not isinstance(actions, list):
        raise LiveContextPriorityError("Controlled action catalog has no actions list.")
    wanted = next(
        (
            item
            for item in actions
            if isinstance(item, dict) and item.get("action_id") == "review_worker_heat_practices_if_applicable"
        ),
        None,
    )
    if wanted is None:
        raise LiveContextPriorityError("Required controlled worksite action is missing from the Day 8 catalog.")
    return [
        {
            "action_id": wanted.get("action_id"),
            "title": wanted.get("title"),
            "action_type": wanted.get("action_type"),
            "priority_tier": wanted.get("priority_tier"),
            "status": wanted.get("status"),
            "recommendation": wanted.get("recommendation"),
            "required_verification": wanted.get("required_verification", []),
            "limitations": wanted.get("limitations", []),
            "authoritative_basis": wanted.get("authoritative_basis", []),
            "guard_status": "approved_day8_catalog_action",
        }
    ]


async def run_live_context_priority(
    request: Day13ContextPriorityRequest,
    *,
    live_cache_dir: str | Path,
    env_cache_dir: str | Path,
    catalog_path: str | Path,
) -> dict[str, Any]:
    """Calculate live evidence-adjusted planning priority from verified context.

    This step performs zero provider calls. It only reuses the verified Day 11
    thermal completion plus the verified Day 12 environmental completion, then
    applies explicit operator-supplied context with existing transparent HeatShield
    priority and site-evidence formulas.
    """
    try:
        readiness = await run_live_decision_readiness(
            request.analysis_request,
            client=None,
            live_cache_dir=live_cache_dir,
            env_cache_dir=env_cache_dir,
        )
    except LiveDecisionReadinessError as exc:
        raise LiveContextPriorityError(
            "Enrich the hottest tile first. Day 13 never creates a provider job; it only reuses verified Day 12 evidence."
        ) from exc

    derived = readiness.get("environmental_derived") or {}
    hazard = derived.get("hazard_planning_ordinal")
    if isinstance(hazard, bool) or not isinstance(hazard, (int, float)):
        raise LiveContextPriorityError(
            "Observed heat index is unavailable, so the transparent hazard ordinal and full live planning priority remain withheld."
        )
    hazard = float(hazard)

    profile = request.context_profile
    scores = _context_scores(profile)
    pre_adaptation = weighted_pre_adaptation_score(
        hazard_score=hazard,
        exposure_score=scores["verified_exposure_score"],
        sensitivity_proxy=scores["verified_sensitive_use_proxy"],
        weight_set=LIVE_PRIORITY_WEIGHT_SET,
    )
    adjusted, adjustment = evidence_adjusted_score(
        pre_adaptation_priority_score=pre_adaptation,
        vulnerability_score=scores["verified_operational_vulnerability_score"],
        adaptive_capacity_score=scores["verified_adaptive_capacity_score"],
        modifier_strength=LIVE_SITE_MODIFIER_STRENGTH,
    )
    band = priority_band(adjusted)

    provenance = readiness.get("provenance") or {}
    env_evidence_id = provenance.get("environmental_evidence_id")
    request_hash = provenance.get("thermal_request_hash")
    if not isinstance(env_evidence_id, str) or not isinstance(request_hash, str):
        raise LiveContextPriorityError("Day 12 provenance is incomplete; context cannot be attached safely.")
    context_evidence_id = _context_evidence_id(
        request_hash=request_hash,
        environmental_evidence_id=env_evidence_id,
        profile=profile,
    )

    recommendations = _load_worker_action(catalog_path, hazard_score=hazard)
    contributions = {
        "hazard_points": round(0.60 * hazard, 4),
        "exposure_points": round(0.30 * scores["verified_exposure_score"], 4),
        "sensitive_use_points": round(0.10 * scores["verified_sensitive_use_proxy"], 4),
        "vulnerability_adjustment_points": round(0.15 * scores["verified_operational_vulnerability_score"], 4),
        "adaptive_capacity_reduction_points": round(-0.15 * scores["verified_adaptive_capacity_score"], 4),
    }

    return {
        "schema_version": "heatshield.day13.live_context_priority.v1",
        "mode": "fresh_provider_plus_verified_operator_context",
        "selected_hotspot": readiness.get("selected_hotspot"),
        "verified_context": {
            "source_type": profile.source_type,
            "source_ref": profile.source_ref,
            "observed_at": profile.observed_at,
            "profile_type": profile.profile_type,
            "exposure_level": profile.exposure_level,
            "sensitive_use_context": profile.sensitive_use_context,
            "physical_exertion": profile.physical_exertion,
            "acclimatization_gap": profile.acclimatization_gap,
            "heat_trapping_ppe_or_clothing": profile.heat_trapping_ppe_or_clothing,
            "potable_water_access": profile.potable_water_access,
            "shaded_or_cooled_recovery": profile.shaded_or_cooled_recovery,
            "work_rest_controls": profile.work_rest_controls,
            "heat_training_and_monitoring": profile.heat_training_and_monitoring,
            **scores,
            "context_evidence_id": context_evidence_id,
        },
        "priority": {
            "model_version": "heatshield.live_priority.day13.v1",
            "weight_set": LIVE_PRIORITY_WEIGHT_SET,
            "site_modifier_set": LIVE_SITE_MODIFIER_SET,
            "hazard_planning_ordinal": hazard,
            "pre_adaptation_priority_score": pre_adaptation,
            "pre_adaptation_priority_band": priority_band(pre_adaptation),
            "operational_adjustment_points": adjustment,
            "evidence_adjusted_priority_score": adjusted,
            "evidence_adjusted_priority_band": band,
            "contributions": contributions,
            "interpretation": "Transparent operational planning priority only; not a probability of illness or an individual medical-risk score.",
        },
        "recommendations": recommendations,
        "recommendation_policy": {
            "source": "Day 8 controlled action catalog",
            "llm_generated_actions": False,
            "trigger_rule": "Only documented catalog triggers using verified live evidence are evaluated.",
            "no_trigger_message": "No controlled Day 8 worksite action is triggered when the live hazard ordinal is below 60.",
        },
        "decision_readiness": {
            "thermal_evidence": "observed_verified",
            "thermal_stress_enrichment": "observed_verified",
            "exposure_context": "verified_authorized_source",
            "operational_vulnerability": "verified_authorized_source",
            "adaptive_capacity": "verified_authorized_source",
            "planning_priority": "derived_supported",
            "medical_risk_probability": "not_supported",
        },
        "provenance": {
            **provenance,
            "context_evidence_id": context_evidence_id,
            "context_source_type": profile.source_type,
            "context_source_ref": profile.source_ref,
            "context_observed_at": profile.observed_at,
            "new_heatmap_jobs_for_this_request": 0,
            "new_environmental_jobs_for_this_request": 0,
            "new_llm_calls_for_this_request": 0,
        },
        "classification": {
            "OBSERVED": "FortyGuard thermal/environmental evidence plus explicitly verified authorized operational context.",
            "DERIVED": "Hazard ordinal, context scores, pre-adaptation priority, operational modifier, evidence-adjusted priority and band.",
            "INFERRED": "No occupancy count, individual vulnerability, medical diagnosis, or medical-risk probability is inferred.",
            "RECOMMENDED": "Only controlled Day 8 catalog actions whose documented trigger is satisfied by verified evidence.",
        },
        "safety": {
            "planning_priority_supported": True,
            "medical_probability_supported": False,
            "individual_medical_vulnerability_inferred": False,
            "provider_calls_for_context_step": 0,
            "llm_generated_recommendations": False,
            "scope_note": "Day 13 unlocks a live operational planning priority only after explicit source-backed context verification.",
        },
    }
