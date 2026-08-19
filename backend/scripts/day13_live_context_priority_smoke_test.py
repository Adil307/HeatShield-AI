from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from app.schemas.fortyguard import HeatmapRequest
from app.services.live_context_priority import Day13ContextPriorityRequest, Day13ContextProfile, run_live_context_priority
from app.services.live_decision_readiness import run_live_decision_readiness
from app.services.live_thermal_analysis import live_request_hash


BACKEND = Path(__file__).resolve().parents[1]
FIXTURES = BACKEND / "tests" / "fixtures"
HEATMAP = FIXTURES / "day11_sample_heatmap_completed.json"
ENV = FIXTURES / "day12_sample_environment_completed.json"
CATALOG = BACKEND / "config" / "day8_action_catalog.json"


def request() -> HeatmapRequest:
    return HeatmapRequest.model_validate(
        {
            "polygon_aoi": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"source": "day13-smoke"},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[
                                [-74.0, 40.70], [-73.998, 40.70], [-73.998, 40.702],
                                [-74.0, 40.702], [-74.0, 40.70],
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


def profile() -> Day13ContextProfile:
    return Day13ContextProfile.model_validate(
        {
            "source_type": "authorized_operator_input",
            "source_ref": "Day 13 smoke authorized operations record",
            "observed_at": "2026-08-20T03:40:00+05:00",
            "exposure_level": "high",
            "sensitive_use_context": "education_and_healthcare",
            "physical_exertion": "high",
            "acclimatization_gap": "partial",
            "heat_trapping_ppe_or_clothing": "some",
            "potable_water_access": "adequate",
            "shaded_or_cooled_recovery": "partial",
            "work_rest_controls": "adequate",
            "heat_training_and_monitoring": "partial",
        }
    )


async def main() -> None:
    req = request()
    completion = json.loads(ENV.read_text(encoding="utf-8"))

    class FixtureEnvironmentalClient:
        async def submit_environmental_parameters(self, request):
            return {"data": {"activity_id": "day13-smoke-env"}}

        async def wait_for_completion(self, activity_id):
            return completion

    with tempfile.TemporaryDirectory(prefix="heatshield-day13-") as temp:
        root = Path(temp)
        live_dir, env_dir = root / "live", root / "env"
        live_dir.mkdir(parents=True, exist_ok=True)
        (live_dir / f"tcm_{live_request_hash(req)}.json").write_text(
            HEATMAP.read_text(encoding="utf-8"), encoding="utf-8"
        )
        await run_live_decision_readiness(
            req,
            client=FixtureEnvironmentalClient(),
            live_cache_dir=live_dir,
            env_cache_dir=env_dir,
        )
        result = await run_live_context_priority(
            Day13ContextPriorityRequest(analysis_request=req, context_profile=profile()),
            live_cache_dir=live_dir,
            env_cache_dir=env_dir,
            catalog_path=CATALOG,
        )

    priority = result["priority"]
    print("HEATSHIELD - DAY 13 CONTROLLED LIVE CONTEXT PRIORITY SMOKE TEST")
    print("=" * 72)
    print(f"Schema: {result['schema_version']}")
    print(f"Hazard ordinal: {priority['hazard_planning_ordinal']}/100")
    print(f"Pre-adaptation priority: {priority['pre_adaptation_priority_score']}/100")
    print(f"Operational adjustment: {priority['operational_adjustment_points']} points")
    print(f"Evidence-adjusted priority: {priority['evidence_adjusted_priority_score']}/100")
    print(f"Priority band: {priority['evidence_adjusted_priority_band']}")
    print(f"Controlled actions: {[item['action_id'] for item in result['recommendations']]}")
    print(f"New FortyGuard calls in context step: {result['provenance']['new_heatmap_jobs_for_this_request'] + result['provenance']['new_environmental_jobs_for_this_request']}")
    print(f"Medical probability supported: {result['safety']['medical_probability_supported']}")
    assert result["decision_readiness"]["planning_priority"] == "derived_supported"
    assert result["provenance"]["new_heatmap_jobs_for_this_request"] == 0
    assert result["provenance"]["new_environmental_jobs_for_this_request"] == 0
    assert result["safety"]["medical_probability_supported"] is False
    print("STATUS: PASS")


if __name__ == "__main__":
    asyncio.run(main())
