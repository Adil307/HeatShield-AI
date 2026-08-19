from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from app.schemas.fortyguard import HeatmapRequest
from app.services.live_context_priority import Day13ContextPriorityRequest, Day13ContextProfile
from app.services.live_decision_readiness import run_live_decision_readiness
from app.services.live_scenario_studio import (
    Day15ScenarioChanges,
    Day15ScenarioRequest,
    run_live_scenario_studio,
)
from app.services.live_thermal_analysis import live_request_hash


BACKEND = Path(__file__).resolve().parents[1]
FIXTURES = BACKEND / "tests" / "fixtures"
HEATMAP = FIXTURES / "day11_sample_heatmap_completed.json"
ENV = FIXTURES / "day12_sample_environment_completed.json"
CATALOG = BACKEND / "config" / "day8_action_catalog.json"


def analysis_request() -> HeatmapRequest:
    return HeatmapRequest.model_validate(
        {
            "polygon_aoi": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"source": "day15-smoke"},
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


def context_request() -> Day13ContextPriorityRequest:
    return Day13ContextPriorityRequest.model_validate(
        {
            "analysis_request": analysis_request().model_dump(mode="json"),
            "context_profile": {
                "source_type": "authorized_operator_input",
                "source_ref": "Day 15 smoke verified baseline operations record",
                "observed_at": "2026-08-20T04:20:00+05:00",
                "exposure_level": "high",
                "sensitive_use_context": "education_and_healthcare",
                "physical_exertion": "high",
                "acclimatization_gap": "partial",
                "heat_trapping_ppe_or_clothing": "some",
                "potable_water_access": "adequate",
                "shaded_or_cooled_recovery": "partial",
                "work_rest_controls": "adequate",
                "heat_training_and_monitoring": "partial",
            },
        }
    )


async def seed(live_dir: Path, env_dir: Path) -> None:
    req = analysis_request()
    live_dir.mkdir(parents=True, exist_ok=True)
    (live_dir / f"tcm_{live_request_hash(req)}.json").write_text(
        HEATMAP.read_text(encoding="utf-8"), encoding="utf-8"
    )
    completion = json.loads(ENV.read_text(encoding="utf-8"))

    class FixtureEnvironmentalClient:
        async def submit_environmental_parameters(self, request):
            return {"data": {"activity_id": "day15-smoke-env"}}

        async def wait_for_completion(self, activity_id):
            return completion

    await run_live_decision_readiness(
        req,
        client=FixtureEnvironmentalClient(),
        live_cache_dir=live_dir,
        env_cache_dir=env_dir,
    )


async def main() -> None:
    with tempfile.TemporaryDirectory(prefix="heatshield-day15-") as temp:
        root = Path(temp)
        live_dir, env_dir = root / "live", root / "env"
        await seed(live_dir, env_dir)
        result = await run_live_scenario_studio(
            Day15ScenarioRequest(
                context_request=context_request(),
                scenario_label="Assume exposure is one level lower",
                scenario_changes=Day15ScenarioChanges(exposure_level="moderate"),
            ),
            live_cache_dir=live_dir,
            env_cache_dir=env_dir,
            catalog_path=CATALOG,
        )

    print("HEATSHIELD - DAY 15 LIVE SCENARIO STUDIO SMOKE TEST")
    print("=" * 72)
    print(f"Schema: {result['schema_version']}")
    print(f"Baseline priority: {result['baseline']['evidence_adjusted_priority_score']:.2f}/100")
    print(f"Scenario priority: {result['scenario']['evidence_adjusted_priority_score']:.2f}/100")
    print(f"Priority delta: {result['comparison']['priority_delta_points']:+.2f} points")
    print(f"Scenario band: {result['scenario']['evidence_adjusted_priority_band']}")
    print(f"Thermal treatment: {result['scenario']['thermal_hazard_treatment']}")
    print(f"Temperature reduction estimated: {result['safety']['temperature_reduction_estimated']}")
    print(f"New FortyGuard calls: {result['safety']['provider_calls_for_scenario_step']}")
    print(f"New LLM calls: {result['safety']['llm_calls_for_scenario_step']}")
    print(f"Medical probability supported: {result['safety']['medical_probability_supported']}")

    assert result["baseline"]["evidence_adjusted_priority_score"] == 74.75
    assert result["scenario"]["evidence_adjusted_priority_score"] == 59.75
    assert result["comparison"]["priority_delta_points"] == -15.0
    assert result["scenario"]["temperature_change_celsius"] is None
    assert result["safety"]["provider_calls_for_scenario_step"] == 0
    assert result["safety"]["medical_probability_supported"] is False
    print("STATUS: PASS")


if __name__ == "__main__":
    asyncio.run(main())
