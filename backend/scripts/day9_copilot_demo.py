from __future__ import annotations

import sys
from pathlib import Path as _BackendPath

sys.path.insert(0, str(_BackendPath(__file__).resolve().parents[1]))

import asyncio
import json
from pathlib import Path

from app.core.config import get_settings
from app.ai.copilot_engine import answer_copilot


DAY44 = Path("data/processed/day44_scenario_replay.json")
DAY5 = Path("data/processed/day5_planning_priority.json")
DAY6 = Path("data/processed/day6_site_evidence_layer.json")
DAY7 = Path("data/processed/day7_explainability_guard.json")
DAY8 = Path("data/processed/day8_controlled_recommendations.json")
CATALOG = Path("config/day8_action_catalog.json")
OUTPUT = Path("data/processed/day9_copilot_demo.json")

QUESTIONS = (
    "Which hotspot has the highest planning priority and how does it compare with the others?",
    "Why does hotspot 2 have this planning priority?",
    "What actions should we consider for hotspot 2?",
    "What evidence is still missing for hotspot 2?",
    "What is the heat index for hotspot 2?",
    "What is the current heat risk percentage for hotspot 2?",
)


async def main() -> None:
    settings = get_settings()
    responses = []
    print("\nHEATSHIELD - DAY 9 GROUNDED AI COPILOT CORE v1")
    print("=" * 84)
    print("Installer demo mode: deterministic guarded planner (ZERO LLM/network calls)")
    print("LLM role when enabled: select whitelisted evidence/action IDs only; never author final facts")
    print()

    for question in QUESTIONS:
        response = await answer_copilot(
            query=question,
            settings=settings,
            day7_path=DAY7,
            day8_path=DAY8,
            day6_path=DAY6,
            day5_path=DAY5,
            day44_path=DAY44,
            catalog_path=CATALOG,
            mode="deterministic",
        )
        responses.append(response)
        print(f"Q: {question}")
        print(f"Intent: {response['plan']['intent']} | planner={response['planner']}")
        print(f"A: {response['answer']}")
        print(
            "Grounding: "
            f"claims={response['grounding']['approved_structured_claim_count']} "
            f"actions={len(response['grounding']['controlled_recommendation_ids'])} "
            f"guard={response['grounding']['guard_status']}"
        )
        print("-" * 84)

    payload = {
        "schema_version": "heatshield.day9.copilot_demo.v1",
        "policy": {
            "installer_demo_mode": "deterministic",
            "new_llm_calls": 0,
            "new_provider_calls": 0,
            "llm_writes_final_factual_answer": False,
            "live_openai_smoke_is_opt_in": True,
        },
        "responses": responses,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Saved Day 9 demo artifact: {OUTPUT}")
    print("New FortyGuard calls: ZERO | New Overpass calls: ZERO | New LLM calls: ZERO")


if __name__ == "__main__":
    asyncio.run(main())
