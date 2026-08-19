from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.fortyguard import HeatmapRequest
from app.services.live_context_priority import (
    Day13ContextPriorityRequest,
    Day13ContextProfile,
    LiveContextPriorityError,
    run_live_context_priority,
)
from app.services.live_decision_readiness import run_live_decision_readiness
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
                        "properties": {"source": "day13-test"},
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


def context_profile() -> Day13ContextProfile:
    return Day13ContextProfile.model_validate(
        {
            "profile_type": "operational_worksite_v1",
            "source_type": "authorized_operator_input",
            "source_ref": "Shift supervisor briefing HS-13",
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


def seed_live_cache(directory: Path, request: HeatmapRequest) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"tcm_{live_request_hash(request)}.json").write_text(
        HEATMAP.read_text(encoding="utf-8"), encoding="utf-8"
    )


async def seed_day12_environment(live_dir: Path, env_dir: Path, request: HeatmapRequest) -> dict:
    completion = json.loads(ENV.read_text(encoding="utf-8"))

    class FakeEnvironmentalClient:
        async def submit_environmental_parameters(self, request):
            return {"data": {"activity_id": "day13-env-fixture-activity"}}

        async def wait_for_completion(self, activity_id):
            assert activity_id == "day13-env-fixture-activity"
            return completion

    return await run_live_decision_readiness(
        request,
        client=FakeEnvironmentalClient(),
        live_cache_dir=live_dir,
        env_cache_dir=env_dir,
    )


def test_day13_context_requires_auditable_aware_source() -> None:
    raw = context_profile().model_dump()
    raw["source_ref"] = " "
    with pytest.raises(ValidationError):
        Day13ContextProfile.model_validate(raw)

    raw = context_profile().model_dump()
    raw["observed_at"] = "2026-08-20T03:40:00"
    with pytest.raises(ValidationError, match="timezone"):
        Day13ContextProfile.model_validate(raw)


def test_day13_refuses_to_create_environmental_job_when_day12_cache_is_missing(tmp_path: Path) -> None:
    request = live_request()
    live_dir = tmp_path / "live"
    seed_live_cache(live_dir, request)
    payload = Day13ContextPriorityRequest(analysis_request=request, context_profile=context_profile())

    with pytest.raises(LiveContextPriorityError, match="Enrich the hottest tile first"):
        asyncio.run(
            run_live_context_priority(
                payload,
                live_cache_dir=live_dir,
                env_cache_dir=tmp_path / "env",
                catalog_path=CATALOG,
            )
        )


def test_day13_calculates_evidence_adjusted_priority_from_verified_context(tmp_path: Path) -> None:
    request = live_request()
    live_dir, env_dir = tmp_path / "live", tmp_path / "env"
    seed_live_cache(live_dir, request)
    asyncio.run(seed_day12_environment(live_dir, env_dir, request))

    result = asyncio.run(
        run_live_context_priority(
            Day13ContextPriorityRequest(analysis_request=request, context_profile=context_profile()),
            live_cache_dir=live_dir,
            env_cache_dir=env_dir,
            catalog_path=CATALOG,
        )
    )

    assert result["schema_version"] == "heatshield.day13.live_context_priority.v1"
    assert result["priority"]["hazard_planning_ordinal"] == 60.0
    assert result["verified_context"]["verified_exposure_score"] == 100.0
    assert result["verified_context"]["verified_sensitive_use_proxy"] == 100.0
    assert result["verified_context"]["verified_operational_vulnerability_score"] == pytest.approx(66.6667)
    assert result["verified_context"]["verified_adaptive_capacity_score"] == 75.0
    assert result["priority"]["pre_adaptation_priority_score"] == 76.0
    assert result["priority"]["operational_adjustment_points"] == pytest.approx(-1.25, abs=1e-4)
    assert result["priority"]["evidence_adjusted_priority_score"] == pytest.approx(74.75, abs=1e-4)
    assert result["priority"]["evidence_adjusted_priority_band"] == "high_planning_priority"
    assert result["decision_readiness"]["planning_priority"] == "derived_supported"
    assert result["decision_readiness"]["medical_risk_probability"] == "not_supported"


def test_day13_uses_only_controlled_catalog_action_when_trigger_is_met(tmp_path: Path) -> None:
    request = live_request()
    live_dir, env_dir = tmp_path / "live", tmp_path / "env"
    seed_live_cache(live_dir, request)
    asyncio.run(seed_day12_environment(live_dir, env_dir, request))
    result = asyncio.run(
        run_live_context_priority(
            Day13ContextPriorityRequest(analysis_request=request, context_profile=context_profile()),
            live_cache_dir=live_dir,
            env_cache_dir=env_dir,
            catalog_path=CATALOG,
        )
    )
    assert [item["action_id"] for item in result["recommendations"]] == [
        "review_worker_heat_practices_if_applicable"
    ]
    assert result["recommendations"][0]["guard_status"] == "approved_day8_catalog_action"
    assert result["recommendation_policy"]["llm_generated_actions"] is False


def test_day13_context_step_has_zero_provider_and_llm_calls(tmp_path: Path) -> None:
    request = live_request()
    live_dir, env_dir = tmp_path / "live", tmp_path / "env"
    seed_live_cache(live_dir, request)
    asyncio.run(seed_day12_environment(live_dir, env_dir, request))
    result = asyncio.run(
        run_live_context_priority(
            Day13ContextPriorityRequest(analysis_request=request, context_profile=context_profile()),
            live_cache_dir=live_dir,
            env_cache_dir=env_dir,
            catalog_path=CATALOG,
        )
    )
    assert result["provenance"]["environmental_cache_hit"] is True
    assert result["provenance"]["new_heatmap_jobs_for_this_request"] == 0
    assert result["provenance"]["new_environmental_jobs_for_this_request"] == 0
    assert result["provenance"]["new_llm_calls_for_this_request"] == 0
    assert result["safety"]["medical_probability_supported"] is False
    assert result["safety"]["individual_medical_vulnerability_inferred"] is False
