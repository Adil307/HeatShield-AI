from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.providers.openstreetmap import OverpassError, validate_overpass_payload
from app.services.context_intelligence import (
    ContextValidationError,
    build_context_query_bundle,
    build_hotspot_contexts,
    expanded_bbox,
    haversine_meters,
    parse_overpass_context,
    query_bundle_fingerprint,
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


def test_query_bundle_uses_historical_bbox_and_splits_categories() -> None:
    plans, _ = build_context_query_bundle(
        HOTSPOTS,
        radius_meters=500,
        snapshot_utc=datetime(2024, 7, 15, 18, 0, tzinfo=timezone.utc),
    )
    assert len(plans) == 5
    assert {plan.category for plan in plans} == {
        "healthcare", "education", "transit_waiting", "outdoor_public", "civic_public"
    }
    healthcare = next(plan for plan in plans if plan.category == "healthcare")
    assert '[date:"2024-07-15T18:00:00Z"]' in healthcare.query
    assert "[bbox:" in healthcare.query
    assert "around:" not in healthcare.query
    assert 'nwr["amenity"="hospital"]' in healthcare.query
    assert "~" not in healthcare.query
    assert "[timeout:25]" in healthcare.query
    assert "out center tags qt;" in healthcare.query
    assert len(query_bundle_fingerprint(plans)) == 64


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



def test_http_200_overpass_runtime_remark_is_rejected() -> None:
    payload = {
        "elements": [],
        "remark": 'runtime error: Query timed out in "query" after 36 seconds.',
    }
    with pytest.raises(OverpassError, match="semantic failure"):
        validate_overpass_payload(payload)


def test_cached_overpass_runtime_remark_cannot_be_parsed_as_zero_context() -> None:
    wrapper = {
        "response": {
            "elements": [],
            "remark": 'runtime error: Query timed out in "query" after 36 seconds.',
        }
    }
    with pytest.raises(ContextValidationError, match="not semantically valid"):
        parse_overpass_context(wrapper)


def test_valid_empty_response_is_distinct_from_provider_failure() -> None:
    payload = {"elements": [], "osm3s": {"timestamp_osm_base": "2024-07-15T19:00:00Z"}}
    assert validate_overpass_payload(payload) is payload
    places, osm_base = parse_overpass_context(payload)
    assert places == ()
    assert osm_base == "2024-07-15T19:00:00Z"

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

@pytest.mark.asyncio
async def test_client_retries_semantic_failure_and_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.providers.openstreetmap as osm_provider
    from app.core.config import Settings

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self.status_code = 200
            self._payload = payload
            self.text = json.dumps(payload)

        def json(self) -> dict:
            return self._payload

    responses = [
        FakeResponse({"elements": [], "remark": "runtime error: Query timed out"}),
        FakeResponse({"elements": [{"type": "node", "id": 1}]}),
    ]

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, endpoint: str, data: dict) -> FakeResponse:
            assert data == {"data": "query"}
            return responses.pop(0)

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(osm_provider.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(osm_provider.asyncio, "sleep", no_sleep)

    settings = Settings(
        overpass_base_url="https://primary.example/api/interpreter",
        overpass_fallback_url="https://fallback.example/api/interpreter",
        overpass_third_url="",
        overpass_request_timeout_seconds=5,
    )
    result = await osm_provider.OverpassClient(settings).query("query")

    assert result.endpoint == "https://fallback.example/api/interpreter"
    assert result.request_count == 2
    assert result.semantic_rejections == 1
    assert result.attempted_endpoints == (
        "https://primary.example/api/interpreter",
        "https://fallback.example/api/interpreter",
    )


def test_category_status_distinguishes_unknown_from_observed_zero() -> None:
    contexts = build_hotspot_contexts(
        hotspots=HOTSPOTS,
        places=(),
        radius_meters=500,
        day3_sha256="a" * 64,
        query_sha256="b" * 64,
        category_status={
            "healthcare": "observed",
            "education": "unavailable_provider_failure",
            "transit_waiting": "observed",
            "outdoor_public": "observed",
            "civic_public": "observed",
        },
    )
    first = contexts[0].to_dict()
    assert first["category_counts"]["healthcare"] == 0
    assert first["category_status"]["healthcare"] == "observed"
    assert first["category_counts"]["education"] == 0
    assert first["category_status"]["education"] == "unavailable_provider_failure"


@pytest.mark.asyncio
async def test_client_can_reach_third_endpoint_after_two_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.providers.openstreetmap as osm_provider
    from app.core.config import Settings

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self.status_code = 200
            self._payload = payload
            self.text = json.dumps(payload)

        def json(self) -> dict:
            return self._payload

    responses = [
        FakeResponse({"elements": [], "remark": "runtime error: Query timed out"}),
        FakeResponse({"elements": [], "remark": "runtime error: Query timed out"}),
        FakeResponse({"elements": [{"type": "node", "id": 7}]}),
    ]

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, endpoint: str, data: dict) -> FakeResponse:
            return responses.pop(0)

    monkeypatch.setattr(osm_provider.httpx, "AsyncClient", FakeAsyncClient)
    settings = Settings(
        overpass_base_url="https://one.example",
        overpass_fallback_url="https://two.example",
        overpass_third_url="https://three.example",
        overpass_request_timeout_seconds=5,
    )
    result = await osm_provider.OverpassClient(settings).query("query")
    assert result.endpoint == "https://three.example"
    assert result.request_count == 3
    assert result.semantic_rejections == 2
    assert result.attempted_endpoints == (
        "https://one.example", "https://two.example", "https://three.example"
    )
