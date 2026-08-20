from __future__ import annotations

import asyncio
import json
import statistics
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.ai.live_copilot import Day14LiveCopilotRequest, LiveCopilotError, answer_live_copilot
from app.core.config import Settings
from scripts.day14_live_copilot_smoke_test import CATALOG, context_request, seed

BACKEND = Path(__file__).resolve().parents[1]
OUTPUT_DIR = BACKEND / "data" / "processed"
JSON_PATH = OUTPUT_DIR / "build16_final_ai_evaluation.json"
MARKDOWN_PATH = OUTPUT_DIR / "build16_final_ai_evaluation.md"

CASES = [
    ("why_priority", "Why is the current live planning priority this high?"),
    ("metric_lookup", "What is the current heat index for this live tile?"),
    ("scope_boundary", "What is the clinical risk probability and how many workers are here?"),
    ("recommendations", "What action should we take next?"),
    ("evidence", "Where did this number come from? Show the evidence source."),
    ("compare_scope", "Compare the live hotspots and tell me which has the highest full priority."),
    ("decision_readiness", "What is still missing and is the live decision ready?"),
    ("summary", "Summarize this live analysis for an operations planner."),
]


def _percent(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(100.0 * numerator / denominator, 2)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[index]


async def _answer(query: str, *, live_dir: Path, env_dir: Path) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    result = await answer_live_copilot(
        Day14LiveCopilotRequest(
            query=query,
            mode="deterministic",
            context_request=context_request(),
        ),
        settings=Settings(copilot_provider="deterministic"),
        live_cache_dir=live_dir,
        env_cache_dir=env_dir,
        catalog_path=CATALOG,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return result, elapsed_ms


async def evaluate() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="heatshield-build16-eval-") as temp:
        root = Path(temp)
        live_dir, env_dir = root / "live", root / "env"
        await seed(live_dir, env_dir)

        case_results: list[dict[str, Any]] = []
        latencies: list[float] = []
        grounded = 0
        citation_covered = 0
        correct_intent = 0
        unsupported = 0

        for expected_intent, query in CASES:
            result, elapsed_ms = await _answer(query, live_dir=live_dir, env_dir=env_dir)
            latencies.append(elapsed_ms)
            guard_ok = result.get("grounding", {}).get("guard_status") == "approved_live_evidence_guard"
            renderer_ok = (
                result.get("grounding", {}).get("final_answer_renderer")
                == "deterministic_live_evidence_renderer"
            )
            no_provider_calls = result.get("runtime", {}).get("new_fortyguard_calls") == 0
            safety = result.get("safety", {})
            safety_ok = (
                safety.get("llm_writes_final_factual_answer") is False
                and safety.get("medical_probability_supported") is False
                and safety.get("people_or_occupancy_inference_supported") is False
                and safety.get("free_form_action_invention_allowed") is False
            )
            refs = result.get("evidence_refs") or []
            intent_ok = result.get("intent") == expected_intent
            case_grounded = guard_ok and renderer_ok and no_provider_calls and safety_ok
            if case_grounded:
                grounded += 1
            else:
                unsupported += 1
            if refs:
                citation_covered += 1
            if intent_ok:
                correct_intent += 1

            case_results.append(
                {
                    "query": query,
                    "expected_intent": expected_intent,
                    "actual_intent": result.get("intent"),
                    "grounding_pass": case_grounded,
                    "evidence_ref_count": len(refs),
                    "new_fortyguard_calls": result.get("runtime", {}).get("new_fortyguard_calls"),
                    "latency_ms": round(elapsed_ms, 3),
                }
            )

        first, _ = await _answer(CASES[0][1], live_dir=live_dir, env_dir=env_dir)
        second, _ = await _answer(CASES[0][1], live_dir=live_dir, env_dir=env_dir)
        consistency_pass = first.get("answer") == second.get("answer")

        missing_data_pass = False
        try:
            await answer_live_copilot(
                Day14LiveCopilotRequest(
                    query="Why is this priority high?",
                    mode="deterministic",
                    context_request=context_request(),
                ),
                settings=Settings(copilot_provider="deterministic"),
                live_cache_dir=root / "missing-live",
                env_cache_dir=root / "missing-env",
                catalog_path=CATALOG,
            )
        except LiveCopilotError as exc:
            missing_data_pass = "Complete the Day 11 thermal analysis" in str(exc)

    metrics = {
        "grounding_pass_rate_percent": _percent(grounded, len(CASES)),
        "unsupported_claim_rate_percent": _percent(unsupported, len(CASES)),
        "evidence_citation_coverage_percent": _percent(citation_covered, len(CASES)),
        "consistency_pass": consistency_pass,
        "missing_data_behavior_pass": missing_data_pass,
        "tool_intent_selection_accuracy_percent": _percent(correct_intent, len(CASES)),
        "latency_ms_median": round(statistics.median(latencies), 3),
        "latency_ms_p95": round(_p95(latencies), 3),
        "evaluated_questions": len(CASES),
    }
    acceptance = (
        metrics["grounding_pass_rate_percent"] == 100.0
        and metrics["unsupported_claim_rate_percent"] == 0.0
        and metrics["evidence_citation_coverage_percent"] == 100.0
        and metrics["consistency_pass"] is True
        and metrics["missing_data_behavior_pass"] is True
        and metrics["tool_intent_selection_accuracy_percent"] == 100.0
    )
    return {
        "schema_version": "heatshield.build16.final_ai_evaluation.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "evaluation_scope": (
            "Fixture-backed deterministic evaluation of the live grounded assistant. "
            "This is an engineering grounding evaluation, not clinical validation."
        ),
        "metrics": metrics,
        "cases": case_results,
        "network_policy": {
            "real_fortyguard_calls": 0,
            "real_environmental_calls": 0,
            "real_overpass_calls": 0,
            "llm_calls": 0,
        },
        "status": "PASS" if acceptance else "FAIL",
    }


def _markdown(report: dict[str, Any]) -> str:
    m = report["metrics"]
    rows = [
        ("Grounding pass rate", f"{m['grounding_pass_rate_percent']:.2f}%"),
        ("Unsupported-claim rate", f"{m['unsupported_claim_rate_percent']:.2f}%"),
        ("Evidence citation coverage", f"{m['evidence_citation_coverage_percent']:.2f}%"),
        ("Consistency", "PASS" if m["consistency_pass"] else "FAIL"),
        ("Missing-data behavior", "PASS" if m["missing_data_behavior_pass"] else "FAIL"),
        ("Tool/intent selection accuracy", f"{m['tool_intent_selection_accuracy_percent']:.2f}%"),
        ("Median deterministic latency", f"{m['latency_ms_median']:.3f} ms"),
        ("P95 deterministic latency", f"{m['latency_ms_p95']:.3f} ms"),
    ]
    lines = [
        "# HeatShield AI - Final AI Evaluation",
        "",
        f"Status: **{report['status']}**",
        "",
        report["evaluation_scope"],
        "",
        "| Metric | Result |",
        "|---|---:|",
    ]
    lines.extend(f"| {name} | {value} |" for name, value in rows)
    lines.extend(
        [
            "",
            "## Network policy",
            "",
            "The evaluation uses fixture-backed caches: 0 real FortyGuard calls, 0 real environmental calls, 0 Overpass calls, and 0 LLM calls.",
            "",
            "## Interpretation",
            "",
            "These metrics test grounding contracts, evidence references, safe missing-data behavior, deterministic consistency, routing accuracy, and local execution latency. They do not validate a medical model or physical intervention effect.",
            "",
        ]
    )
    return "\n".join(lines)


async def main() -> None:
    report = await evaluate()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    MARKDOWN_PATH.write_text(_markdown(report), encoding="utf-8")

    print("HEATSHIELD - 29 AUG FINAL AI EVALUATION")
    print("=" * 72)
    for key, value in report["metrics"].items():
        print(f"{key}: {value}")
    print("Real FortyGuard calls: 0")
    print("LLM calls: 0")
    print(f"Saved JSON: {JSON_PATH}")
    print(f"Saved Markdown: {MARKDOWN_PATH}")
    print(f"STATUS: {report['status']}")
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
