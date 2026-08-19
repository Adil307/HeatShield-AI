from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.ai import live_copilot as module
from app.ai.live_copilot import Day14LiveCopilotRequest, answer_live_copilot
from app.core.config import Settings
from app.schemas.fortyguard import HeatmapRequest
from app.services.live_context_priority import Day13ContextPriorityRequest, Day13ContextProfile
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
                        "properties": {"source": "day14-test"},
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
            "source_type": "authorized_operator_input",
            "source_ref": "Day 14 authorized operations record",
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
        }
    )


def context_request() -> Day13ContextPriorityRequest:
    return Day13ContextPriorityRequest(
        analysis_request=live_request(),
        context_profile=context_profile(),
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
            return {"data": {"activity_id": "day14-env-fixture"}}

        async def wait_for_completion(self, activity_id):
            return completion

    await run_live_decision_readiness(
        req,
        client=FixtureEnvironmentalClient(),
        live_cache_dir=live_dir,
        env_cache_dir=env_dir,
    )


def ask(tmp_path: Path, query: str, *, mode: str = "deterministic") -> dict:
    live_dir, env_dir = tmp_path / "live", tmp_path / "env"
    asyncio.run(seed_caches(live_dir, env_dir))
    return asyncio.run(
        answer_live_copilot(
            Day14LiveCopilotRequest(query=query, mode=mode, context_request=context_request()),
            settings=Settings(copilot_provider="deterministic"),
            live_cache_dir=live_dir,
            env_cache_dir=env_dir,
            catalog_path=CATALOG,
        )
    )


def test_day14_why_priority_is_rendered_from_verified_live_evidence(tmp_path: Path) -> None:
    result = ask(tmp_path, "Why is the current live planning priority this high?")
    assert result["schema_version"] == "heatshield.day14.live_grounded_copilot.v1"
    assert result["intent"] == "why_priority"
    assert "76.00/100" in result["answer"]
    assert "74.75/100" in result["answer"]
    assert "medical-risk probability" in result["answer"]
    assert result["grounding"]["guard_status"] == "approved_live_evidence_guard"
    assert result["grounding"]["approved_claim_count"] >= 6
    assert result["runtime"]["new_fortyguard_calls"] == 0
    assert result["runtime"]["new_environmental_calls"] == 0
    assert result["safety"]["llm_writes_final_factual_answer"] is False


def test_day14_current_heat_index_lookup_is_live_not_historical(tmp_path: Path) -> None:
    result = ask(tmp_path, "What is the current heat index for this live tile?")
    assert result["intent"] == "metric_lookup"
    assert "38.2 C" in result["answer"]
    assert "current verified hottest tile" in result["answer"]
    assert result["grounding"]["claims"][0]["metric_key"] == "heat_index_celsius"


def test_day14_medical_or_people_count_request_hits_scope_boundary(tmp_path: Path) -> None:
    result = ask(tmp_path, "What is the clinical risk probability and how many workers are here?")
    assert result["intent"] == "scope_boundary"
    assert "not an individual medical-risk probability" in result["answer"]
    assert "people/occupancy count" in result["answer"]
    assert result["safety"]["medical_probability_supported"] is False
    assert result["safety"]["people_or_occupancy_inference_supported"] is False


def test_day14_recommendations_are_only_from_controlled_catalog(tmp_path: Path) -> None:
    result = ask(tmp_path, "What action should we take next?")
    assert result["intent"] == "recommendations"
    assert result["grounding"]["controlled_recommendation_ids"] == [
        "review_worker_heat_practices_if_applicable"
    ]
    assert "assistant did not invent" in result["answer"]
    assert result["safety"]["free_form_action_invention_allowed"] is False


def test_day14_evidence_answer_exposes_traceability_without_new_provider_calls(tmp_path: Path) -> None:
    result = ask(tmp_path, "Where did this number come from? Show the evidence source.")
    assert result["intent"] == "evidence"
    assert "FortyGuard thermal activity" in result["answer"]
    assert "authorized operational context source" in result["answer"]
    assert {item["kind"] for item in result["evidence_refs"]} == {"thermal", "environmental", "context"}
    assert result["runtime"]["new_fortyguard_calls"] == 0


def test_day14_comparison_keeps_full_priority_scope_bounded(tmp_path: Path) -> None:
    result = ask(tmp_path, "Compare the live hotspots and tell me which has the highest full priority.")
    assert result["intent"] == "compare_scope"
    assert "relative hottest-tile temperatures" in result["answer"]
    assert "does not rank the other live tiles by full decision priority" in result["answer"]
    assert result["safety"]["full_priority_comparison_requires_equivalent_context_per_tile"] is True


def test_day14_qwen_can_route_ambiguous_question_but_never_write_final_answer(tmp_path: Path, monkeypatch) -> None:
    live_dir, env_dir = tmp_path / "live", tmp_path / "env"
    asyncio.run(seed_caches(live_dir, env_dir))

    async def fake_qwen(**kwargs):
        assert "available_metric_keys" in kwargs["compact_context"]
        return "evidence"

    monkeypatch.setattr(module, "ollama_live_intent", fake_qwen)
    result = asyncio.run(
        answer_live_copilot(
            Day14LiveCopilotRequest(
                query="Walk me through what backs this result.",
                mode="ollama",
                context_request=context_request(),
            ),
            settings=Settings(copilot_provider="ollama", ollama_model="qwen3:1.7b"),
            live_cache_dir=live_dir,
            env_cache_dir=env_dir,
            catalog_path=CATALOG,
        )
    )
    assert result["intent"] == "evidence"
    assert result["runtime"]["llm_calls"] == 1
    assert result["runtime"]["local_inference"] is True
    assert result["grounding"]["final_answer_renderer"] == "deterministic_live_evidence_renderer"
    assert result["safety"]["llm_writes_final_factual_answer"] is False
