from __future__ import annotations

from pathlib import Path

from app.services.recommendation_engine import RecommendationEngineError, build_recommendations, save_recommendations


DAY7 = Path("data/processed/day7_explainability_guard.json")
DAY6 = Path("data/processed/day6_site_evidence_layer.json")
DAY5 = Path("data/processed/day5_planning_priority.json")
DAY44 = Path("data/processed/day44_scenario_replay.json")
CATALOG = Path("config/day8_action_catalog.json")
OUTPUT = Path("data/processed/day8_controlled_recommendations.json")


def main() -> int:
    try:
        payload = build_recommendations(
            day7_path=DAY7,
            catalog_path=CATALOG,
            day6_path=DAY6,
            day5_path=DAY5,
            day44_path=DAY44,
        )
        save_recommendations(payload, OUTPUT)
    except RecommendationEngineError as exc:
        print(f"DAY 8 FAILED: {exc}")
        return 1

    print("\nHEATSHIELD - DAY 8 CONTROLLED ACTION RECOMMENDATION ENGINE v1")
    print("=" * 92)
    print("Scope: deterministic scenario-planning actions; NOT medical advice and NOT LLM-generated actions")
    print(f"Day-7 source SHA-256: {payload['source']['day7_artifact_sha256']}")
    print(f"Action catalog SHA-256: {payload['source']['action_catalog_sha256']}")
    print(f"Hotspots processed: {payload['summary']['hotspots_processed']}")
    print(f"Controlled recommendations generated: {payload['summary']['recommendations_generated']}")
    print(f"Status counts: {payload['summary']['status_counts']}")
    print("New provider/API calls in Day 8: ZERO")
    print("New LLM calls in Day 8: ZERO")

    print("\nRecommendations by planning priority")
    print("-" * 92)
    for hotspot in payload["hotspots"]:
        adjusted = hotspot["evidence_adjusted_priority_score"]
        adjusted_text = "WITHHELD" if adjusted is None else f"{adjusted:.2f}"
        print(
            f"hotspot_rank={hotspot['hotspot_rank']} tile={hotspot['tile_id']} | "
            f"pre_priority={hotspot['pre_adaptation_priority_score']:.2f}/100 | adjusted={adjusted_text} | "
            f"actions={hotspot['recommendation_count']}"
        )
        for item in hotspot["recommendations"]:
            print(
                f"  {item['priority_tier']} | {item['status']:<35} | "
                f"{item['action_id']}"
            )
            print(f"       {item['recommendation']}")
            print(f"       evidence={item['recommendation_id']} guard={item['guard_status']}")

    print("\nGuardrails")
    print("-" * 92)
    print("Unknown controls trigger verification; they are never described as absent.")
    print("Historical thermal evidence is never described as current heat.")
    print("Mapped objects are never converted into people exposed.")
    print("No medical risk probability or site-specific intervention cooling effect is produced.")
    print(f"\nSaved derived artifact: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
