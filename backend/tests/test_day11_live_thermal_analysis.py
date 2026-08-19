from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.schemas.fortyguard import HeatmapRequest
from app.services.live_thermal_analysis import (
    LiveThermalAnalysisError,
    live_request_hash,
    run_live_thermal_analysis,
    validate_live_request,
)


FIXTURE = Path(__file__).parent / "fixtures" / "day11_sample_heatmap_completed.json"


def request_for_box(*, west=-74.0, south=40.70, east=-73.998, north=40.702) -> HeatmapRequest:
    return HeatmapRequest.model_validate(
        {
            "polygon_aoi": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"source": "test"},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [west, south],
                                    [east, south],
                                    [east, north],
                                    [west, north],
                                    [west, south],
                                ]
                            ],
                        },
                    }
                ],
            },
            "date_time": {
                "start_date": "2026-08-19",
                "filter_type": 1,
                "start_time": "18:00",
            },
            "granularity": 100,
            "analytic_type": "tcm",
        }
    )


def test_day11_request_hash_is_deterministic() -> None:
    assert live_request_hash(request_for_box()) == live_request_hash(request_for_box())
    assert len(live_request_hash(request_for_box())) == 64


def test_day11_rejects_large_demo_aoi_before_provider_call() -> None:
    request = request_for_box(west=-74.2, south=40.60, east=-73.7, north=40.95)
    with pytest.raises(LiveThermalAnalysisError, match="Zoom in"):
        validate_live_request(request)


def test_day11_cache_hit_never_calls_provider(tmp_path: Path) -> None:
    request = request_for_box()
    cache_path = tmp_path / f"tcm_{live_request_hash(request)}.json"
    cache_path.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    class NoNetworkClient:
        async def submit_heatmap(self, request):  # pragma: no cover - failure guard
            raise AssertionError("cache hit must not submit a provider job")

        async def wait_for_completion(self, activity_id):  # pragma: no cover - failure guard
            raise AssertionError("cache hit must not poll provider")

    result = asyncio.run(
        run_live_thermal_analysis(request, client=NoNetworkClient(), cache_dir=tmp_path)
    )

    assert result["schema_version"] == "heatshield.day11.live_thermal_analysis.v1"
    assert result["analysis"]["cache_hit"] is True
    assert result["provenance"]["new_provider_jobs_for_this_request"] == 0
    assert result["summary"]["tile_count"] == 4
    assert result["summary"]["maximum_temperature_celsius"] == 33.0
    assert [item["tile_id"] for item in result["hottest_tiles"]] == [4, 3, 2]
    assert result["safety"]["planning_priority_supported"] is False
    assert result["safety"]["medical_probability_supported"] is False


def test_day11_fresh_job_is_cached_and_reused(tmp_path: Path) -> None:
    request = request_for_box()
    completion = json.loads(FIXTURE.read_text(encoding="utf-8"))

    class FakeClient:
        def __init__(self):
            self.submits = 0
            self.polls = 0

        async def submit_heatmap(self, request):
            self.submits += 1
            return {"data": {"activity_id": "day11-fixture-activity"}}

        async def wait_for_completion(self, activity_id):
            self.polls += 1
            assert activity_id == "day11-fixture-activity"
            return completion

    first_client = FakeClient()
    first = asyncio.run(
        run_live_thermal_analysis(request, client=first_client, cache_dir=tmp_path)
    )
    assert first_client.submits == 1
    assert first_client.polls == 1
    assert first["analysis"]["cache_hit"] is False
    assert first["provenance"]["new_provider_jobs_for_this_request"] == 1

    second_client = FakeClient()
    second = asyncio.run(
        run_live_thermal_analysis(request, client=second_client, cache_dir=tmp_path)
    )
    assert second_client.submits == 0
    assert second_client.polls == 0
    assert second["analysis"]["cache_hit"] is True
    assert second["provenance"]["activity_id"] == "day11-fixture-activity"


def test_day11_dashboard_route_rejects_oversize_before_credentials(monkeypatch) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.routes_dashboard import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/dashboard")
    payload = request_for_box(west=-74.2, south=40.60, east=-73.7, north=40.95).model_dump()
    response = TestClient(app).post("/api/v1/dashboard/live-analysis", json=payload)
    assert response.status_code == 400
    assert "Zoom in" in response.json()["detail"]
