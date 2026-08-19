from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from app.ai.live_copilot import Day14LiveCopilotRequest, answer_live_copilot
from app.core.config import Settings
from app.schemas.fortyguard import HeatmapRequest
from app.services.live_context_priority import Day13ContextPriorityRequest, Day13ContextProfile
from app.services.live_decision_readiness import run_live_decision_readiness
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
                        "properties": {"source": "day14-smoke"},
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
                "source_ref": "Day 14 smoke authorized operations record",
                "observed_at": "2026-08-20T04:00:00+05:00",
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
            return {"data": {"activity_id": "day14-smoke-env"}}

        async def wait_for_completion(self, activity_id):
            return completion

    await run_live_decision_readiness(
        req,
        client=FixtureEnvironmentalClient(),
        live_cache_dir=live_dir,
        env_cache_dir=env_dir,
    )


async def main() -> None:
    with tempfile.TemporaryDirectory(prefix="heatshield-day14-") as temp:
        root = Path(temp)
        live_dir, env_dir = root / "live", root / "env"
        await seed(live_dir, env_dir)
        result = await answer_live_copilot(
            Day14LiveCopilotRequest(
                query="Why is the current live planning priority this high?",
                mode="deterministic",
                context_request=context_request(),
            ),
            settings=Settings(copilot_provider="deterministic"),
            live_cache_dir=live_dir,
            env_cache_dir=env_dir,
            catalog_path=CATALOG,
        )

    print("HEATSHIELD - DAY 14 LIVE GROUNDED COPILOT SMOKE TEST")
    print("=" * 72)
    print(f"Schema: {result['schema_version']}")
    print(f"Intent: {result['intent']}")
    print(f"Planner: {result['runtime']['planner']}")
    print(f"Guard: {result['grounding']['guard_status']}")
    print(f"Approved claims: {result['grounding']['approved_claim_count']}")
    print(f"Evidence refs: {len(result['evidence_refs'])}")
    print(f"New FortyGuard calls: {result['runtime']['new_fortyguard_calls']}")
    print(f"LLM writes final answer: {result['safety']['llm_writes_final_factual_answer']}")
    print(f"Answer: {result['answer']}")
    assert result["intent"] == "why_priority"
    assert "74.75/100" in result["answer"]
    assert result["runtime"]["new_fortyguard_calls"] == 0
    assert result["safety"]["llm_writes_final_factual_answer"] is False
    assert result["safety"]["medical_probability_supported"] is False
    print("STATUS: PASS")


if __name__ == "__main__":
    asyncio.run(main())
