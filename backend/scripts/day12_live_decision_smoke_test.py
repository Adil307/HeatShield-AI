from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from app.schemas.fortyguard import HeatmapRequest
from app.services.live_decision_readiness import run_live_decision_readiness
from app.services.live_thermal_analysis import live_request_hash


FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def request() -> HeatmapRequest:
    return HeatmapRequest.model_validate({
        "polygon_aoi": {"type": "FeatureCollection", "features": [{
            "type": "Feature", "properties": {"source": "day12-smoke"},
            "geometry": {"type": "Polygon", "coordinates": [[
                [-74.0, 40.70], [-73.998, 40.70], [-73.998, 40.702], [-74.0, 40.702], [-74.0, 40.70]
            ]]}
        }]},
        "date_time": {"start_date": "2026-08-19", "filter_type": 1, "start_time": "18:00"},
        "granularity": 100,
        "analytic_type": "tcm",
    })


def main() -> int:
    req = request()
    env_completion = json.loads((FIXTURES / "day12_sample_environment_completed.json").read_text(encoding="utf-8"))

    class FixtureClient:
        submissions = 0
        polls = 0

        async def submit_environmental_parameters(self, request):
            self.submissions += 1
            return {"data": {"activity_id": "day12-env-fixture-activity"}}

        async def wait_for_completion(self, activity_id):
            self.polls += 1
            return env_completion

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        live_dir = root / "day11"
        env_dir = root / "day12"
        live_dir.mkdir(parents=True)
        (live_dir / f"tcm_{live_request_hash(req)}.json").write_text(
            (FIXTURES / "day11_sample_heatmap_completed.json").read_text(encoding="utf-8"), encoding="utf-8"
        )
        client = FixtureClient()
        result = asyncio.run(run_live_decision_readiness(req, client=client, live_cache_dir=live_dir, env_cache_dir=env_dir))
        second = asyncio.run(run_live_decision_readiness(req, client=client, live_cache_dir=live_dir, env_cache_dir=env_dir))

    assert result["selected_hotspot"]["tile_id"] == 4
    assert result["environmental_derived"]["hazard_planning_ordinal"] == 60.0
    assert result["decision_readiness"]["planning_priority"].startswith("withheld")
    assert result["safety"]["medical_probability_supported"] is False
    assert second["provenance"]["environmental_cache_hit"] is True
    assert client.submissions == 1 and client.polls == 1

    print("HEATSHIELD - DAY 12 LIVE DECISION READINESS SMOKE TEST")
    print("=" * 72)
    print(f"Selected hottest tile: {result['selected_hotspot']['tile_id']}")
    print(f"Observed heat index: {result['environmental_observed']['heat_index_celsius']} C")
    print(f"Derived hazard ordinal: {result['environmental_derived']['hazard_planning_ordinal']}/100")
    print(f"Planning priority: {result['decision_readiness']['planning_priority']}")
    print(f"Medical probability supported: {result['safety']['medical_probability_supported']}")
    print(f"Fixture environmental submissions: {client.submissions}")
    print("Real FortyGuard calls: 0")
    print("Cache reuse verified: True")
    print("STATUS: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
