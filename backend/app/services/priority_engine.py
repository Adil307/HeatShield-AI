from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Iterable, Mapping

from app.domain.priority import PriorityComponents, PriorityResult
from app.services.day44_artifact import Day44HotspotInput


# Public NWS heat-index bands. The score attached to each band is a HeatShield
# planning ordinal, not an NWS probability or medical-risk percentage.
NWS_HEAT_INDEX_REFERENCE_URL = "https://www.weather.gov/ama/heatindex"
NIOSH_HEAT_STRESS_REFERENCE_URL = "https://www.cdc.gov/niosh/heat-stress/about/"

CATEGORY_ORDER = (
    "healthcare",
    "education",
    "transit_waiting",
    "outdoor_public",
    "civic_public",
)

# Fahrenheit thresholds from the NWS public heat-index classification converted
# to Celsius. Boundary behavior is deterministic and tested.
F_TO_C = lambda f: (f - 32.0) * 5.0 / 9.0
CAUTION_C = F_TO_C(80.0)
EXTREME_CAUTION_C = F_TO_C(90.0)
DANGER_C = F_TO_C(103.0)
EXTREME_DANGER_C = F_TO_C(125.0)

# Versioned prototype planning weights. These are deliberately exposed and
# sensitivity-tested; they are not a validated health model.
WEIGHT_SETS: dict[str, tuple[float, float, float]] = {
    "baseline_v1": (0.60, 0.30, 0.10),
    "hazard_heavy": (0.70, 0.20, 0.10),
    "context_heavy": (0.50, 0.35, 0.15),
}


class PriorityEngineError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class WeightSensitivityResult:
    weight_set: str
    ranking: tuple[int, ...]
    scores_by_rank: dict[int, float]

    def to_dict(self) -> dict:
        return {
            "weight_set": self.weight_set,
            "ranking": list(self.ranking),
            "scores_by_rank": {str(k): v for k, v in self.scores_by_rank.items()},
        }


def heat_index_band(heat_index_celsius: float) -> str:
    if not math.isfinite(heat_index_celsius):
        raise PriorityEngineError("Heat index must be finite.")
    if heat_index_celsius < CAUTION_C:
        return "below_nws_caution"
    if heat_index_celsius < EXTREME_CAUTION_C:
        return "nws_caution"
    if heat_index_celsius < DANGER_C:
        return "nws_extreme_caution"
    if heat_index_celsius < EXTREME_DANGER_C:
        return "nws_danger"
    return "nws_extreme_danger"


def hazard_ordinal_score(heat_index_celsius: float) -> float:
    """Map NWS heat-index category to a transparent HeatShield planning ordinal.

    The returned value is for prioritization/ranking only. It is not a probability
    of illness, a clinical risk score, or an NWS-issued numeric risk value.
    """
    return {
        "below_nws_caution": 20.0,
        "nws_caution": 40.0,
        "nws_extreme_caution": 60.0,
        "nws_danger": 80.0,
        "nws_extreme_danger": 100.0,
    }[heat_index_band(heat_index_celsius)]


def _count_signal(count: int, *, saturation_count: int = 20) -> float:
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise PriorityEngineError("Mapped context counts must be non-negative integers.")
    if saturation_count < 1:
        raise PriorityEngineError("saturation_count must be positive.")
    if count == 0:
        return 0.0
    # Log saturation limits the influence of OSM mapping granularity: hundreds of
    # mapped garden polygons cannot dominate the score merely because they are split.
    return min(1.0, math.log1p(count) / math.log1p(saturation_count))


def mapped_exposure_score(category_counts: Mapping[str, int]) -> float:
    missing = [category for category in CATEGORY_ORDER if category not in category_counts]
    if missing:
        raise PriorityEngineError(f"Mapped exposure categories missing: {', '.join(missing)}")
    signals = [_count_signal(category_counts[category]) for category in CATEGORY_ORDER]
    return round(100.0 * sum(signals) / len(signals), 4)


def context_sensitivity_proxy(category_counts: Mapping[str, int]) -> float:
    """Conservative place-type proxy; never a claim about individual vulnerability."""
    healthcare_present = category_counts.get("healthcare", 0) > 0
    education_present = category_counts.get("education", 0) > 0
    return float(50 * int(healthcare_present) + 50 * int(education_present))


def weighted_pre_adaptation_score(
    *,
    hazard_score: float,
    exposure_score: float,
    sensitivity_proxy: float,
    weight_set: str = "baseline_v1",
) -> float:
    try:
        h_w, e_w, s_w = WEIGHT_SETS[weight_set]
    except KeyError as exc:
        raise PriorityEngineError(f"Unknown weight set: {weight_set}") from exc
    if not math.isclose(h_w + e_w + s_w, 1.0, abs_tol=1e-12):
        raise PriorityEngineError("Priority weights must sum to 1.0.")
    for value in (hazard_score, exposure_score, sensitivity_proxy):
        if not math.isfinite(value) or not 0.0 <= value <= 100.0:
            raise PriorityEngineError("Priority components must be finite values in [0, 100].")
    return round(h_w * hazard_score + e_w * exposure_score + s_w * sensitivity_proxy, 4)


def priority_band(score: float) -> str:
    if not math.isfinite(score) or not 0 <= score <= 100:
        raise PriorityEngineError("Priority score must be in [0, 100].")
    if score < 40:
        return "lower_planning_priority"
    if score < 60:
        return "moderate_planning_priority"
    if score < 80:
        return "high_planning_priority"
    return "very_high_planning_priority"


def priority_evidence_id(*, day44_sha256: str, hotspot: Day44HotspotInput, weight_set: str) -> str:
    raw = (
        f"priority|{day44_sha256}|{hotspot.context_evidence_id}|{hotspot.environmental_evidence_id}|"
        f"{hotspot.thermal_evidence_id}|{hotspot.tile_id}|{hotspot.hotspot_rank}|{weight_set}"
    )
    return "hs_priority_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def score_hotspot(
    hotspot: Day44HotspotInput,
    *,
    day44_sha256: str,
    weight_set: str = "baseline_v1",
) -> PriorityResult:
    if hotspot.heat_index_celsius is None:
        raise PriorityEngineError(
            "Day 5 v1 requires an observed heat index; it will not substitute apparent temperature into NWS heat-index bands."
        )
    if any(hotspot.category_status.get(category) != "observed" for category in CATEGORY_ORDER):
        raise PriorityEngineError("All mapped context categories must be observed before scoring.")

    h_band = heat_index_band(hotspot.heat_index_celsius)
    hazard = hazard_ordinal_score(hotspot.heat_index_celsius)
    exposure = mapped_exposure_score(hotspot.category_counts)
    sensitivity = context_sensitivity_proxy(hotspot.category_counts)
    pre_score = weighted_pre_adaptation_score(
        hazard_score=hazard,
        exposure_score=exposure,
        sensitivity_proxy=sensitivity,
        weight_set=weight_set,
    )

    components = PriorityComponents(
        hazard_score=hazard,
        mapped_exposure_score=exposure,
        context_sensitivity_proxy=sensitivity,
        verified_vulnerability_score=None,
        verified_adaptive_capacity_score=None,
    )

    explanations = (
        f"Hazard uses observed heat index {hotspot.heat_index_celsius:.2f} C and NWS band {h_band}; HeatShield converts the band to a planning ordinal, not a health probability.",
        f"Mapped exposure proxy is {exposure:.2f}/100 from five equally represented OSM context categories with logarithmic count saturation to limit map-segmentation bias.",
        f"Context sensitivity proxy is {sensitivity:.0f}/100 from presence of healthcare and education place types; it is not a claim about individual vulnerability.",
        "Verified individual vulnerability is unavailable, so Day 5 does not invent a vulnerability score.",
        "Verified adaptive-capacity evidence (shade, cooling, hydration, operational controls, etc.) is unavailable, so no downward adaptation adjustment is applied and no final risk score is produced.",
    )

    return PriorityResult(
        hotspot_rank=hotspot.hotspot_rank,
        tile_id=hotspot.tile_id,
        priority_evidence_id=priority_evidence_id(
            day44_sha256=day44_sha256,
            hotspot=hotspot,
            weight_set=weight_set,
        ),
        heat_index_band=h_band,
        pre_adaptation_priority_score=pre_score,
        pre_adaptation_priority_band=priority_band(pre_score),
        final_priority_score=None,
        final_priority_band=None,
        components=components,
        evidence_status={
            "thermal_hazard": "observed",
            "mapped_exposure_context": "observed_complete",
            "context_sensitivity": "derived_place_type_proxy",
            "individual_vulnerability": "unknown_not_observed",
            "adaptive_capacity": "unknown_not_observed",
            "final_risk_score": "withheld_missing_vulnerability_and_adaptive_capacity",
        },
        factor_explanations=explanations,
    )


def sensitivity_analysis(
    hotspots: Iterable[Day44HotspotInput],
) -> tuple[WeightSensitivityResult, ...]:
    selected = tuple(hotspots)
    if not selected:
        raise PriorityEngineError("No hotspots supplied for sensitivity analysis.")

    results: list[WeightSensitivityResult] = []
    for weight_set in WEIGHT_SETS:
        scores: dict[int, float] = {}
        for hotspot in selected:
            if hotspot.heat_index_celsius is None:
                raise PriorityEngineError("Heat index is required for sensitivity analysis.")
            score = weighted_pre_adaptation_score(
                hazard_score=hazard_ordinal_score(hotspot.heat_index_celsius),
                exposure_score=mapped_exposure_score(hotspot.category_counts),
                sensitivity_proxy=context_sensitivity_proxy(hotspot.category_counts),
                weight_set=weight_set,
            )
            scores[hotspot.hotspot_rank] = score
        ranking = tuple(sorted(scores, key=lambda rank: (-scores[rank], rank)))
        results.append(
            WeightSensitivityResult(
                weight_set=weight_set,
                ranking=ranking,
                scores_by_rank=scores,
            )
        )
    return tuple(results)


def ranking_stability(results: Iterable[WeightSensitivityResult]) -> dict:
    items = tuple(results)
    if not items:
        raise PriorityEngineError("Sensitivity results are required.")
    baseline = items[0].ranking
    stable = all(item.ranking == baseline for item in items[1:])
    return {
        "stable_across_weight_sets": stable,
        "baseline_ranking": list(baseline),
        "rankings": {item.weight_set: list(item.ranking) for item in items},
    }
