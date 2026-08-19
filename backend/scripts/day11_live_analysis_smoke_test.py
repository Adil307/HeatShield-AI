from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from app.schemas.fortyguard import HeatmapRequest
from app.services.live_thermal_analysis import run_live_thermal_analysis


FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "day11_sample_heatmap_completed.json"


def build_request() -> HeatmapRequest:
    return HeatmapRequest.model_validate(
        {
            "polygon_aoi": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"source": "day11_smoke"},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [-74.0000, 40.7000],
                                    [-73.9980, 40.7000],
                                    [-73.9980, 40.7020],
                                    [-74.0000, 40.7020],
                                    [-74.0000, 40.7000],
                                ]
                            ],
                        },
                    }
                ],
            },
            "date_time": {"start_date": "2026-08-19", "filter_type": 1, "start_time": "18:00"},
            "granularity": 100,
            "analytic_type": "tcm",
        }
    )


class FixtureClient:
    def __init__(self, completion: dict):
        self.completion = completion
        self.submits = 0
        self.polls = 0

    async def submit_heatmap(self, request: HeatmapRequest) -> dict:
        self.submits += 1
        return {"data": {"activity_id": "day11-smoke-activity"}}

    async def wait_for_completion(self, activity_id: str) -> dict:
        self.polls += 1
        return self.completion


async def main() -> None:
    completion = json.loads(FIXTURE.read_text(encoding="utf-8"))
    request = build_request()

    with tempfile.TemporaryDirectory(prefix="heatshield_day11_") as temp:
        first_client = FixtureClient(completion)
        first = await run_live_thermal_analysis(request, client=first_client, cache_dir=temp)

        second_client = FixtureClient(completion)
        second = await run_live_thermal_analysis(request, client=second_client, cache_dir=temp)

    assert first["schema_version"] == "heatshield.day11.live_thermal_analysis.v1"
    assert first_client.submits == 1 and first_client.polls == 1
    assert first["provenance"]["new_provider_jobs_for_this_request"] == 1
    assert second_client.submits == 0 and second_client.polls == 0
    assert second["provenance"]["cache_hit"] is True
    assert first["safety"]["planning_priority_supported"] is False
    assert first["safety"]["medical_probability_supported"] is False

    print("HEATSHIELD - DAY 11 CONTROLLED LIVE THERMAL ANALYSIS SMOKE TEST")
    print("=" * 72)
    print(f"Schema: {first['schema_version']}")
    print(f"Fixture provider jobs on first request: {first_client.submits}")
    print(f"Provider jobs on identical cached request: {second_client.submits}")
    print(f"Tiles: {first['summary']['tile_count']}")
    print(f"Maximum temperature: {first['summary']['maximum_temperature_celsius']:.2f} C")
    print(f"Hottest tile order: {[item['tile_id'] for item in first['hottest_tiles']]}")
    print(f"Planning priority supported: {first['safety']['planning_priority_supported']}")
    print(f"Medical probability supported: {first['safety']['medical_probability_supported']}")
    print("STATUS: PASS")


if __name__ == "__main__":
    asyncio.run(main())
