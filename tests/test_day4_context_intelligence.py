from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.context_intelligence import (
    ContextValidationError,
    build_context_query,
    build_hotspot_contexts,
    expanded_bbox,
    haversine_meters,
    parse_overpass_context,
    query_fingerprint,
)
from app.services.context_taxonomy import classify_context
from app.services.day3_artifact import Day3ArtifactError, Day3ContextInput, load_day3_artifact, resolve_osm_snapshot_utc


HOTSPOTS = (
    Day3ContextInput(
        rank=1,
        tile_id=149,
        thermal_evidence_id="hs_thermal_149",
        environmental_evidence_id="hs_env_149",
        latitude=40.7175,
        longitude=-74.0039,
        observed_timestamp="2024-07-15T14:00:00-04:00",
    ),
    Day3ContextInput(
        rank=2,
        tile_id=137,
        thermal_evidence_id="hs_thermal_137",
        environmental_evidence_id="hs_env_137",
        latitude=40.7166,
        longitude=-74.0039,
        observed_timestamp="2024-07-15T14:00:00-04:00",
    ),
)


def test_taxonomy_is_deterministic_and_non_risk() -> None:
    assert classify_context({"amenity": "hospital"}) == ("healthcare", "hospital")
    assert classify_context({"amenity": "school"}) == ("education", "school")
    assert classify_context({"highway": "bus_stop"}) == ("transit_waiting", "bus_stop")
    assert classify_context({"leisure": "park"}) == ("outdoor_public", "park")
    assert classify_context({"amenity": "restaurant"}) is None


def test_bbox_expands_around_all_hotspots() -> None:
    bbox = expanded_bbox(((h.latitude, h.longitude) for h in HOTSPOTS), 500)
    assert bbox.south < min(h.latitude for h in HOTSPOTS)
    assert bbox.north > max(h.latitude for h in HOTSPOTS)
    assert bbox.west < min(h.longitude for h in HOTSPOTS)
    assert bbox.east > max(h.longitude for h in HOTSPOTS)


def test_bbox_rejects_unbounded_radius() -> None:
    with pytest.raises(ContextValidationError):
        expanded_bbox(((40.7, -74.0),), 50)


def test_query_uses_historical_bbox_not_per_hotspot_around() -> None:
    query, _ = build_context_query(
        HOTSPOTS,
        radius_meters=500,
        snapshot_utc=datetime(2024, 7, 15, 18, 0, tzinfo=timezone.utc),
    )
    assert '[date:"2024-07-15T18:00:00Z"]' in query
    assert "[bbox:" in query
    assert "around:" not in query
    assert 'nwr["amenity"~' in query
    assert "out center tags qt;" in query


def test_query_fingerprint_is_deterministic() -> None:
    assert query_fingerprint("abc") == query_fingerprint("abc")
    assert query_fingerprint("abc") != query_fingerprint("abcd")


def test_parse_overpass_deduplicates_and_uses_way_center() -> None:
    payload = {
        "osm3s": {"timestamp_osm_base": "2024-07-15T18:00:00Z"},
        "elements": [
            {"type": "node", "id": 1, "lat": 40.7176, "lon": -74.0039, "tags": {"amenity": "school", "name": "A"}},
            {"type": "node", "id": 1, "lat": 40.7176, "lon": -74.0039, "tags": {"amenity": "school", "name": "A"}},
            {"type": "way", "id": 2, "center": {"lat": 40.7178, "lon": -74.0040}, "tags": {"amenity": "hospital", "name": "B"}},
            {"type": "node", "id": 3, "lat": 40.7, "lon": -74.0, "tags": {"amenity": "restaurant"}},
        ],
    }
    places, osm_base = parse_overpass_context(payload)
    assert len(places) == 2
    assert osm_base == "2024-07-15T18:00:00Z"
    assert any(p.osm_ref == "way/2" and p.category == "healthcare" for p in places)


def test_haversine_zero_and_short_distance() -> None:
    assert haversine_meters(40.0, -74.0, 40.0, -74.0) == pytest.approx(0.0)
    distance = haversine_meters(40.0, -74.0, 40.001, -74.0)
    assert 110 < distance < 112


def test_spatial_assignment_filters_outside_radius_and_preserves_evidence() -> None:
    payload = {
        "elements": [
            {"type": "node", "id": 1, "lat": 40.7176, "lon": -74.0039, "tags": {"amenity": "school", "name": "Near School"}},
            {"type": "node", "id": 2, "lat": 40.7300, "lon": -74.0039, "tags": {"amenity": "hospital", "name": "Far Hospital"}},
        ]
    }
    places, _ = parse_overpass_context(payload)
    contexts = build_hotspot_contexts(
        hotspots=HOTSPOTS,
        places=places,
        radius_meters=500,
        day3_sha256="a" * 64,
        query_sha256="b" * 64,
    )
    assert len(contexts) == 2
    assert contexts[0].category_counts["education"] == 1
    assert all(item.place.osm_id != 2 for context in contexts for item in context.nearby_places)
    assert contexts[0].environmental_evidence_id == "hs_env_149"
    assert contexts[0].context_evidence_id.startswith("hs_ctx_")


def test_day3_loader_and_timestamp_alignment(tmp_path: Path) -> None:
    artifact = {
        "schema_version": "heatshield.day3.environment.v1",
        "source": {
            "heatmap_artifact_path": "data/raw/x.json",
            "heatmap_artifact_sha256": "a" * 64,
            "date_time": {"start_date": "2024-07-15", "start_time": "14:00"},
        },
        "environmental_enrichments": [
            {
                "hotspot_rank": 1,
                "tile_id": 149,
                "thermal_evidence_id": "hs_t",
                "environmental_evidence_id": "hs_e",
                "representative_latitude": 40.7,
                "representative_longitude": -74.0,
                "observed": {"timestamp": "2024-07-15T14:00:00-04:00"},
            }
        ],
    }
    path = tmp_path / "day3.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    loaded = load_day3_artifact(path)
    snapshot, basis = resolve_osm_snapshot_utc(loaded)
    assert snapshot == datetime(2024, 7, 15, 18, 0, tzinfo=timezone.utc)
    assert basis == "provider_observed_timestamp"


def test_day3_loader_rejects_duplicate_ranks(tmp_path: Path) -> None:
    base = {
        "schema_version": "heatshield.day3.environment.v1",
        "source": {
            "heatmap_artifact_path": "x",
            "heatmap_artifact_sha256": "a" * 64,
        },
        "environmental_enrichments": [],
    }
    item = {
        "hotspot_rank": 1,
        "tile_id": 1,
        "thermal_evidence_id": "t",
        "environmental_evidence_id": "e",
        "representative_latitude": 40.0,
        "representative_longitude": -74.0,
        "observed": {"timestamp": "2024-07-15T14:00:00Z"},
    }
    base["environmental_enrichments"] = [item, {**item, "tile_id": 2}]
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(base), encoding="utf-8")
    with pytest.raises(Day3ArtifactError):
        load_day3_artifact(path)
