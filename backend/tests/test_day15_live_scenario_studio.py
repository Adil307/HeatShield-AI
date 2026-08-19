from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.schemas.fortyguard import HeatmapRequest
from app.services.live_context_priority import Day13ContextPriorityRequest, Day13ContextProfile
from app.services.live_decision_readiness import run_live_decision_readiness
from app.services.live_scenario_studio import (
    Day15ScenarioChanges,
    Day15ScenarioRequest,
    LiveScenarioStudioError,
    run_live_scenario_studio,
)
from app.services.live_thermal_analysis import live_request_hash


FIXTURES = Path(__file__).parent / "fixtures"
HEATMAP = FIXTURES / "day11_sample_heatmap_completed.json"
ENV = FIXTURES / "day12_sample_environment_completed.json"
CATALOG = Path(__file__).resolve().parents[1] / "config" / "day8_action_catalog.json"


def live_request() -> HeatmapRequest:
    return HeatmapRequest.model_validate(
        {
            "polygon_aoi": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"source": "day15-test"},
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


def context_request() -> Day13ContextPriorityRequest:
    return Day13ContextPriorityRequest(
        analysis_request=live_request(),
        context_profile=Day13ContextProfile.model_validate(
            {
                "source_type": "authorized_operator_input",
                "source_ref": "Day 15 verified baseline operations record",
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
            }
        ),
    )


async def seed_caches(live_dir: Path, env_dir: Path) -> None:
    req = live_request()
    live_dir.mkdir(parents=True, exist_ok=True)
    (live_dir / f"tcm_{live_request_hash(req)}.json").write_text(
        HEATMAP.read_text(encoding="utf-8"), encoding="utf-8"
    )
    completion = json.loads(ENV.read_text(encoding="utf-8"))

    class FixtureEnvironmentalClient:
        async def submit_environmental_parameters(self, request):
            return {"data": {"activity_id": "day15-env-fixture"}}

        async def wait_for_completion(self, activity_id):
            return completion

    await run_live_decision_readiness(
        req,
        client=FixtureEnvironmentalClient(),
        live_cache_dir=live_dir,
        env_cache_dir=env_dir,
    )


def run_scenario(tmp_path: Path, changes: dict, label: str = "Day 15 scenario") -> dict:
    live_dir, env_dir = tmp_path / "live", tmp_path / "env"
    asyncio.run(seed_caches(live_dir, env_dir))
    request = Day15ScenarioRequest(
        context_request=context_request(),
        scenario_label=label,
        scenario_changes=Day15ScenarioChanges.model_validate(changes),
    )
    return asyncio.run(
        run_live_scenario_studio(
            request,
            live_cache_dir=live_dir,
            env_cache_dir=env_dir,
            catalog_path=CATALOG,
        )
    )


def test_day15_lower_exposure_recomputes_priority_without_changing_thermal_hazard(tmp_path: Path) -> None:
    result = run_scenario(tmp_path, {"exposure_level": "moderate"}, "Assume lower exposure")
    assert result["schema_version"] == "heatshield.day15.live_scenario_studio.v1"
    assert result["baseline"]["evidence_adjusted_priority_score"] == 74.75
    assert result["scenario"]["evidence_adjusted_priority_score"] == 59.75
    assert result["comparison"]["priority_delta_points"] == -15.0
    assert result["scenario"]["evidence_adjusted_priority_band"] == "moderate_planning_priority"
    assert result["scenario"]["thermal_hazard_treatment"] == "held_constant_from_verified_day12_evidence"
    assert result["scenario"]["temperature_change_celsius"] is None


def test_day15_protection_bundle_is_assumption_not_observed_future_state(tmp_path: Path) -> None:
    result = run_scenario(
        tmp_path,
        {
            "potable_water_access": "adequate",
            "shaded_or_cooled_recovery": "adequate",
            "work_rest_controls": "adequate",
            "heat_training_and_monitoring": "adequate",
        },
        "Assume all protective controls are adequate",
    )
    assert result["scenario"]["evidence_adjusted_priority_score"] == 71.0
    assert result["comparison"]["priority_delta_points"] == -3.75
    assert all(item["classification"] == "ASSUMED" for item in result["assumptions"]["changes"])
    assert {item["field"] for item in result["assumptions"]["changes"]} == {
        "shaded_or_cooled_recovery",
        "heat_training_and_monitoring",
    }
    assert result["safety"]["measured_future_outcome"] is False


def test_day15_rejects_a_scenario_that_makes_no_effective_change(tmp_path: Path) -> None:
    live_dir, env_dir = tmp_path / "live", tmp_path / "env"
    asyncio.run(seed_caches(live_dir, env_dir))
    request = Day15ScenarioRequest(
        context_request=context_request(),
        scenario_label="No effective change",
        scenario_changes=Day15ScenarioChanges(potable_water_access="adequate"),
    )
    with pytest.raises(LiveScenarioStudioError, match="does not change"):
        asyncio.run(
            run_live_scenario_studio(
                request,
                live_cache_dir=live_dir,
                env_cache_dir=env_dir,
                catalog_path=CATALOG,
            )
        )


def test_day15_scenario_step_makes_zero_provider_and_llm_calls(tmp_path: Path) -> None:
    result = run_scenario(tmp_path, {"work_rest_controls": "partial"})
    assert result["provenance"]["new_heatmap_jobs_for_this_request"] == 0
    assert result["provenance"]["new_environmental_jobs_for_this_request"] == 0
    assert result["provenance"]["new_llm_calls_for_this_request"] == 0
    assert result["safety"]["provider_calls_for_scenario_step"] == 0
    assert result["safety"]["llm_calls_for_scenario_step"] == 0


def test_day15_never_estimates_temperature_reduction_or_medical_probability(tmp_path: Path) -> None:
    result = run_scenario(tmp_path, {"shaded_or_cooled_recovery": "adequate"})
    assert result["scenario"]["temperature_change_celsius"] is None
    assert result["assumptions"]["temperature_reduction_model_available"] is False
    assert result["assumptions"]["time_shift_supported"] is False
    assert result["safety"]["temperature_reduction_estimated"] is False
    assert result["safety"]["medical_probability_supported"] is False
    assert result["safety"]["time_shift_requires_fresh_provider_evidence"] is True


def test_day15_scenario_id_is_stable_for_same_baseline_and_assumptions(tmp_path: Path) -> None:
    first = run_scenario(tmp_path / "a", {"physical_exertion": "moderate"}, "Lower workload")
    second = run_scenario(tmp_path / "b", {"physical_exertion": "moderate"}, "Lower workload")
    assert first["scenario"]["scenario_assumption_id"] == second["scenario"]["scenario_assumption_id"]
