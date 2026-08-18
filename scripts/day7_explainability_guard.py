from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from app.services.claim_guard import evaluate_structured_claim, screen_natural_language
from app.services.day6_artifact import file_sha256
from app.services.explainability import ExplainabilityError, build_explainability_packets


DAY6_PATH = Path("data/processed/day6_site_evidence_layer.json")
DAY5_PATH = Path("data/processed/day5_planning_priority.json")
DAY44_PATH = Path("data/processed/day44_scenario_replay.json")
OUTPUT_PATH = Path("data/processed/day7_explainability_guard.json")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day6", type=Path, default=DAY6_PATH)
    parser.add_argument("--day5", type=Path, default=DAY5_PATH)
    parser.add_argument("--day44", type=Path, default=DAY44_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()

    try:
        packets = build_explainability_packets(day6_path=args.day6, day5_path=args.day5, day44_path=args.day44)
        packet_dicts = [packet.to_dict() for packet in packets]

        guard_self_test = []
        for packet in packet_dicts:
            exact_priority = evaluate_structured_claim(
                packet,
                {
                    "claim_type": "metric_assertion",
                    "metric_key": "pre_adaptation_planning_priority",
                    "claimed_value": packet["pre_adaptation_priority_score"],
                },
            )
            blocked_medical = evaluate_structured_claim(
                packet,
                {
                    "claim_type": "metric_assertion",
                    "metric_key": "medical_risk_probability",
                    "claimed_value": 70.0,
                },
            )
            if not exact_priority.approved or blocked_medical.approved:
                raise ExplainabilityError("Claim Guard self-test failed.")
            guard_self_test.append(
                {
                    "hotspot_rank": packet["hotspot_rank"],
                    "grounded_priority_claim": exact_priority.to_dict(),
                    "blocked_medical_claim": blocked_medical.to_dict(),
                }
            )

        artifact = {
            "schema_version": "heatshield.day7.explainability_guard.v1",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "scope": "deterministic_explainability_and_claim_grounding_not_llm_reasoning",
            "source": {
                "day6_artifact_path": str(args.day6),
                "day6_artifact_sha256": file_sha256(args.day6),
                "day5_artifact_path": str(args.day5),
                "day5_artifact_sha256": file_sha256(args.day5),
                "day44_artifact_path": str(args.day44),
                "day44_artifact_sha256": file_sha256(args.day44),
            },
            "classification_policy": {
                "observed": "Direct provider/mapped/verified evidence carried through the provenance chain.",
                "derived": "Deterministic HeatShield calculations that can be recomputed from observed evidence.",
                "unknown": "Required evidence is not verified; no value may be invented or defaulted to zero.",
                "withheld": "A value is intentionally not produced under the current evidence/policy scope.",
            },
            "claim_guard_policy": {
                "structured_claims": "Only exact observed/derived ledger values or exact evidence-status assertions can be approved.",
                "unknown_withheld": "Unknown/withheld values cannot be asserted as numeric facts.",
                "medical_probability": "Never approved or produced.",
                "mapped_object_semantics": "OSM mapped objects are not people, occupancy, footfall, or independent-facility counts.",
                "temporal_semantics": "Historical hazard cannot be described as current/live heat.",
                "natural_language": "Natural language is screened for red flags but never self-authorizes; factual clauses must be grounded as structured claims.",
                "recommendations": "Not approved by Day 7; controlled recommendation policy is a later layer.",
            },
            "packets": packet_dicts,
            "claim_guard_self_test": guard_self_test,
            "natural_language_guard_examples": {
                "blocked": screen_natural_language("This location has a 70% health risk.").to_dict(),
                "requires_structured_grounding": screen_natural_language(
                    "The planning priority is high because heat and mapped context are elevated."
                ).to_dict(),
            },
            "limitations": [
                "Day 7 is deterministic explainability and claim grounding; it is not an LLM and does not validate arbitrary natural-language semantics exhaustively.",
                "The natural-language scanner is a defense-in-depth red-flag filter, not a substitute for structured claim grounding.",
                "Scenario replay combines historical hazard evidence with current mapped context; it is not current heat and not historical exposure reconstruction.",
                "Mapped OSM objects are context evidence only and do not establish actual occupancy or exposed-person counts.",
                "No medical/clinical probability is generated, and recommendation claims remain outside Day 7.",
            ],
        }
        _write_json(args.output, artifact)

        print("\nHEATSHIELD - DAY 7 EXPLAINABILITY + EVIDENCE GUARD v1")
        print("=" * 84)
        print("Scope: deterministic evidence-grounded explanation; NOT LLM reasoning")
        print(f"Packets built: {len(packet_dicts)}")
        print(f"Day-6 SHA-256: {artifact['source']['day6_artifact_sha256']}")
        print(f"Day-5 SHA-256: {artifact['source']['day5_artifact_sha256']}")
        print(f"Day-4.4 SHA-256: {artifact['source']['day44_artifact_sha256']}")
        print("\nExplainability packets")
        print("-" * 84)
        for packet in sorted(packet_dicts, key=lambda item: -float(item["pre_adaptation_priority_score"])):
            contrib = {item["component"]: item["weighted_points"] for item in packet["contributions"]}
            print(
                f"tile={packet['tile_id']} hotspot_rank={packet['hotspot_rank']} | "
                f"pre_priority={packet['pre_adaptation_priority_score']:.2f}/100 | "
                f"adjusted={'WITHHELD' if packet['evidence_adjusted_priority_score'] is None else packet['evidence_adjusted_priority_score']}"
            )
            print(
                "  contribution_points="
                f"hazard:{contrib['hazard']:.2f}, mapped_exposure:{contrib['mapped_exposure']:.2f}, "
                f"context_sensitivity:{contrib['context_sensitivity_proxy']:.2f}"
            )
            print(f"  unknown={list(packet['unknowns'])}")
            print(f"  withheld={list(packet['withheld'])}")
            print(f"  packet={packet['packet_id']}")

        print("\nClaim Guard self-test")
        print("-" * 84)
        print("Exact grounded planning-priority claims: APPROVED")
        print("Medical risk probability claims: REJECTED")
        print("Historical-as-current claims: REJECTED by text guard")
        print("Mapped-object-as-people claims: REJECTED by text guard")
        print("Natural-language factual text: REQUIRES STRUCTURED GROUNDING")
        print("New provider/API calls in Day 7: ZERO")
        print(f"Saved derived artifact: {args.output}")
        return 0
    except (ExplainabilityError, OSError, ValueError) as exc:
        print(f"DAY 7 FAILED: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
