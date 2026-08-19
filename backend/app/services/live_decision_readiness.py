from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from app.providers.fortyguard import FortyGuardError
from app.schemas.fortyguard import EnvironmentalDateTimeConfig, EnvironmentalParametersRequest, HeatmapRequest
from app.services.environmental_enrichment import build_environmental_enrichment, request_fingerprint
from app.services.environmental_parser import EnvironmentalValidationError, parse_environmental_artifact
from app.services.geometry import GeometryError, representative_point
from app.services.live_thermal_analysis import LiveThermalAnalysisError, run_live_thermal_analysis
from app.services.priority_engine import hazard_ordinal_score, heat_index_band


class LiveDecisionReadinessError(ValueError):
    """Raised when Day 12 cannot build a grounded live decision-readiness packet."""


class FortyGuardEnvironmentalClient(Protocol):
    async def submit_environmental_parameters(self, request: EnvironmentalParametersRequest) -> dict[str, Any]: ...

    async def wait_for_completion(self, activity_id: str) -> dict[str, Any]: ...


def _extract_activity_id(response: dict[str, Any]) -> str:
    data = response.get("data")
    activity_id = data.get("activity_id") if isinstance(data, dict) else None
    if not isinstance(activity_id, str) or not activity_id:
        raise LiveDecisionReadinessError("FortyGuard environmental submission returned no activity_id.")
    return activity_id


def _feature_for_tile(geojson: dict[str, Any], tile_id: int | str) -> dict[str, Any]:
    features = geojson.get("features") if isinstance(geojson, dict) else None
    if not isinstance(features, list):
        raise LiveDecisionReadinessError("Live heatmap GeoJSON has no feature list.")

    target = str(tile_id)
    for feature in features:
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties")
        if not isinstance(props, dict):
            continue
        for key in ("tile_id", "tileId", "id", "tile", "grid_id"):
            value = props.get(key)
            if value is not None and str(value) == target:
                return feature
    raise LiveDecisionReadinessError(f"Could not find GeoJSON geometry for hottest tile {tile_id!r}.")


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def _environmental_request(
    request: HeatmapRequest,
    *,
    latitude: float,
    longitude: float,
    temperature_celsius: float,
) -> EnvironmentalParametersRequest:
    # Day 11 is intentionally single-hour TCM. Day 12 keeps the environmental
    # enrichment aligned to that same wall-clock request rather than silently
    # changing time semantics.
    if request.date_time.filter_type != 1 or not request.date_time.start_time:
        raise LiveDecisionReadinessError("Day 12 live enrichment requires a single-hour live analysis.")
    return EnvironmentalParametersRequest(
        latitude=latitude,
        longitude=longitude,
        temperature=temperature_celsius,
        date_time=EnvironmentalDateTimeConfig(
            start_date=request.date_time.start_date,
            filter_type=1,
            start_time=request.date_time.start_time,
        ),
    )


def _next_checks() -> list[dict[str, str]]:
    return [
        {
            "check_id": "verify_exposure_context",
            "label": "Verify exposure context",
            "reason": "Thermal stress alone does not show how many people, assets, or activities are meaningfully exposed.",
            "classification": "RECOMMENDED_EVIDENCE_CHECK",
        },
        {
            "check_id": "verify_operational_vulnerability",
            "label": "Verify operational vulnerability",
            "reason": "Activity intensity, acclimatization, and heat-trapping PPE/clothing must come from an authorized source.",
            "classification": "RECOMMENDED_EVIDENCE_CHECK",
        },
        {
            "check_id": "verify_adaptive_capacity",
            "label": "Verify protection and controls",
            "reason": "Water, shaded/cooled recovery, work-rest controls, and heat monitoring can change operational priority but are not inferred from the map.",
            "classification": "RECOMMENDED_EVIDENCE_CHECK",
        },
    ]


async def run_live_decision_readiness(
    request: HeatmapRequest,
    *,
    client: FortyGuardEnvironmentalClient | None,
    live_cache_dir: str | Path,
    env_cache_dir: str | Path,
) -> dict[str, Any]:
    """Enrich the verified Day 11 hottest tile and state what decisions are ready.

    This function never creates a second heatmap job: the Day 11 completion must
    already exist in cache. The only optional new provider job is the explicit
    environmental-parameters enrichment for the hottest verified tile.
    """
    try:
        live = await run_live_thermal_analysis(request, client=None, cache_dir=live_cache_dir)
    except LiveThermalAnalysisError as exc:
        raise LiveDecisionReadinessError(
            "Run the fresh thermal analysis first; Day 12 enrichment only reuses a verified Day 11 completion."
        ) from exc

    hottest = live.get("hottest_tiles") or []
    if not hottest or not isinstance(hottest[0], dict):
        raise LiveDecisionReadinessError("The live thermal result contains no hottest-tile candidate.")
    top = hottest[0]
    tile_id = top.get("tile_id")
    thermal_evidence_id = top.get("evidence_id")
    temperature = top.get("temperature_celsius")
    if tile_id is None or not isinstance(thermal_evidence_id, str) or not thermal_evidence_id:
        raise LiveDecisionReadinessError("The hottest tile is missing provenance identifiers.")
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
        raise LiveDecisionReadinessError("The hottest tile is missing a valid temperature.")

    feature = _feature_for_tile(live["heatmap_geojson"], tile_id)
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict):
        raise LiveDecisionReadinessError("The hottest tile has no valid geometry.")
    try:
        latitude, longitude = representative_point(geometry)
    except GeometryError as exc:
        raise LiveDecisionReadinessError(str(exc)) from exc

    env_request = _environmental_request(
        request,
        latitude=latitude,
        longitude=longitude,
        temperature_celsius=float(temperature),
    )
    env_hash = request_fingerprint(env_request.to_provider_payload())
    env_cache_path = Path(env_cache_dir) / f"env_top_{tile_id}_{env_hash}.json"

    parsed = None
    env_cache_hit = False
    if env_cache_path.exists():
        try:
            parsed = parse_environmental_artifact(env_cache_path)
            env_cache_hit = True
        except EnvironmentalValidationError:
            try:
                env_cache_path.unlink()
            except OSError:
                pass

    submitted_activity_id: str | None = None
    if parsed is None:
        if client is None:
            raise LiveDecisionReadinessError(
                "FORTYGUARD_API_KEY is not configured and no completed Day 12 environmental cache exists for this hottest tile."
            )
        try:
            submitted = await client.submit_environmental_parameters(env_request)
            submitted_activity_id = _extract_activity_id(submitted)
            completed = await client.wait_for_completion(submitted_activity_id)
        except FortyGuardError:
            raise
        _atomic_write_json(env_cache_path, completed)
        try:
            parsed = parse_environmental_artifact(env_cache_path)
        except EnvironmentalValidationError as exc:
            try:
                env_cache_path.unlink()
            except OSError:
                pass
            raise LiveDecisionReadinessError(f"Environmental completion could not be validated: {exc}") from exc

    observation = parsed.observation
    if abs(observation.latitude - latitude) > 0.01 or abs(observation.longitude - longitude) > 0.01:
        raise LiveDecisionReadinessError("Environmental location differs materially from the hottest-tile representative point.")
    if abs(observation.temperature_celsius - float(temperature)) > 0.05:
        raise LiveDecisionReadinessError("Environmental temperature does not match the verified hottest-tile temperature.")

    enrichment = build_environmental_enrichment(
        hotspot_rank=int(top.get("hotspot_rank") or 1),
        tile_id=tile_id,
        thermal_evidence_id=thermal_evidence_id,
        request_hash=env_hash,
        representative_latitude=latitude,
        representative_longitude=longitude,
        activity_id=parsed.activity_id or submitted_activity_id,
        observation=observation,
    )

    heat_index = observation.heat_index_celsius
    if heat_index is None:
        hazard = {
            "status": "withheld_missing_observed_heat_index",
            "heat_index_band": None,
            "hazard_planning_ordinal": None,
            "note": "HeatShield does not substitute air or apparent temperature into the heat-index hazard band.",
        }
    else:
        hazard = {
            "status": "derived_from_observed_heat_index",
            "heat_index_band": heat_index_band(heat_index),
            "hazard_planning_ordinal": hazard_ordinal_score(heat_index),
            "note": "HeatShield hazard ordinal is a transparent planning category, not a medical probability or an NWS-issued numeric score.",
        }

    return {
        "schema_version": "heatshield.day12.live_decision_readiness.v1",
        "mode": "fresh_provider_thermal_stress_decision_readiness",
        "selected_hotspot": {
            "hotspot_rank": enrichment.hotspot_rank,
            "tile_id": enrichment.tile_id,
            "temperature_celsius": float(temperature),
            "relative_band": top.get("relative_band"),
            "thermal_evidence_id": enrichment.thermal_evidence_id,
            "representative_latitude": latitude,
            "representative_longitude": longitude,
        },
        "environmental_observed": enrichment.observed.to_dict(),
        "environmental_derived": {
            "environmental_evidence_id": enrichment.environmental_evidence_id,
            "core_metric_completeness": enrichment.core_metric_completeness,
            "heat_index_minus_air_celsius": enrichment.heat_index_minus_air_celsius,
            "apparent_minus_air_celsius": enrichment.apparent_minus_air_celsius,
            **hazard,
        },
        "decision_readiness": {
            "thermal_evidence": "observed_verified",
            "thermal_stress_enrichment": "observed_verified",
            "relative_hotspot_rank": "derived_supported",
            "hazard_ordinal": hazard["status"],
            "mapped_exposure_context": "missing",
            "operational_vulnerability": "missing",
            "adaptive_capacity": "missing",
            "planning_priority": "withheld_missing_required_context",
            "medical_risk_probability": "not_supported",
        },
        "next_checks": _next_checks(),
        "provenance": {
            "thermal_provider": "FortyGuard",
            "thermal_activity_id": live.get("provenance", {}).get("activity_id"),
            "thermal_request_hash": live.get("provenance", {}).get("request_hash"),
            "thermal_evidence_id": enrichment.thermal_evidence_id,
            "environmental_provider": "FortyGuard",
            "environmental_activity_id": parsed.activity_id or submitted_activity_id,
            "environmental_request_hash": env_hash,
            "environmental_evidence_id": enrichment.environmental_evidence_id,
            "environmental_cache_hit": env_cache_hit,
            "new_heatmap_jobs_for_this_request": 0,
            "new_environmental_jobs_for_this_request": 0 if env_cache_hit else 1,
        },
        "classification": {
            "OBSERVED": "FortyGuard air temperature plus environmental thermal-stress parameters for the verified hottest tile.",
            "DERIVED": "Relative hotspot rank, evidence links, metric deltas, completeness, and hazard planning ordinal when observed heat index is available.",
            "INFERRED": "No occupancy, vulnerability, adaptive capacity, or individual medical risk is inferred.",
            "RECOMMENDED": "Evidence-collection checks only; no site intervention is recommended from thermal evidence alone.",
        },
        "safety": {
            "planning_priority_supported": False,
            "medical_probability_supported": False,
            "occupancy_inferred": False,
            "intervention_recommendations_generated": False,
            "scope_note": "Day 12 improves live decision readiness without crossing the evidence boundary: full planning priority remains withheld until required context is verified.",
        },
    }
