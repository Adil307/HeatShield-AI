from __future__ import annotations

from app.core.paths import backend_path
from app.services.dashboard_snapshot import build_dashboard_snapshot


def main() -> int:
    snapshot = build_dashboard_snapshot(
        day7_path=backend_path("data/processed/day7_explainability_guard.json"),
        day8_path=backend_path("data/processed/day8_controlled_recommendations.json"),
        day6_path=backend_path("data/processed/day6_site_evidence_layer.json"),
        day5_path=backend_path("data/processed/day5_planning_priority.json"),
        day44_path=backend_path("data/processed/day44_scenario_replay.json"),
        catalog_path=backend_path("config/day8_action_catalog.json"),
        raw_heatmap_path=backend_path("data/raw/official_heatmap_completed.json"),
    )
    print("HEATSHIELD - DAY 10 JUDGE-READY DASHBOARD SMOKE TEST")
    print("=" * 72)
    print("Schema:", snapshot["schema_version"])
    print("Thermal source:", snapshot["scenario"]["thermal_evidence_source"])
    print("Scenario mode:", snapshot["scenario"]["mode"])
    print("Hotspots:", snapshot["summary"]["hotspot_count"])
    print("Planning order:", snapshot["planning_order"])
    print("Highest priority rank:", snapshot["summary"]["highest_priority_rank"])
    print("Highest priority score:", snapshot["summary"]["highest_priority_score"])
    print("Heatmap features:", snapshot["summary"]["heatmap_feature_count"])
    print("New FortyGuard calls:", snapshot["provenance"]["new_fortyguard_calls_for_dashboard_snapshot"])
    print("Medical probability supported:", snapshot["safety"]["medical_probability_supported"])
    print("STATUS: PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
