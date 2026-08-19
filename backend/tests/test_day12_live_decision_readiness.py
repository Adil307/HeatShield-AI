from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.schemas.fortyguard import HeatmapRequest
from app.services.live_decision_readiness import LiveDecisionReadinessError, run_live_decision_readiness
from app.services.live_thermal_analysis import live_request_hash


FIXTURES = Path(__file__).parent / "fixtures"
HEATMAP = FIXTURES / "day11_sample_heatmap_completed.json"
ENV = FIXTURES / "day12_sample_environment_completed.json"


def live_request() -> HeatmapRequest:
    return HeatmapRequest.model_validate(
        {
            "polygon_aoi": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"source": "day12-test"},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[
                                [-74.0, 40.70],
                                [-73.998, 40.70],
                                [-73.998, 40.702],
                                [-74.0, 40.702],
                                [-74.0, 40.70],
                            ]],
                        },
                    }
                ],
            },
            "date_time": {"start_date": "2026-08-19", "filter_type": 1, "start_time": "18:00"},
            "granularity": 100,
            "analytic_type": "tcm",
        }
    )


def seed_live_cache(directory: Path, request: HeatmapRequest) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"tcm_{live_request_hash(request)}.json").write_text(
        HEATMAP.read_text(encoding="utf-8"), encoding="utf-8"
    )


def test_day12_requires_existing_verified_live_completion(tmp_path: Path) -> None:
    with pytest.raises(LiveDecisionReadinessError, match="Run the fresh thermal analysis first"):
        asyncio.run(
            run_live_decision_readiness(
                live_request(), client=None, live_cache_dir=tmp_path / "live", env_cache_dir=tmp_path / "env"
            )
        )


def test_day12_enriches_server_selected_hottest_tile_and_keeps_priority_withheld(tmp_path: Path) -> None:
    request = live_request()
    seed_live_cache(tmp_path / "live", request)
    completion = json.loads(ENV.read_text(encoding="utf-8"))

    class FakeEnvironmentalClient:
        def __init__(self):
            self.requests = []
            self.polls = 0

        async def submit_environmental_parameters(self, request):
            self.requests.append(request)
            return {"data": {"activity_id": "day12-env-fixture-activity"}}

        async def wait_for_completion(self, activity_id):
            self.polls += 1
            assert activity_id == "day12-env-fixture-activity"
            return completion

    client = FakeEnvironmentalClient()
    result = asyncio.run(
        run_live_decision_readiness(
            request, client=client, live_cache_dir=tmp_path / "live", env_cache_dir=tmp_path / "env"
        )
    )

    assert len(client.requests) == 1
    env_request = client.requests[0]
    assert env_request.latitude == pytest.approx(40.7015)
    assert env_request.longitude == pytest.approx(-73.9985)
    assert env_request.temperature == 33.0
    assert env_request.date_time.start_date == "2026-08-19"
    assert env_request.date_time.start_time == "18:00"

    assert result["schema_version"] == "heatshield.day12.live_decision_readiness.v1"
    assert result["selected_hotspot"]["tile_id"] == 4
    assert result["selected_hotspot"]["hotspot_rank"] == 1
    assert result["environmental_observed"]["heat_index_celsius"] == 38.2
    assert result["environmental_derived"]["heat_index_band"] == "nws_extreme_caution"
    assert result["environmental_derived"]["hazard_planning_ordinal"] == 60.0
    assert result["decision_readiness"]["planning_priority"] == "withheld_missing_required_context"
    assert result["decision_readiness"]["medical_risk_probability"] == "not_supported"
    assert result["safety"]["occupancy_inferred"] is False
    assert result["safety"]["intervention_recommendations_generated"] is False
    assert [item["check_id"] for item in result["next_checks"]] == [
        "verify_exposure_context",
        "verify_operational_vulnerability",
        "verify_adaptive_capacity",
    ]
    assert result["provenance"]["new_heatmap_jobs_for_this_request"] == 0
    assert result["provenance"]["new_environmental_jobs_for_this_request"] == 1


def test_day12_environmental_cache_reuse_makes_zero_new_provider_calls(tmp_path: Path) -> None:
    request = live_request()
    seed_live_cache(tmp_path / "live", request)
    completion = json.loads(ENV.read_text(encoding="utf-8"))

    class FirstClient:
        async def submit_environmental_parameters(self, request):
            return {"data": {"activity_id": "day12-env-fixture-activity"}}

        async def wait_for_completion(self, activity_id):
            return completion

    first = asyncio.run(
        run_live_decision_readiness(
            request, client=FirstClient(), live_cache_dir=tmp_path / "live", env_cache_dir=tmp_path / "env"
        )
    )
    assert first["provenance"]["environmental_cache_hit"] is False

    class NoNetworkClient:
        async def submit_environmental_parameters(self, request):  # pragma: no cover - safety guard
            raise AssertionError("completed environmental cache must prevent submission")

        async def wait_for_completion(self, activity_id):  # pragma: no cover - safety guard
            raise AssertionError("completed environmental cache must prevent polling")

    second = asyncio.run(
        run_live_decision_readiness(
            request, client=NoNetworkClient(), live_cache_dir=tmp_path / "live", env_cache_dir=tmp_path / "env"
        )
    )
    assert second["provenance"]["environmental_cache_hit"] is True
    assert second["provenance"]["new_environmental_jobs_for_this_request"] == 0
    assert second["provenance"]["environmental_activity_id"] == "day12-env-fixture-activity"


def test_day12_does_not_substitute_other_temperature_metrics_for_missing_heat_index(tmp_path: Path) -> None:
    request = live_request()
    seed_live_cache(tmp_path / "live", request)
    completion = json.loads(ENV.read_text(encoding="utf-8"))
    completion["data"]["result"]["locations"][0]["parameters"]["heat_index_celsius"] = ["N/A"]

    class Client:
        async def submit_environmental_parameters(self, request):
            return {"data": {"activity_id": "day12-missing-hi"}}

        async def wait_for_completion(self, activity_id):
            return completion

    result = asyncio.run(
        run_live_decision_readiness(
            request, client=Client(), live_cache_dir=tmp_path / "live", env_cache_dir=tmp_path / "env"
        )
    )
    assert result["environmental_observed"]["heat_index_celsius"] is None
    assert result["environmental_derived"]["hazard_planning_ordinal"] is None
    assert result["environmental_derived"]["status"] == "withheld_missing_observed_heat_index"
