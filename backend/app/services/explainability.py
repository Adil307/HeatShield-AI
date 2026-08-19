from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from app.domain.explainability import Contribution, EvidenceLedgerEntry, ExplainabilityPacket
from app.services.day44_artifact import Day44ArtifactError, load_day44_priority_source
from app.services.day6_artifact import Day6ArtifactError, Day6EvidenceSource, file_sha256, load_day6_evidence_source


class ExplainabilityError(ValueError):
    pass


EXPECTED_DAY5_SCHEMA = "heatshield.day5.planning_priority.v1"
EXPECTED_DAY44_SCHEMA = "heatshield.day4_4.scenario_replay.v1"
SCENARIO_SCOPE = "historical_hazard_current_context_scenario_replay"


def _read_json(path: str | Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExplainabilityError(f"Cannot read {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise ExplainabilityError(f"{label} must contain a JSON object.")
    return payload


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExplainabilityError(f"{field} must be numeric.")
    number = float(value)
    if not math.isfinite(number):
        raise ExplainabilityError(f"{field} must be finite.")
    return number


def _load_verified_chain(day6_path: str | Path, day5_path: str | Path, day44_path: str | Path) -> tuple[Day6EvidenceSource, dict[str, Any], dict[str, Any]]:
    day6 = load_day6_evidence_source(day6_path)
    day5_file = Path(day5_path)
    day44_file = Path(day44_path)

    if file_sha256(day5_file) != day6.day5_artifact_sha256:
        raise ExplainabilityError("Day 6 -> Day 5 SHA-256 provenance mismatch.")

    day5 = _read_json(day5_file, "Day 5 artifact")
    if day5.get("schema_version") != EXPECTED_DAY5_SCHEMA:
        raise ExplainabilityError("Unsupported Day 5 artifact schema.")
    source5 = day5.get("source")
    if not isinstance(source5, dict):
        raise ExplainabilityError("Day 5 source metadata is missing.")
    day44_sha = source5.get("day44_artifact_sha256")
    if day44_sha != day6.day44_artifact_sha256:
        raise ExplainabilityError("Day 6 and Day 5 disagree on the Day 4.4 provenance hash.")
    if file_sha256(day44_file) != day44_sha:
        raise ExplainabilityError("Day 5 -> Day 4.4 SHA-256 provenance mismatch.")

    day44 = _read_json(day44_file, "Day 4.4 artifact")
    if day44.get("schema_version") != EXPECTED_DAY44_SCHEMA:
        raise ExplainabilityError("Unsupported Day 4.4 artifact schema.")
    if day44.get("mode") != SCENARIO_SCOPE:
        raise ExplainabilityError("Explainability requires the explicit Day 4.4 scenario-replay mode.")
    try:
        load_day44_priority_source(day44_file)
    except Day44ArtifactError as exc:
        raise ExplainabilityError(str(exc)) from exc

    return day6, day5, day44


def _indexed(items: list[dict[str, Any]], label: str) -> dict[int, dict[str, Any]]:
    index: dict[int, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            raise ExplainabilityError(f"{label} entries must be objects.")
        rank = item.get("hotspot_rank")
        if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1 or rank in index:
            raise ExplainabilityError(f"{label} hotspot ranks must be unique positive integers.")
        index[rank] = item
    return index


def _packet_id(day6_sha: str, day5_sha: str, day44_sha: str, rank: int, tile_id: int | str) -> str:
    canonical = json.dumps(
        {
            "day6": day6_sha,
            "day5": day5_sha,
            "day44": day44_sha,
            "hotspot_rank": rank,
            "tile_id": tile_id,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return "hs_explain_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]


def _contributions(priority_item: dict[str, Any], weights: dict[str, float]) -> tuple[Contribution, ...]:
    components = priority_item.get("components")
    if not isinstance(components, dict):
        raise ExplainabilityError("Day 5 components are missing.")
    mapping = {
        "hazard": "hazard_score",
        "mapped_exposure": "mapped_exposure_score",
        "context_sensitivity_proxy": "context_sensitivity_proxy",
    }
    result: list[Contribution] = []
    for weight_key, score_key in mapping.items():
        raw = _finite(components.get(score_key), score_key)
        weight = _finite(weights.get(weight_key), f"weight.{weight_key}")
        result.append(
            Contribution(
                component=weight_key,
                raw_score=round(raw, 4),
                weight=round(weight, 6),
                weighted_points=round(raw * weight, 4),
            )
        )
    total = round(sum(item.weighted_points for item in result), 4)
    expected = round(_finite(priority_item.get("pre_adaptation_priority_score"), "pre_adaptation_priority_score"), 4)
    if abs(total - expected) > 0.0002:
        raise ExplainabilityError(
            f"Priority contribution decomposition mismatch: weighted components={total}, score={expected}."
        )
    return tuple(result)


def _ledger(
    *,
    day44_item: dict[str, Any],
    day5_item: dict[str, Any],
    day6_result: Any,
) -> tuple[EvidenceLedgerEntry, ...]:
    hazard = day44_item.get("historical_hazard")
    context = day44_item.get("current_context")
    if not isinstance(hazard, dict) or not isinstance(context, dict):
        raise ExplainabilityError("Day 4.4 hotspot hazard/context sections are missing.")
    counts = context.get("category_counts")
    if not isinstance(counts, dict):
        raise ExplainabilityError("Day 4.4 context counts are missing.")

    thermal_id = day44_item.get("thermal_evidence_id")
    env_id = day44_item.get("environmental_evidence_id")
    ctx_id = day44_item.get("context_evidence_id")
    priority_id = day5_item.get("priority_evidence_id")

    entries = [
        EvidenceLedgerEntry(
            key="historical_air_temperature_celsius",
            label="Historical air temperature",
            classification="observed",
            value=hazard.get("temperature_celsius"),
            unit="C",
            source_artifact="day4.4_scenario_replay",
            source_evidence_id=thermal_id if isinstance(thermal_id, str) else None,
            status="observed_historical_hazard",
            explanation="FortyGuard thermal value preserved from the verified historical hazard event.",
        ),
        EvidenceLedgerEntry(
            key="historical_heat_index_celsius",
            label="Historical heat index",
            classification="observed",
            value=hazard.get("heat_index_celsius"),
            unit="C",
            source_artifact="day4.4_scenario_replay",
            source_evidence_id=env_id if isinstance(env_id, str) else None,
            status="observed_historical_environment",
            explanation="FortyGuard environmental value aligned to the historical thermal evidence.",
        ),
        EvidenceLedgerEntry(
            key="historical_apparent_temperature_celsius",
            label="Historical apparent temperature",
            classification="observed",
            value=hazard.get("apparent_temperature_celsius"),
            unit="C",
            source_artifact="day4.4_scenario_replay",
            source_evidence_id=env_id if isinstance(env_id, str) else None,
            status="observed_historical_environment",
            explanation="FortyGuard environmental value aligned to the historical thermal evidence.",
        ),
        EvidenceLedgerEntry(
            key="historical_wet_bulb_temperature_celsius",
            label="Historical wet-bulb temperature",
            classification="observed",
            value=hazard.get("wet_bulb_temperature_celsius"),
            unit="C",
            source_artifact="day4.4_scenario_replay",
            source_evidence_id=env_id if isinstance(env_id, str) else None,
            status="observed_historical_environment",
            explanation="FortyGuard environmental value aligned to the historical thermal evidence.",
        ),
        EvidenceLedgerEntry(
            key="historical_relative_humidity_percent",
            label="Historical relative humidity",
            classification="observed",
            value=hazard.get("relative_humidity_percent"),
            unit="percent",
            source_artifact="day4.4_scenario_replay",
            source_evidence_id=env_id if isinstance(env_id, str) else None,
            status="observed_historical_environment",
            explanation="FortyGuard environmental value aligned to the historical thermal evidence.",
        ),
    ]

    for category in ("healthcare", "education", "transit_waiting", "outdoor_public", "civic_public"):
        value = counts.get(category)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ExplainabilityError(f"Invalid observed OSM count for category {category!r}.")
        entries.append(
            EvidenceLedgerEntry(
                key=f"current_mapped_{category}_objects_within_radius",
                label=f"Current mapped {category.replace('_', ' ')} objects within radius",
                classification="observed",
                value=value,
                unit="mapped_objects",
                source_artifact="day4.4_scenario_replay",
                source_evidence_id=ctx_id if isinstance(ctx_id, str) else None,
                status="observed_current_map_context",
                explanation="Current OpenStreetMap object count; not population, occupancy, footfall, or independent-facility count.",
            )
        )

    components = day5_item.get("components")
    if not isinstance(components, dict):
        raise ExplainabilityError("Day 5 components are missing.")
    entries.extend(
        [
            EvidenceLedgerEntry(
                key="hazard_planning_ordinal",
                label="Hazard planning ordinal",
                classification="derived",
                value=components.get("hazard_score"),
                unit="planning_points_0_100",
                source_artifact="day5_planning_priority",
                source_evidence_id=priority_id if isinstance(priority_id, str) else None,
                status="derived_non_probability",
                explanation="Transparent planning ordinal derived from the observed heat-index band; not a health probability.",
            ),
            EvidenceLedgerEntry(
                key="mapped_exposure_proxy",
                label="Mapped exposure-context proxy",
                classification="derived",
                value=components.get("mapped_exposure_score"),
                unit="proxy_points_0_100",
                source_artifact="day5_planning_priority",
                source_evidence_id=priority_id if isinstance(priority_id, str) else None,
                status="derived_context_proxy",
                explanation="Derived from mapped context categories with saturation; not exposed-person count.",
            ),
            EvidenceLedgerEntry(
                key="context_sensitivity_proxy",
                label="Context sensitivity proxy",
                classification="derived",
                value=components.get("context_sensitivity_proxy"),
                unit="proxy_points_0_100",
                source_artifact="day5_planning_priority",
                source_evidence_id=priority_id if isinstance(priority_id, str) else None,
                status="derived_place_type_proxy",
                explanation="Place-type proxy based on mapped healthcare/education presence; not individual vulnerability.",
            ),
            EvidenceLedgerEntry(
                key="pre_adaptation_planning_priority",
                label="Pre-adaptation planning priority",
                classification="derived",
                value=day5_item.get("pre_adaptation_priority_score"),
                unit="planning_points_0_100",
                source_artifact="day5_planning_priority",
                source_evidence_id=priority_id if isinstance(priority_id, str) else None,
                status="derived_scenario_planning_priority",
                explanation="Scenario-planning prioritization index; not medical, epidemiological, or individual risk probability.",
            ),
        ]
    )

    if day6_result.vulnerability_score is None:
        entries.append(
            EvidenceLedgerEntry(
                key="verified_operational_vulnerability",
                label="Verified operational vulnerability",
                classification="unknown",
                value=None,
                unit="planning_points_0_100",
                source_artifact="day6_site_evidence",
                source_evidence_id=day6_result.evidence_bundle_id,
                status="unknown_not_verified",
                explanation="Operational vulnerability remains unknown until every required factor is explicitly verified.",
            )
        )
    else:
        entries.append(
            EvidenceLedgerEntry(
                key="verified_operational_vulnerability",
                label="Verified operational vulnerability",
                classification="derived",
                value=day6_result.vulnerability_score,
                unit="planning_points_0_100",
                source_artifact="day6_site_evidence",
                source_evidence_id=day6_result.evidence_bundle_id,
                status="derived_from_verified_operator_evidence",
                explanation="Ordinal summary derived only from explicitly verified operational evidence.",
            )
        )

    if day6_result.adaptive_capacity_score is None:
        entries.append(
            EvidenceLedgerEntry(
                key="verified_adaptive_capacity",
                label="Verified adaptive capacity",
                classification="unknown",
                value=None,
                unit="planning_points_0_100",
                source_artifact="day6_site_evidence",
                source_evidence_id=day6_result.evidence_bundle_id,
                status="unknown_not_verified",
                explanation="Adaptive capacity remains unknown until every required protective/control factor is explicitly verified.",
            )
        )
    else:
        entries.append(
            EvidenceLedgerEntry(
                key="verified_adaptive_capacity",
                label="Verified adaptive capacity",
                classification="derived",
                value=day6_result.adaptive_capacity_score,
                unit="planning_points_0_100",
                source_artifact="day6_site_evidence",
                source_evidence_id=day6_result.evidence_bundle_id,
                status="derived_from_verified_operator_evidence",
                explanation="Ordinal summary derived only from explicitly verified operational evidence.",
            )
        )

    if day6_result.evidence_adjusted_priority_score is None:
        entries.append(
            EvidenceLedgerEntry(
                key="evidence_adjusted_planning_priority",
                label="Evidence-adjusted planning priority",
                classification="withheld",
                value=None,
                unit="planning_points_0_100",
                source_artifact="day6_site_evidence",
                source_evidence_id=day6_result.evidence_bundle_id,
                status="withheld_incomplete_verified_evidence",
                explanation="Withheld because required vulnerability/adaptive-capacity evidence is incomplete.",
            )
        )
    else:
        entries.append(
            EvidenceLedgerEntry(
                key="evidence_adjusted_planning_priority",
                label="Evidence-adjusted planning priority",
                classification="derived",
                value=day6_result.evidence_adjusted_priority_score,
                unit="planning_points_0_100",
                source_artifact="day6_site_evidence",
                source_evidence_id=day6_result.evidence_bundle_id,
                status="derived_from_complete_verified_operational_evidence",
                explanation="Planning priority adjusted only after complete verified operational evidence; still not medical risk.",
            )
        )

    entries.append(
        EvidenceLedgerEntry(
            key="medical_risk_probability",
            label="Medical/clinical risk probability",
            classification="withheld",
            value=None,
            unit="probability",
            source_artifact="heatshield_policy",
            source_evidence_id=None,
            status="never_produced",
            explanation="HeatShield does not produce a medical, clinical, mortality, or individual probability-of-illness score.",
        )
    )
    return tuple(entries)


def build_explainability_packets(
    *,
    day6_path: str | Path,
    day5_path: str | Path,
    day44_path: str | Path,
) -> tuple[ExplainabilityPacket, ...]:
    try:
        day6, day5, day44 = _load_verified_chain(day6_path, day5_path, day44_path)
    except Day6ArtifactError as exc:
        raise ExplainabilityError(str(exc)) from exc

    priorities_raw = day5.get("priority_results")
    hotspots_raw = day44.get("hotspots")
    method = day5.get("method")
    source5 = day5.get("source")
    if not isinstance(priorities_raw, list) or not isinstance(hotspots_raw, list) or not isinstance(method, dict) or not isinstance(source5, dict):
        raise ExplainabilityError("Day 5/4.4 artifact sections required for explainability are missing.")
    weights_raw = method.get("baseline_weights")
    if not isinstance(weights_raw, dict):
        raise ExplainabilityError("Day 5 baseline weights are missing.")
    weights = {key: _finite(value, f"baseline_weights.{key}") for key, value in weights_raw.items()}
    if abs(sum(weights.values()) - 1.0) > 1e-9:
        raise ExplainabilityError("Day 5 baseline weights must sum to 1.0.")

    p_index = _indexed(priorities_raw, "Day 5 priority_results")
    h_index = _indexed(hotspots_raw, "Day 4.4 hotspots")
    d6_index = {item.hotspot_rank: item for item in day6.results}
    if set(p_index) != set(h_index) or set(p_index) != set(d6_index):
        raise ExplainabilityError("Hotspot identity sets differ across Day 4.4, Day 5, and Day 6 artifacts.")

    scenario_statement = day44.get("scenario_statement")
    if not isinstance(scenario_statement, str) or not scenario_statement:
        raise ExplainabilityError("Day 4.4 scenario statement is missing.")
    temporal_gap = _finite((day44.get("provenance") or {}).get("temporal_gap_days"), "temporal_gap_days")

    packets: list[ExplainabilityPacket] = []
    for rank in sorted(p_index):
        p = p_index[rank]
        h = h_index[rank]
        d6 = d6_index[rank]
        if str(p.get("tile_id")) != str(h.get("tile_id")) or str(p.get("tile_id")) != str(d6.tile_id):
            raise ExplainabilityError(f"Tile identity mismatch for hotspot_rank={rank}.")
        if p.get("priority_evidence_id") != d6.priority_evidence_id:
            raise ExplainabilityError(f"Priority evidence ID mismatch for hotspot_rank={rank}.")

        contributions = _contributions(p, weights)
        ledger = _ledger(day44_item=h, day5_item=p, day6_result=d6)
        unknowns = tuple(item.key for item in ledger if item.classification == "unknown")
        withheld = tuple(item.key for item in ledger if item.classification == "withheld")
        contribution_text = ", ".join(
            f"{item.component}={item.weighted_points:.2f} points" for item in contributions
        )
        pre_score = _finite(p.get("pre_adaptation_priority_score"), "pre_adaptation_priority_score")
        band = p.get("pre_adaptation_priority_band")
        if not isinstance(band, str) or not band:
            raise ExplainabilityError("Priority band is missing.")

        explanations = [
            f"The pre-adaptation planning priority is {pre_score:.2f}/100, decomposed exactly as {contribution_text}.",
            "The hazard term is anchored to historical FortyGuard environmental evidence; the mapped-context terms use current OSM data under an explicitly labeled scenario replay.",
            f"The historical hazard and current mapped context are separated by {temporal_gap:.3f} days; this temporal mismatch is part of the scenario, not hidden uncertainty.",
        ]
        if d6.evidence_adjusted_priority_score is None:
            explanations.append(
                "Evidence-adjusted priority is withheld because verified vulnerability and/or adaptive-capacity evidence is incomplete; unknown factors are not treated as zero."
            )
        else:
            explanations.append(
                f"Complete verified operational evidence unlocks an evidence-adjusted planning priority of {d6.evidence_adjusted_priority_score:.2f}/100; this remains a planning index, not a health probability."
            )

        packets.append(
            ExplainabilityPacket(
                packet_id=_packet_id(
                    day6.artifact_sha256,
                    day6.day5_artifact_sha256,
                    day6.day44_artifact_sha256,
                    rank,
                    d6.tile_id,
                ),
                hotspot_rank=rank,
                tile_id=d6.tile_id,
                scenario_scope=SCENARIO_SCOPE,
                scenario_statement=scenario_statement,
                temporal_gap_days=round(temporal_gap, 6),
                pre_adaptation_priority_score=round(pre_score, 4),
                pre_adaptation_priority_band=band,
                evidence_adjusted_priority_score=d6.evidence_adjusted_priority_score,
                evidence_adjusted_priority_band=d6.evidence_adjusted_priority_band,
                evidence_complete=d6.evidence_complete,
                contributions=contributions,
                evidence_ledger=ledger,
                unknowns=unknowns,
                withheld=withheld,
                explanation=tuple(explanations),
                guardrails=(
                    "Historical hazard must never be described as current heat.",
                    "Mapped OSM object counts must never be described as people, occupancy, footfall, or independent-facility counts.",
                    "Planning priority scores must never be described as medical/clinical probabilities.",
                    "Unknown vulnerability/adaptive-capacity evidence must never default to zero.",
                    "Recommendations are outside Day 7 and require the controlled recommendation layer.",
                ),
            )
        )

    return tuple(packets)
