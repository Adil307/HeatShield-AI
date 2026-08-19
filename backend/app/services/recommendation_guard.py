from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


class RecommendationGuardError(ValueError):
    pass


_PERCENT_RISK = re.compile(r"\b\d+(?:\.\d+)?\s*%\s*(?:health|medical|clinical|illness|mortality)?\s*risk\b", re.I)
_CURRENT_HEAT = re.compile(r"\b(?:current|currently|right now|live)\b.{0,35}\b(?:heat|temperature|heat index|hotspot)\b", re.I)
_PEOPLE_EXPOSED = re.compile(r"\b(?:people|persons|population|students|patients|workers)\s+(?:are\s+)?exposed\b", re.I)
_CERTAINTY = re.compile(r"\b(?:safe|unsafe|guaranteed|will prevent|will eliminate|will get sick|will not get sick)\b", re.I)
_NUMERIC_COOLING = re.compile(r"\b(?:reduce|lower|cool)\w*\b.{0,30}\b\d+(?:\.\d+)?\s*(?:°|degrees?\s*)?[CF]\b", re.I)


def _red_flag(text: str) -> str | None:
    checks = (
        (_PERCENT_RISK, "medical_probability_claim"),
        (_CURRENT_HEAT, "historical_as_current"),
        (_PEOPLE_EXPOSED, "mapped_objects_as_people"),
        (_CERTAINTY, "unsupported_safety_certainty"),
        (_NUMERIC_COOLING, "unsupported_intervention_effect_size"),
    )
    for pattern, code in checks:
        if pattern.search(text):
            return code
    return None


def validate_controlled_recommendation(
    recommendation: Mapping[str, Any],
    *,
    catalog_action: Mapping[str, Any],
    source_registry: Mapping[str, Any],
) -> None:
    for key in ("action_id", "title", "action_type", "priority_tier", "status", "recommendation"):
        if recommendation.get(key) != catalog_action.get(key):
            raise RecommendationGuardError(f"Recommendation field {key!r} diverges from the controlled catalog.")

    combined = " ".join(
        str(recommendation.get(key) or "")
        for key in ("title", "recommendation", "why")
    )
    code = _red_flag(combined)
    if code:
        raise RecommendationGuardError(f"Recommendation blocked by guardrail: {code}.")

    basis = recommendation.get("authoritative_basis")
    if not isinstance(basis, (list, tuple)) or not basis:
        raise RecommendationGuardError("Controlled recommendation must cite at least one registered authoritative basis.")
    for source_id in basis:
        if source_id not in source_registry:
            raise RecommendationGuardError(f"Unknown authoritative source id: {source_id}")

    trigger_evidence = recommendation.get("trigger_evidence")
    if not isinstance(trigger_evidence, (list, tuple)) or not trigger_evidence:
        raise RecommendationGuardError("Controlled recommendation must carry triggering evidence.")
    for item in trigger_evidence:
        if not isinstance(item, Mapping):
            raise RecommendationGuardError("Trigger evidence entries must be objects.")
        if item.get("classification") not in {"observed", "derived", "unknown", "withheld"}:
            raise RecommendationGuardError("Trigger evidence classification is invalid.")

    if recommendation.get("guard_status") != "approved_controlled_catalog_action":
        raise RecommendationGuardError("Recommendation has not passed the controlled-action guard.")
