from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from app.ai.live_copilot import Day14LiveCopilotRequest, answer_live_copilot
from app.core.config import get_settings
from app.schemas.fortyguard import HeatmapRequest
from app.services.live_context_priority import Day13ContextPriorityRequest
from app.services.live_decision_readiness import run_live_decision_readiness
from app.services.live_thermal_analysis import live_request_hash


BACKEND = Path(__file__).resolve().parents[1]
FIXTURES = BACKEND / "tests" / "fixtures"
HEATMAP = FIXTURES / "day11_sample_heatmap_completed.json"
ENV = FIXTURES / "day12_sample_environment_completed.json"
CATALOG = BACKEND / "config" / "day8_action_catalog.json"


def context_request() -> Day13ContextPriorityRequest:
    return Day13ContextPriorityRequest.model_validate(
        {
            "analysis_request": {
                "polygon_aoi": {
                    "type": "FeatureCollection",
                    "features": [{
                        "type": "Feature",
                        "properties": {"source": "day14-qwen-smoke"},
                        "geometry": {"type": "Polygon", "coordinates": [[
                            [-74.0, 40.70], [-73.998, 40.70], [-73.998, 40.702],
                            [-74.0, 40.702], [-74.0, 40.70]
                        ]]},
                    }],
                },
                "date_time": {"start_date": "2026-08-19", "filter_type": 1, "start_time": "18:00"},
                "granularity": 100,
                "analytic_type": "tcm",
            },
            "context_profile": {
                "source_type": "authorized_operator_input",
                "source_ref": "Day 14 Qwen smoke authorized operations record",
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


async def main() -> None:
    ctx = context_request()
    req: HeatmapRequest = ctx.analysis_request
    completion = json.loads(ENV.read_text(encoding="utf-8"))

    class FixtureEnvironmentalClient:
        async def submit_environmental_parameters(self, request):
            return {"data": {"activity_id": "day14-qwen-smoke-env"}}

        async def wait_for_completion(self, activity_id):
            return completion

    with tempfile.TemporaryDirectory(prefix="heatshield-day14-qwen-") as temp:
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
        result = await answer_live_copilot(
            Day14LiveCopilotRequest(
                query="Walk me through what backs this result.",
                mode="ollama",
                context_request=ctx,
            ),
            settings=get_settings(),
            live_cache_dir=live_dir,
            env_cache_dir=env_dir,
            catalog_path=CATALOG,
        )

    print("HEATSHIELD - DAY 14 LOCAL QWEN LIVE ROUTER SMOKE TEST")
    print("=" * 72)
    print(f"Planner: {result['runtime']['planner']}")
    print(f"Intent: {result['intent']}")
    print(f"Local inference: {result['runtime']['local_inference']}")
    print(f"LLM calls: {result['runtime']['llm_calls']}")
    print(f"Final renderer: {result['grounding']['final_answer_renderer']}")
    print(f"New FortyGuard calls: {result['runtime']['new_fortyguard_calls']}")
    print(f"Answer: {result['answer']}")
    assert result["runtime"]["local_inference"] is True
    assert result["runtime"]["llm_calls"] == 1
    assert result["grounding"]["final_answer_renderer"] == "deterministic_live_evidence_renderer"
    assert result["runtime"]["new_fortyguard_calls"] == 0
    print("STATUS: PASS")


if __name__ == "__main__":
    asyncio.run(main())
