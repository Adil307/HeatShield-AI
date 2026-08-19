from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.services.context_taxonomy import CATEGORY_ORDER
from app.services.scenario_replay import (
    ScenarioReplayError,
    build_current_context_query_bundle,
    coverage_status,
    load_scenario_replay_source,
    scenario_query_bundle_sha256,
    temporal_gap_days,
)


def _artifact() -> dict:
    return {
        "schema_version": "heatshield.day3.environment.v1",
        "source": {
            "heatmap_artifact_path": "data/raw/official_heatmap_completed.json",
            "heatmap_artifact_sha256": "a" * 64,
        },
        "environmental_enrichments": [
            {
                "hotspot_rank": 1,
                "tile_id": 149,
                "thermal_evidence_id": "hs_thermal_149",
                "environmental_evidence_id": "hs_env_149",
                "representative_latitude": 40.7175,
                "representative_longitude": -74.0038,
                "observed": {
                    "timestamp": "2024-07-15T14:00:00-05:00",
                    "temperature_celsius": 33.1424,
                    "heat_index_celsius": 38.2,
                    "apparent_temperature_celsius": 38.4,
                    "wet_bulb_temperature_celsius": 26.6,
                    "relative_humidity_percent": 55.3,
                },
            },
            {
                "hotspot_rank": 2,
                "tile_id": 137,
                "thermal_evidence_id": "hs_thermal_137",
                "environmental_evidence_id": "hs_env_137",
                "representative_latitude": 40.7166,
                "representative_longitude": -74.0038,
                "observed": {
                    "timestamp": "2024-07-15T14:00:00-05:00",
                    "temperature_celsius": 33.1396,
                    "heat_index_celsius": 38.2,
                    "apparent_temperature_celsius": 38.4,
                    "wet_bulb_temperature_celsius": 26.6,
                    "relative_humidity_percent": 55.3,
                },
            },
        ],
    }


def test_load_scenario_source_preserves_historical_observations(tmp_path) -> None:
    path = tmp_path / "day3.json"
    path.write_text(json.dumps(_artifact()), encoding="utf-8")
    source = load_scenario_replay_source(path, hotspot_limit=2)
    assert source.hazard_timestamp == "2024-07-15T19:00:00+00:00"
    assert len(source.hotspots) == 2
    assert source.hotspots[0].temperature_celsius == pytest.approx(33.1424)
    assert source.hotspots[0].heat_index_celsius == pytest.approx(38.2)


def test_current_query_bundle_uses_five_categories_and_no_history_date(tmp_path) -> None:
    path = tmp_path / "day3.json"
    path.write_text(json.dumps(_artifact()), encoding="utf-8")
    source = load_scenario_replay_source(path, hotspot_limit=2)
    plans, bbox = build_current_context_query_bundle(
        (item.context_input for item in source.hotspots),
        radius_meters=500,
    )
    assert tuple(plan.category for plan in plans) == CATEGORY_ORDER
    assert all('[date:' not in plan.query for plan in plans)
    assert all('[bbox:' in plan.query for plan in plans)
    assert bbox.south < bbox.north
    assert bbox.west < bbox.east


def test_current_queries_use_exact_tag_filters(tmp_path) -> None:
    path = tmp_path / "day3.json"
    path.write_text(json.dumps(_artifact()), encoding="utf-8")
    source = load_scenario_replay_source(path)
    plans, _ = build_current_context_query_bundle(
        (item.context_input for item in source.hotspots),
        radius_meters=500,
    )
    text = "\n".join(plan.query for plan in plans)
    assert 'amenity"="hospital' in text
    assert 'highway"="bus_stop' in text
    assert '[date:' not in text


def test_query_bundle_fingerprint_is_stable(tmp_path) -> None:
    path = tmp_path / "day3.json"
    path.write_text(json.dumps(_artifact()), encoding="utf-8")
    source = load_scenario_replay_source(path)
    plans, _ = build_current_context_query_bundle(
        (item.context_input for item in source.hotspots), radius_meters=500
    )
    first = scenario_query_bundle_sha256(plans)
    second = scenario_query_bundle_sha256(plans)
    assert first == second
    assert len(first) == 64


def test_coverage_status_distinguishes_unknown_from_zero() -> None:
    complete = {category: "observed" for category in CATEGORY_ORDER}
    partial = dict(complete)
    partial["education"] = "unavailable_provider_failure"
    unavailable = {category: "unavailable_provider_failure" for category in CATEGORY_ORDER}
    assert coverage_status(complete) == "complete"
    assert coverage_status(partial) == "partial"
    assert coverage_status(unavailable) == "unavailable"


def test_temporal_gap_is_explicit() -> None:
    gap = temporal_gap_days(
        hazard_timestamp="2024-07-15T19:00:00+00:00",
        context_timestamp_utc="2026-08-19T00:00:00+00:00",
    )
    assert gap > 700


def test_rejects_misaligned_hazard_timestamps(tmp_path) -> None:
    payload = _artifact()
    payload["environmental_enrichments"][1]["observed"]["timestamp"] = "2024-07-15T15:00:00-05:00"
    path = tmp_path / "day3.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ScenarioReplayError):
        load_scenario_replay_source(path, hotspot_limit=2)
