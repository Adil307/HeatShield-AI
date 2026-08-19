from __future__ import annotations

import asyncio
import json
import time

from app.ai.copilot_engine import CopilotEngineError, answer_copilot
from app.core.config import get_settings
from app.core.paths import backend_path


async def main() -> None:
    settings = get_settings()

    started = time.perf_counter()
    try:
        response = await answer_copilot(
            query="Why is hotspot 2 high priority?",
            settings=settings,
            day7_path=backend_path("data/processed/day7_explainability_guard.json"),
            day8_path=backend_path("data/processed/day8_controlled_recommendations.json"),
            day6_path=backend_path("data/processed/day6_site_evidence_layer.json"),
            day5_path=backend_path("data/processed/day5_planning_priority.json"),
            day44_path=backend_path("data/processed/day44_scenario_replay.json"),
            catalog_path=backend_path("config/day8_action_catalog.json"),
            mode="ollama",
        )
    except CopilotEngineError as exc:
        raise SystemExit(f"LOCAL QWEN COPILOT SMOKE TEST FAILED: {exc}") from exc

    elapsed = time.perf_counter() - started
    print("HEATSHIELD - DAY 9.1.3 MONOREPO LOCAL QWEN SMOKE TEST")
    print("=" * 72)
    print("Planner:", response["planner"])
    print("Model:", settings.ollama_model)
    print("Ollama base URL:", settings.ollama_base_url)
    print("Local LLM calls:", response["runtime"]["llm_calls"])
    print("Local inference:", response["runtime"]["local_inference"])
    print("Final factual renderer:", response["safety"]["final_answer_renderer"])
    print("Guard status:", response["grounding"]["guard_status"])
    print("New FortyGuard calls:", response["runtime"]["new_fortyguard_calls"])
    print("Elapsed seconds:", round(elapsed, 3))
    print("Route corrections:", response["runtime"].get("local_route_corrections"))
    print("Materialized plan:", json.dumps(response["plan"], indent=2))
    print("Answer:", response["answer"])

    output = backend_path("data/processed/day9_1_3_local_qwen_smoke.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(response, indent=2), encoding="utf-8")
    print("Saved local smoke artifact:", output)


if __name__ == "__main__":
    asyncio.run(main())
