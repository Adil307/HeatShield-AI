from __future__ import annotations

import sys
from pathlib import Path as _BackendPath

sys.path.insert(0, str(_BackendPath(__file__).resolve().parents[1]))

import asyncio
from pathlib import Path

from app.core.config import get_settings
from app.ai.copilot_engine import CopilotEngineError, answer_copilot


async def main() -> None:
    settings = get_settings()
    if settings.copilot_provider.lower() != "openai":
        raise SystemExit("Set COPILOT_PROVIDER=openai in .env before this opt-in live smoke test.")
    if not settings.openai_api_key_configured:
        raise SystemExit("OPENAI_API_KEY is not configured. Do not paste the key into chat or source code.")

    try:
        response = await answer_copilot(
            query="Why is the highest-priority hotspot ranked first, and what controlled actions are available?",
            settings=settings,
            day7_path=Path("data/processed/day7_explainability_guard.json"),
            day8_path=Path("data/processed/day8_controlled_recommendations.json"),
            day6_path=Path("data/processed/day6_site_evidence_layer.json"),
            day5_path=Path("data/processed/day5_planning_priority.json"),
            day44_path=Path("data/processed/day44_scenario_replay.json"),
            catalog_path=Path("config/day8_action_catalog.json"),
            mode="openai",
        )
    except CopilotEngineError as exc:
        raise SystemExit(f"LIVE COPILOT SMOKE TEST FAILED: {exc}") from exc

    print("LIVE GROUNDED COPILOT SMOKE TEST")
    print("=" * 60)
    print("Planner:", response["planner"])
    print("LLM calls:", response["runtime"]["llm_calls"])
    print("Final factual renderer:", response["safety"]["final_answer_renderer"])
    print("Guard status:", response["grounding"]["guard_status"])
    print("Answer:", response["answer"])


if __name__ == "__main__":
    asyncio.run(main())
