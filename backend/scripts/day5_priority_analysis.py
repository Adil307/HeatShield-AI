from __future__ import annotations

import sys
from pathlib import Path as _BackendPath

sys.path.insert(0, str(_BackendPath(__file__).resolve().parents[1]))

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from app.services.day44_artifact import Day44ArtifactError, load_day44_priority_source
from app.services.evidence import sha256_file
from app.services.priority_engine import (
    NIOSH_HEAT_STRESS_REFERENCE_URL,
    NWS_HEAT_INDEX_REFERENCE_URL,
    PriorityEngineError,
    WEIGHT_SETS,
    ranking_stability,
    score_hotspot,
    sensitivity_analysis,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build HeatShield Day 5 planning-priority intelligence.")
    parser.add_argument("--source", default="data/processed/day44_scenario_replay.json")
    parser.add_argument("--output", default="data/processed/day5_planning_priority.json")
    args = parser.parse_args()

    source_path = Path(args.source)
    output_path = Path(args.output)

    try:
        source = load_day44_priority_source(source_path)
        day44_sha = sha256_file(source_path)

        scored = [
            score_hotspot(item, day44_sha256=day44_sha, weight_set="baseline_v1")
            for item in source.hotspots
        ]
        scored.sort(key=lambda item: (-item.pre_adaptation_priority_score, item.hotspot_rank))

        sensitivity = sensitivity_analysis(source.hotspots)
        stability = ranking_stability(sensitivity)

        artifact = {
            "schema_version": "heatshield.day5.planning_priority.v1",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "scope": "scenario_planning_priority_not_medical_risk",
            "source": {
                "day44_artifact_path": str(source_path),
                "day44_artifact_sha256": day44_sha,
                "scenario_mode": source.mode,
                "scenario_statement": source.scenario_statement,
                "historical_hazard_timestamp_utc": source.hazard_timestamp_utc,
                "current_context_timestamp_utc": source.context_timestamp_utc,
                "temporal_gap_days": source.temporal_gap_days,
                "context_coverage_status": source.context_coverage_status,
            },
            "method": {
                "version": "hs-priority-v1",
                "baseline_weights": {
                    "hazard": WEIGHT_SETS["baseline_v1"][0],
                    "mapped_exposure": WEIGHT_SETS["baseline_v1"][1],
                    "context_sensitivity_proxy": WEIGHT_SETS["baseline_v1"][2],
                },
                "hazard_method": "NWS heat-index category -> HeatShield ordinal planning score",
                "mapped_exposure_method": "equal-category mean of log-saturated OSM counts; saturation count=20",
                "context_sensitivity_method": "binary healthcare/education place-type presence proxy",
                "vulnerability_method": "withheld unless directly observed/verified",
                "adaptive_capacity_method": "withheld unless directly observed/verified",
                "final_risk_score_policy": "withhold final score while vulnerability/adaptive-capacity evidence is missing",
                "references": {
                    "nws_heat_index": NWS_HEAT_INDEX_REFERENCE_URL,
                    "niosh_heat_stress": NIOSH_HEAT_STRESS_REFERENCE_URL,
                },
            },
            "classification": {
                "observed": "FortyGuard historical thermal/environmental evidence plus complete current OSM mapped context from Day 4.4",
                "derived": "HeatShield hazard ordinal, mapped-exposure proxy, context-sensitivity proxy, priority ranking, evidence IDs and weight sensitivity analysis",
                "inferred": "No individual vulnerability or adaptive capacity is inferred",
                "recommended": None,
            },
            "priority_results": [item.to_dict() for item in scored],
            "weight_sensitivity": {
                "tests": [item.to_dict() for item in sensitivity],
                "ranking_stability": stability,
            },
            "limitations": [
                "This is a scenario-planning prioritization index, not a medical, epidemiological, or individual risk probability.",
                "The NWS heat-index category is used only to anchor a transparent hazard ordinal; HeatShield's 0-100 ordinal is not an NWS score.",
                "Mapped OSM object counts are exposure-context proxies, not population, occupancy, footfall, or independent-facility counts.",
                "Healthcare/education presence is a place-type sensitivity proxy and must not be interpreted as observed individual vulnerability.",
                "Verified vulnerability and adaptive-capacity evidence are unavailable; therefore final adjusted risk is intentionally withheld.",
                "The scenario combines a verified historical hazard with current mapped context and explicitly preserves the temporal mismatch.",
            ],
        }
        _write_json(output_path, artifact)

        print("\nHEATSHIELD - DAY 5 PLANNING PRIORITY ENGINE v1")
        print("=" * 78)
        print("Scope: scenario planning priority; NOT medical/clinical risk")
        print(f"Day-4.4 source SHA-256: {day44_sha}")
        print(f"Scenario temporal gap: {source.temporal_gap_days:.3f} days")
        print(f"Mapped context coverage: {source.context_coverage_status}")
        print("Final risk score policy: WITHHELD until verified vulnerability/adaptive capacity exists")
        print("\nRanked pre-adaptation planning priorities")
        print("-" * 78)
        for result in scored:
            c = result.components
            print(
                f"Priority #{result.hotspot_rank} | tile={result.tile_id} | "
                f"score={result.pre_adaptation_priority_score:.2f}/100 | {result.pre_adaptation_priority_band}"
            )
            print(
                f"  hazard={c.hazard_score:.1f} ({result.heat_index_band}) | "
                f"mapped_exposure={c.mapped_exposure_score:.2f} | "
                f"sensitivity_proxy={c.context_sensitivity_proxy:.1f}"
            )
            print("  vulnerability=UNKNOWN | adaptive_capacity=UNKNOWN | final_risk_score=WITHHELD")
            print(f"  evidence={result.priority_evidence_id}")

        print("\nWeight sensitivity")
        print("-" * 78)
        for item in sensitivity:
            print(f"{item.weight_set:<16} ranking={list(item.ranking)} scores={item.scores_by_rank}")
        print(f"Rank stable across tested weight sets: {stability['stable_across_weight_sets']}")
        print(f"\nSaved derived artifact: {output_path}")
        return 0
    except (Day44ArtifactError, PriorityEngineError, OSError, ValueError) as exc:
        print(f"DAY 5 FAILED: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
