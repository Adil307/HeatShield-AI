from __future__ import annotations

import json

import pytest

from app.services.day44_artifact import Day44ArtifactError, Day44HotspotInput, load_day44_priority_source
from app.services.priority_engine import (
    PriorityEngineError,
    context_sensitivity_proxy,
    hazard_ordinal_score,
    heat_index_band,
    mapped_exposure_score,
    priority_band,
    ranking_stability,
    score_hotspot,
    sensitivity_analysis,
)


def _hotspot(rank: int = 1, *, heat_index: float = 38.2, counts: dict[str, int] | None = None) -> Day44HotspotInput:
    return Day44HotspotInput(
        hotspot_rank=rank,
        tile_id=100 + rank,
        thermal_evidence_id=f"thermal-{rank}",
        environmental_evidence_id=f"env-{rank}",
        context_evidence_id=f"ctx-{rank}",
        heat_index_celsius=heat_index,
        apparent_temperature_celsius=38.4,
        wet_bulb_temperature_celsius=26.6,
        temperature_celsius=33.1,
        relative_humidity_percent=55.3,
        category_counts=counts
        or {
            "healthcare": 10,
            "education": 3,
            "transit_waiting": 20,
            "outdoor_public": 40,
            "civic_public": 3,
        },
        category_status={
            "healthcare": "observed",
            "education": "observed",
            "transit_waiting": "observed",
            "outdoor_public": "observed",
            "civic_public": "observed",
        },
        radius_meters=500.0,
    )


def _artifact(*, coverage: str = "complete", category_status: str = "observed") -> dict:
    counts = {
        "healthcare": 10,
        "education": 3,
        "transit_waiting": 20,
        "outdoor_public": 40,
        "civic_public": 3,
    }
    statuses = {key: category_status for key in counts}
    return {
        "schema_version": "heatshield.day4_4.scenario_replay.v1",
        "mode": "historical_hazard_current_context_scenario_replay",
        "scenario_statement": "Replay historical hazard against current context.",
        "provenance": {
            "hazard_observed_timestamp_utc": "2024-07-15T19:00:00+00:00",
            "current_context_fetched_at_utc": "2026-08-18T22:00:00+00:00",
            "temporal_gap_days": 764.125,
        },
        "context": {
            "coverage_status": coverage,
            "category_status": statuses,
        },
        "hotspots": [
            {
                "hotspot_rank": 1,
                "tile_id": 149,
                "thermal_evidence_id": "thermal-1",
                "environmental_evidence_id": "env-1",
                "context_evidence_id": "ctx-1",
                "historical_hazard": {
                    "temperature_celsius": 33.1424,
                    "heat_index_celsius": 38.2,
                    "apparent_temperature_celsius": 38.4,
                    "wet_bulb_temperature_celsius": 26.6,
                    "relative_humidity_percent": 55.3,
                },
                "current_context": {
                    "radius_meters": 500,
                    "category_counts": counts,
                    "category_status": statuses,
                },
            }
        ],
    }


def test_nws_band_boundaries():
    assert heat_index_band(20.0) == "below_nws_caution"
    assert heat_index_band(27.0) == "nws_caution"
    assert heat_index_band(38.2) == "nws_extreme_caution"
    assert heat_index_band(40.0) == "nws_danger"
    assert heat_index_band(52.0) == "nws_extreme_danger"
    assert hazard_ordinal_score(38.2) == 60.0


def test_mapped_exposure_is_bounded_and_count_saturated():
    low = {key: 1 for key in ("healthcare", "education", "transit_waiting", "outdoor_public", "civic_public")}
    huge = {key: 10_000 for key in low}
    assert 0 < mapped_exposure_score(low) < 100
    assert mapped_exposure_score(huge) == 100.0


def test_mapped_exposure_requires_all_categories():
    with pytest.raises(PriorityEngineError):
        mapped_exposure_score({"healthcare": 1})


def test_sensitivity_proxy_is_presence_only_not_raw_count():
    assert context_sensitivity_proxy({"healthcare": 1, "education": 1}) == 100.0
    assert context_sensitivity_proxy({"healthcare": 999, "education": 0}) == 50.0
    assert context_sensitivity_proxy({"healthcare": 0, "education": 0}) == 0.0


def test_score_withholds_final_risk_without_verified_vulnerability_and_adaptation():
    result = score_hotspot(_hotspot(), day44_sha256="a" * 64)
    assert result.final_priority_score is None
    assert result.components.verified_vulnerability_score is None
    assert result.components.verified_adaptive_capacity_score is None
    assert result.evidence_status["final_risk_score"].startswith("withheld")
    assert 0 <= result.pre_adaptation_priority_score <= 100


def test_unknown_category_is_never_scored_as_zero():
    hotspot = _hotspot()
    bad = Day44HotspotInput(
        hotspot_rank=hotspot.hotspot_rank,
        tile_id=hotspot.tile_id,
        thermal_evidence_id=hotspot.thermal_evidence_id,
        environmental_evidence_id=hotspot.environmental_evidence_id,
        context_evidence_id=hotspot.context_evidence_id,
        heat_index_celsius=hotspot.heat_index_celsius,
        apparent_temperature_celsius=hotspot.apparent_temperature_celsius,
        wet_bulb_temperature_celsius=hotspot.wet_bulb_temperature_celsius,
        temperature_celsius=hotspot.temperature_celsius,
        relative_humidity_percent=hotspot.relative_humidity_percent,
        category_counts=hotspot.category_counts,
        category_status={**hotspot.category_status, "education": "unavailable_provider_failure"},
        radius_meters=hotspot.radius_meters,
    )
    with pytest.raises(PriorityEngineError):
        score_hotspot(bad, day44_sha256="a" * 64)


def test_heat_index_is_required_for_nws_hazard_method():
    hotspot = _hotspot()
    no_hi = Day44HotspotInput(
        hotspot_rank=hotspot.hotspot_rank,
        tile_id=hotspot.tile_id,
        thermal_evidence_id=hotspot.thermal_evidence_id,
        environmental_evidence_id=hotspot.environmental_evidence_id,
        context_evidence_id=hotspot.context_evidence_id,
        heat_index_celsius=None,
        apparent_temperature_celsius=hotspot.apparent_temperature_celsius,
        wet_bulb_temperature_celsius=hotspot.wet_bulb_temperature_celsius,
        temperature_celsius=hotspot.temperature_celsius,
        relative_humidity_percent=hotspot.relative_humidity_percent,
        category_counts=hotspot.category_counts,
        category_status=hotspot.category_status,
        radius_meters=hotspot.radius_meters,
    )
    with pytest.raises(PriorityEngineError):
        score_hotspot(no_hi, day44_sha256="a" * 64)


def test_weight_sensitivity_reports_rank_stability():
    h1 = _hotspot(1, counts={"healthcare": 15, "education": 4, "transit_waiting": 30, "outdoor_public": 50, "civic_public": 5})
    h2 = _hotspot(2, counts={"healthcare": 5, "education": 2, "transit_waiting": 10, "outdoor_public": 15, "civic_public": 1})
    result = sensitivity_analysis((h1, h2))
    stability = ranking_stability(result)
    assert len(result) == 3
    assert stability["baseline_ranking"][0] == 1
    assert isinstance(stability["stable_across_weight_sets"], bool)


def test_priority_bands_are_internal_planning_bands():
    assert priority_band(39.9) == "lower_planning_priority"
    assert priority_band(40) == "moderate_planning_priority"
    assert priority_band(60) == "high_planning_priority"
    assert priority_band(80) == "very_high_planning_priority"


def test_day44_loader_requires_complete_context(tmp_path):
    path = tmp_path / "day44.json"
    path.write_text(json.dumps(_artifact(coverage="partial")), encoding="utf-8")
    with pytest.raises(Day44ArtifactError):
        load_day44_priority_source(path)


def test_day44_loader_rejects_unknown_category_status(tmp_path):
    path = tmp_path / "day44.json"
    path.write_text(json.dumps(_artifact(category_status="unavailable_provider_failure")), encoding="utf-8")
    with pytest.raises(Day44ArtifactError):
        load_day44_priority_source(path)


def test_day44_loader_reads_valid_scenario(tmp_path):
    path = tmp_path / "day44.json"
    path.write_text(json.dumps(_artifact()), encoding="utf-8")
    source = load_day44_priority_source(path)
    assert source.context_coverage_status == "complete"
    assert len(source.hotspots) == 1
    assert source.hotspots[0].heat_index_celsius == pytest.approx(38.2)
