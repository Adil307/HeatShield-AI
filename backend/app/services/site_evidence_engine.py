from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from app.domain.site_evidence import EvidenceObservation, SiteEvidenceResult
from app.services.day5_artifact import Day5PriorityInput
from app.services.priority_engine import priority_band


class SiteEvidenceError(ValueError):
    pass


PROFILE_TYPE = "operational_worksite_v1"
SCHEMA_VERSION = "heatshield.day6.site_evidence.v1"

# These factors are intentionally operational/worksite oriented because NIOSH
# explicitly identifies exertion, acclimatization, PPE/clothing, hydration,
# recovery/rest, and heat-control programs as relevant to heat-stress prevention.
# HeatShield does not infer these values from OSM or an LLM.
VULNERABILITY_LEVELS: dict[str, dict[str, float]] = {
    "physical_exertion": {"low": 0.0, "moderate": 50.0, "high": 100.0},
    "acclimatization_gap": {"none": 0.0, "partial": 50.0, "substantial": 100.0},
    "heat_trapping_ppe_or_clothing": {"none": 0.0, "some": 50.0, "substantial": 100.0},
}

ADAPTIVE_CAPACITY_LEVELS: dict[str, dict[str, float]] = {
    "potable_water_access": {"absent": 0.0, "partial": 50.0, "adequate": 100.0},
    "shaded_or_cooled_recovery": {"absent": 0.0, "partial": 50.0, "adequate": 100.0},
    "work_rest_controls": {"absent": 0.0, "partial": 50.0, "adequate": 100.0},
    "heat_training_and_monitoring": {"absent": 0.0, "partial": 50.0, "adequate": 100.0},
}

# Versioned prototype modifier strengths. They are used for planning sensitivity
# analysis only, not as validated health-risk coefficients.
MODIFIER_STRENGTHS = {
    "conservative_10pt": 0.10,
    "baseline_15pt": 0.15,
    "stress_20pt": 0.20,
}

ALLOWED_STATUS = {"verified", "unknown"}
ALLOWED_SOURCE_TYPES = {
    "site_assessment",
    "organization_record",
    "sensor_or_system_record",
    "authorized_operator_input",
}


@dataclass(frozen=True, slots=True)
class EvidenceProfile:
    hotspot_rank: int
    tile_id: int | str
    profile_type: str
    vulnerability: dict[str, Mapping[str, Any]]
    adaptive_capacity: dict[str, Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class ModifierSensitivityResult:
    modifier_set: str
    ranking: tuple[int, ...] | None
    scores_by_rank: dict[int, float] | None
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "modifier_set": self.modifier_set,
            "ranking": list(self.ranking) if self.ranking is not None else None,
            "scores_by_rank": {str(k): v for k, v in self.scores_by_rank.items()} if self.scores_by_rank else None,
            "status": self.status,
        }


def _validated_factor(
    factor_id: str,
    raw: Mapping[str, Any],
    level_map: Mapping[str, float],
) -> EvidenceObservation:
    status = raw.get("status")
    if status not in ALLOWED_STATUS:
        raise SiteEvidenceError(f"{factor_id}.status must be one of: {sorted(ALLOWED_STATUS)}")

    level = raw.get("level")
    source_type = raw.get("source_type")
    source_ref = raw.get("source_ref")
    observed_at = raw.get("observed_at")
    notes = raw.get("notes")

    if status == "unknown":
        if level is not None:
            raise SiteEvidenceError(f"{factor_id}: unknown evidence cannot carry a level.")
        return EvidenceObservation(
            factor_id=factor_id,
            status="unknown",
            level=None,
            score=None,
            source_type=None,
            source_ref=None,
            observed_at=None,
            notes=notes if isinstance(notes, str) else None,
        )

    if level not in level_map:
        raise SiteEvidenceError(f"{factor_id}.level must be one of: {sorted(level_map)}")
    if source_type not in ALLOWED_SOURCE_TYPES:
        raise SiteEvidenceError(f"{factor_id}.source_type must be one of: {sorted(ALLOWED_SOURCE_TYPES)}")
    if not isinstance(source_ref, str) or not source_ref.strip():
        raise SiteEvidenceError(f"{factor_id}.source_ref is required for verified evidence.")
    if not isinstance(observed_at, str) or not observed_at.strip():
        raise SiteEvidenceError(f"{factor_id}.observed_at is required for verified evidence.")

    return EvidenceObservation(
        factor_id=factor_id,
        status="verified",
        level=str(level),
        score=float(level_map[str(level)]),
        source_type=str(source_type),
        source_ref=source_ref.strip(),
        observed_at=observed_at.strip(),
        notes=notes if isinstance(notes, str) else None,
    )


def _parse_factor_group(
    raw_group: Mapping[str, Mapping[str, Any]],
    definitions: Mapping[str, Mapping[str, float]],
    group_name: str,
) -> tuple[EvidenceObservation, ...]:
    missing = [factor for factor in definitions if factor not in raw_group]
    extras = [factor for factor in raw_group if factor not in definitions]
    if missing:
        raise SiteEvidenceError(f"{group_name} is missing required factors: {', '.join(missing)}")
    if extras:
        raise SiteEvidenceError(f"{group_name} has unsupported factors: {', '.join(extras)}")
    return tuple(
        _validated_factor(factor_id, raw_group[factor_id], definitions[factor_id])
        for factor_id in definitions
    )


def _group_score(items: Iterable[EvidenceObservation]) -> tuple[float | None, float]:
    observations = tuple(items)
    if not observations:
        return None, 0.0
    verified = [item for item in observations if item.status == "verified"]
    completeness = round(len(verified) / len(observations), 4)
    if len(verified) != len(observations):
        return None, completeness
    values = [item.score for item in verified]
    assert all(value is not None for value in values)
    return round(sum(float(value) for value in values) / len(values), 4), completeness


def evidence_bundle_id(
    *,
    day5_sha256: str,
    priority: Day5PriorityInput,
    vulnerability: Iterable[EvidenceObservation],
    adaptive_capacity: Iterable[EvidenceObservation],
) -> str:
    canonical = {
        "day5_sha256": day5_sha256,
        "priority_evidence_id": priority.priority_evidence_id,
        "tile_id": priority.tile_id,
        "hotspot_rank": priority.hotspot_rank,
        "vulnerability": [item.to_dict() for item in vulnerability],
        "adaptive_capacity": [item.to_dict() for item in adaptive_capacity],
    }
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "hs_site_evidence_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def evidence_adjusted_score(
    *,
    pre_adaptation_priority_score: float,
    vulnerability_score: float,
    adaptive_capacity_score: float,
    modifier_strength: float = 0.15,
) -> tuple[float, float]:
    for field_name, value in (
        ("pre_adaptation_priority_score", pre_adaptation_priority_score),
        ("vulnerability_score", vulnerability_score),
        ("adaptive_capacity_score", adaptive_capacity_score),
    ):
        if not math.isfinite(value) or not 0.0 <= value <= 100.0:
            raise SiteEvidenceError(f"{field_name} must be finite and in [0, 100].")
    if not math.isfinite(modifier_strength) or not 0.0 <= modifier_strength <= 0.5:
        raise SiteEvidenceError("modifier_strength must be in [0, 0.5].")

    # Symmetric bounded planning modifier. This is intentionally simple and
    # versioned: verified vulnerability can raise priority while verified
    # adaptive capacity can lower it. It is not a clinical risk formula.
    adjustment = modifier_strength * vulnerability_score - modifier_strength * adaptive_capacity_score
    adjusted = max(0.0, min(100.0, pre_adaptation_priority_score + adjustment))
    return round(adjusted, 4), round(adjustment, 4)


def score_site_evidence(
    priority: Day5PriorityInput,
    profile: EvidenceProfile,
    *,
    day5_sha256: str,
    modifier_set: str = "baseline_15pt",
) -> SiteEvidenceResult:
    if profile.profile_type != PROFILE_TYPE:
        raise SiteEvidenceError(f"Unsupported profile_type: {profile.profile_type}")
    if profile.hotspot_rank != priority.hotspot_rank or str(profile.tile_id) != str(priority.tile_id):
        raise SiteEvidenceError("Evidence profile hotspot identity does not match the Day 5 priority result.")
    try:
        strength = MODIFIER_STRENGTHS[modifier_set]
    except KeyError as exc:
        raise SiteEvidenceError(f"Unknown modifier set: {modifier_set}") from exc

    vulnerability = _parse_factor_group(profile.vulnerability, VULNERABILITY_LEVELS, "vulnerability")
    adaptive = _parse_factor_group(profile.adaptive_capacity, ADAPTIVE_CAPACITY_LEVELS, "adaptive_capacity")
    vulnerability_score, v_complete = _group_score(vulnerability)
    adaptive_score, a_complete = _group_score(adaptive)
    complete = vulnerability_score is not None and adaptive_score is not None

    if complete:
        assert vulnerability_score is not None and adaptive_score is not None
        adjusted_score, adjustment = evidence_adjusted_score(
            pre_adaptation_priority_score=priority.pre_adaptation_priority_score,
            vulnerability_score=vulnerability_score,
            adaptive_capacity_score=adaptive_score,
            modifier_strength=strength,
        )
        adjusted_band = priority_band(adjusted_score)
        adjusted_status = "derived_from_complete_verified_operational_evidence"
    else:
        adjusted_score = None
        adjustment = None
        adjusted_band = None
        adjusted_status = "withheld_until_all_required_operational_factors_are_verified"

    bundle_id = evidence_bundle_id(
        day5_sha256=day5_sha256,
        priority=priority,
        vulnerability=vulnerability,
        adaptive_capacity=adaptive,
    )

    explanations = (
        "Day 6 never infers operational vulnerability or adaptive capacity from OSM, temperature, or an LLM; each factor must be explicitly verified by an authorized source.",
        f"Operational vulnerability completeness is {v_complete * 100:.0f}% across exertion, acclimatization-gap, and heat-trapping PPE/clothing factors.",
        f"Adaptive-capacity completeness is {a_complete * 100:.0f}% across potable water, shaded/cooled recovery, work-rest controls, and heat training/monitoring factors.",
        "The optional evidence-adjusted planning priority uses a transparent symmetric modifier and is produced only when all required factors are verified.",
        "No medical/clinical or individual probability-of-illness score is produced, even when operational evidence is complete.",
    )

    return SiteEvidenceResult(
        hotspot_rank=priority.hotspot_rank,
        tile_id=priority.tile_id,
        priority_evidence_id=priority.priority_evidence_id,
        evidence_bundle_id=bundle_id,
        vulnerability_score=vulnerability_score,
        adaptive_capacity_score=adaptive_score,
        vulnerability_completeness=v_complete,
        adaptive_capacity_completeness=a_complete,
        evidence_complete=complete,
        evidence_adjusted_priority_score=adjusted_score,
        evidence_adjusted_priority_band=adjusted_band,
        adjustment_points=adjustment,
        medical_risk_score=None,
        vulnerability_factors=vulnerability,
        adaptive_capacity_factors=adaptive,
        evidence_status={
            "operational_vulnerability": "verified_complete" if vulnerability_score is not None else "incomplete_or_unknown",
            "adaptive_capacity": "verified_complete" if adaptive_score is not None else "incomplete_or_unknown",
            "evidence_adjusted_planning_priority": adjusted_status,
            "medical_risk_score": "never_produced_by_day6",
        },
        explanations=explanations,
    )


def load_evidence_profiles(path: str | Path) -> dict[int, EvidenceProfile]:
    artifact_path = Path(path)
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SiteEvidenceError(f"Cannot read site evidence file: {artifact_path}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise SiteEvidenceError("Unsupported Day 6 site-evidence schema.")
    if payload.get("profile_type") != PROFILE_TYPE:
        raise SiteEvidenceError(f"profile_type must be {PROFILE_TYPE}.")
    hotspots = payload.get("hotspots")
    if not isinstance(hotspots, list):
        raise SiteEvidenceError("hotspots must be a list.")

    result: dict[int, EvidenceProfile] = {}
    for index, item in enumerate(hotspots):
        if not isinstance(item, dict):
            raise SiteEvidenceError(f"hotspots[{index}] must be an object.")
        rank = item.get("hotspot_rank")
        tile_id = item.get("tile_id")
        vulnerability = item.get("vulnerability")
        adaptive = item.get("adaptive_capacity")
        if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
            raise SiteEvidenceError(f"hotspots[{index}].hotspot_rank is invalid.")
        if tile_id is None or isinstance(tile_id, bool):
            raise SiteEvidenceError(f"hotspots[{index}].tile_id is invalid.")
        if rank in result:
            raise SiteEvidenceError(f"Duplicate hotspot_rank in site evidence: {rank}")
        if not isinstance(vulnerability, dict) or not isinstance(adaptive, dict):
            raise SiteEvidenceError(f"hotspots[{index}] is missing vulnerability/adaptive_capacity objects.")
        result[rank] = EvidenceProfile(
            hotspot_rank=rank,
            tile_id=tile_id,
            profile_type=PROFILE_TYPE,
            vulnerability=vulnerability,
            adaptive_capacity=adaptive,
        )
    return result


def unknown_factor(levels: Mapping[str, float]) -> dict[str, Any]:
    del levels
    return {
        "status": "unknown",
        "level": None,
        "source_type": None,
        "source_ref": None,
        "observed_at": None,
        "notes": None,
    }


def build_unknown_profile(priority_results: Iterable[Day5PriorityInput]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "profile_type": PROFILE_TYPE,
        "scope": "human_in_the_loop_operational_evidence_not_medical_risk",
        "instructions": (
            "Replace unknown values only with directly verified operational evidence. "
            "Do not infer factors from OSM place types, temperature, or an LLM."
        ),
        "hotspots": [
            {
                "hotspot_rank": item.hotspot_rank,
                "tile_id": item.tile_id,
                "vulnerability": {
                    factor: unknown_factor(levels) for factor, levels in VULNERABILITY_LEVELS.items()
                },
                "adaptive_capacity": {
                    factor: unknown_factor(levels) for factor, levels in ADAPTIVE_CAPACITY_LEVELS.items()
                },
            }
            for item in priority_results
        ],
    }


def modifier_sensitivity(
    priorities: Iterable[Day5PriorityInput],
    profiles: Mapping[int, EvidenceProfile],
    *,
    day5_sha256: str,
) -> tuple[ModifierSensitivityResult, ...]:
    priority_items = tuple(priorities)
    results: list[ModifierSensitivityResult] = []
    for modifier_set in MODIFIER_STRENGTHS:
        scores: dict[int, float] = {}
        complete = True
        for priority in priority_items:
            profile = profiles.get(priority.hotspot_rank)
            if profile is None:
                complete = False
                break
            scored = score_site_evidence(
                priority,
                profile,
                day5_sha256=day5_sha256,
                modifier_set=modifier_set,
            )
            if scored.evidence_adjusted_priority_score is None:
                complete = False
                break
            scores[priority.hotspot_rank] = scored.evidence_adjusted_priority_score
        if not complete:
            results.append(
                ModifierSensitivityResult(
                    modifier_set=modifier_set,
                    ranking=None,
                    scores_by_rank=None,
                    status="withheld_incomplete_evidence",
                )
            )
            continue
        ranking = tuple(sorted(scores, key=lambda rank: (-scores[rank], rank)))
        results.append(
            ModifierSensitivityResult(
                modifier_set=modifier_set,
                ranking=ranking,
                scores_by_rank=scores,
                status="computed_complete_verified_evidence",
            )
        )
    return tuple(results)
