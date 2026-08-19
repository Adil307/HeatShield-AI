from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.environment import EnvironmentalObservation
from app.schemas.fortyguard import EnvironmentalDateTimeConfig, EnvironmentalParametersRequest
from app.services.environmental_enrichment import (
    build_environmental_enrichment,
    request_fingerprint,
)
from app.services.environmental_parser import (
    EnvironmentalValidationError,
    parse_environmental_artifact,
)
from app.services.geometry import representative_point


def test_environmental_request_matches_documented_shape() -> None:
    request = EnvironmentalParametersRequest(
        latitude=40.7128,
        longitude=-74.0060,
        temperature=32.5,
        date_time=EnvironmentalDateTimeConfig(
            start_date="2024-07-15",
            start_time="14:00",
            filter_type=1,
        ),
    )

    assert request.to_provider_payload() == {
        "latitude": 40.7128,
        "longitude": -74.0060,
        "temperature": 32.5,
        "date_time": {
            "start_date": "2024-07-15",
            "filter_type": 1,
            "start_time": "14:00",
        },
    }


def test_environmental_request_rejects_invalid_coordinate() -> None:
    with pytest.raises(ValidationError):
        EnvironmentalParametersRequest(
            latitude=91.0,
            longitude=0.0,
            temperature=30.0,
            date_time=EnvironmentalDateTimeConfig(
                start_date="2024-07-15",
                start_time="14:00",
                filter_type=1,
            ),
        )


def test_polygon_representative_point_rectangle() -> None:
    geometry = {
        "type": "Polygon",
        "coordinates": [[
            [-74.02, 40.70],
            [-74.00, 40.70],
            [-74.00, 40.72],
            [-74.02, 40.72],
            [-74.02, 40.70],
        ]],
    }
    lat, lon = representative_point(geometry)
    assert lat == pytest.approx(40.71, abs=1e-8)
    assert lon == pytest.approx(-74.01, abs=1e-8)


def test_multipolygon_uses_largest_exterior_ring() -> None:
    geometry = {
        "type": "MultiPolygon",
        "coordinates": [
            [[[[0.0, 0.0], [0.1, 0.0], [0.1, 0.1], [0.0, 0.1], [0.0, 0.0]]]],
            [[[[10.0, 10.0], [11.0, 10.0], [11.0, 11.0], [10.0, 11.0], [10.0, 10.0]]]],
        ],
    }
    # Correct GeoJSON MultiPolygon nesting has polygon -> rings -> points.
    geometry["coordinates"] = [
        [[[0.0, 0.0], [0.1, 0.0], [0.1, 0.1], [0.0, 0.1], [0.0, 0.0]]],
        [[[10.0, 10.0], [11.0, 10.0], [11.0, 11.0], [10.0, 11.0], [10.0, 10.0]]],
    ]
    lat, lon = representative_point(geometry)
    assert lat == pytest.approx(10.5)
    assert lon == pytest.approx(10.5)


def write_environmental_artifact(path: Path, *, sentinel_wet_bulb: bool = False) -> None:
    wet_bulb = ["NA"] if sentinel_wet_bulb else [26.1]
    payload = {
        "error": False,
        "data": {
            "activity_id": "env-123",
            "status": "Completed",
            "result": {
                "metadata": {
                    "timezone": "America/New_York",
                    "timestamps": ["2024-07-15T14:00:00-04:00"],
                },
                "locations": [
                    {
                        "lat": 40.7128,
                        "lon": -74.0060,
                        "temperature": 32.5,
                        "parameters": {
                            "heat_index_celsius": [35.4],
                            "apparent_temperature_celsius": [34.7],
                            "wet_bulb_temperature_celsius": wet_bulb,
                            "relative_humidity_percent": [58.0],
                        },
                    }
                ],
            },
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_environmental_parser_extracts_core_metrics(tmp_path: Path) -> None:
    path = tmp_path / "env.json"
    write_environmental_artifact(path)
    parsed = parse_environmental_artifact(path)

    assert parsed.activity_id == "env-123"
    assert parsed.observation.heat_index_celsius == 35.4
    assert parsed.observation.apparent_temperature_celsius == 34.7
    assert parsed.observation.wet_bulb_temperature_celsius == 26.1
    assert parsed.observation.relative_humidity_percent == 58.0


def test_environmental_parser_preserves_sentinel_as_missing(tmp_path: Path) -> None:
    path = tmp_path / "env.json"
    write_environmental_artifact(path, sentinel_wet_bulb=True)
    parsed = parse_environmental_artifact(path)
    assert parsed.observation.wet_bulb_temperature_celsius is None
    assert parsed.observation.heat_index_celsius == 35.4


def test_environmental_parser_rejects_unfinished_response(tmp_path: Path) -> None:
    path = tmp_path / "env.json"
    path.write_text(json.dumps({"data": {"status": "Processing"}}), encoding="utf-8")
    with pytest.raises(EnvironmentalValidationError, match="not completed"):
        parse_environmental_artifact(path)


def test_request_fingerprint_is_order_independent() -> None:
    first = {"latitude": 1.0, "temperature": 30.0, "date_time": {"filter_type": 1}}
    second = {"date_time": {"filter_type": 1}, "temperature": 30.0, "latitude": 1.0}
    assert request_fingerprint(first) == request_fingerprint(second)


def test_environmental_enrichment_computes_only_transparent_derivations() -> None:
    observation = EnvironmentalObservation(
        latitude=1.0,
        longitude=2.0,
        temperature_celsius=32.0,
        heat_index_celsius=35.0,
        apparent_temperature_celsius=34.0,
        wet_bulb_temperature_celsius=26.0,
        relative_humidity_percent=60.0,
        timezone="UTC",
        timestamp="2024-01-01T12:00:00+00:00",
    )

    result = build_environmental_enrichment(
        hotspot_rank=1,
        tile_id=10,
        thermal_evidence_id="hs_thermal_x",
        request_hash="a" * 64,
        representative_latitude=1.0,
        representative_longitude=2.0,
        activity_id="env-1",
        observation=observation,
    )

    assert result.apparent_minus_air_celsius == 2.0
    assert result.heat_index_minus_air_celsius == 3.0
    assert result.core_metric_completeness == 1.0
    assert result.environmental_evidence_id.startswith("hs_env_")
