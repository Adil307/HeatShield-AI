from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from app.services.day5_artifact import Day5ArtifactError, load_day5_evidence_source
from app.services.site_evidence_engine import (
    MODIFIER_STRENGTHS,
    SiteEvidenceError,
    build_unknown_profile,
    load_evidence_profiles,
    modifier_sensitivity,
    score_site_evidence,
)


DAY5_PATH = Path("data/processed/day5_planning_priority.json")
EVIDENCE_PATH = Path("data/input/day6_site_evidence.json")
OUTPUT_PATH = Path("data/processed/day6_site_evidence_layer.json")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day5", type=Path, default=DAY5_PATH)
    parser.add_argument("--evidence", type=Path, default=EVIDENCE_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()

    try:
        source = load_day5_evidence_source(args.day5)
        day5_sha = _sha256(args.day5)

        if not args.evidence.exists():
            template = build_unknown_profile(source.priority_results)
            _write_json(args.evidence, template)
            template_created = True
        else:
            template_created = False

        profiles = load_evidence_profiles(args.evidence)
        scored = []
        for priority in source.priority_results:
            profile = profiles.get(priority.hotspot_rank)
            if profile is None:
                raise SiteEvidenceError(
                    f"No Day 6 evidence profile exists for hotspot_rank={priority.hotspot_rank}."
                )
            scored.append(
                score_site_evidence(
                    priority,
                    profile,
                    day5_sha256=day5_sha,
                    modifier_set="baseline_15pt",
                )
            )

        sensitivity = modifier_sensitivity(
            source.priority_results,
            profiles,
            day5_sha256=day5_sha,
        )
        all_complete = all(item.evidence_complete for item in scored)
        adjusted_results = [
            item for item in scored if item.evidence_adjusted_priority_score is not None
        ]
        adjusted_ranking = (
            [
                item.hotspot_rank
                for item in sorted(
                    adjusted_results,
                    key=lambda item: (-float(item.evidence_adjusted_priority_score), item.hotspot_rank),
                )
            ]
            if all_complete
            else None
        )

        artifact = {
            "schema_version": "heatshield.day6.evidence_layer.v1",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "scope": "verified_operational_evidence_layer_not_medical_risk",
            "source": {
                "day5_artifact_path": str(args.day5),
                "day5_artifact_sha256": day5_sha,
                "day5_source_day44_sha256": source.day44_sha256,
                "site_evidence_path": str(args.evidence),
                "site_evidence_sha256": _sha256(args.evidence),
            },
            "method": {
                "version": "hs-site-evidence-v1",
                "profile_type": "operational_worksite_v1",
                "vulnerability_factors": [
                    "physical_exertion",
                    "acclimatization_gap",
                    "heat_trapping_ppe_or_clothing",
                ],
                "adaptive_capacity_factors": [
                    "potable_water_access",
                    "shaded_or_cooled_recovery",
                    "work_rest_controls",
                    "heat_training_and_monitoring",
                ],
                "adjustment_formula": "P_adjusted = clamp(P_pre + s*V - s*A, 0, 100)",
                "baseline_modifier_strength": MODIFIER_STRENGTHS["baseline_15pt"],
                "score_policy": "adjusted planning priority only when every required factor is explicitly verified",
                "medical_risk_policy": "never produced by Day 6",
                "references": {
                    "niosh_heat_stress_recommendations": "https://www.cdc.gov/niosh/heat-stress/recommendations/index.html",
                    "niosh_heat_stress_risk_factors": "https://www.cdc.gov/niosh/heat-stress/about/",
                },
            },
            "classification": {
                "observed": "Only explicitly verified site/organization/operator evidence supplied through the Day 6 evidence profile.",
                "derived": "Evidence completeness, factor ordinals, optional evidence-adjusted planning priority, evidence IDs, and modifier sensitivity.",
                "inferred": "None. Unknown operational factors remain unknown.",
                "recommended": None,
            },
            "template_created_this_run": template_created,
            "all_required_evidence_complete": all_complete,
            "evidence_adjusted_ranking": adjusted_ranking,
            "results": [item.to_dict() for item in scored],
            "modifier_sensitivity": [item.to_dict() for item in sensitivity],
            "limitations": [
                "Day 6 is a human-in-the-loop operational evidence layer, not an automatic vulnerability inference model.",
                "Operational factor ordinals and modifier strengths are transparent prototype planning values, not validated epidemiological coefficients.",
                "Unknown or partially verified factors never default to zero and never unlock an adjusted planning score.",
                "The worksite-oriented NIOSH-aligned profile is optional and must not be applied to a general urban population without appropriate verified operational context.",
                "No medical, clinical, mortality, or individual probability-of-illness score is produced.",
            ],
        }
        _write_json(args.output, artifact)

        print("\nHEATSHIELD - DAY 6 VERIFIED EVIDENCE LAYER v1")
        print("=" * 78)
        print("Scope: human-in-the-loop operational evidence; NOT medical/clinical risk")
        print(f"Day-5 source SHA-256: {day5_sha}")
        print(f"Evidence template created this run: {template_created}")
        print(f"Evidence file: {args.evidence}")
        print(f"All required evidence complete: {all_complete}")
        print("\nEvidence readiness by hotspot")
        print("-" * 78)
        for item in scored:
            print(
                f"hotspot_rank={item.hotspot_rank} tile={item.tile_id} | "
                f"vulnerability_complete={item.vulnerability_completeness * 100:.0f}% | "
                f"adaptive_complete={item.adaptive_capacity_completeness * 100:.0f}%"
            )
            if item.evidence_adjusted_priority_score is None:
                print("  adjusted_planning_priority=WITHHELD (verified evidence incomplete)")
            else:
                print(
                    f"  vulnerability={item.vulnerability_score:.1f} | "
                    f"adaptive_capacity={item.adaptive_capacity_score:.1f} | "
                    f"adjustment={item.adjustment_points:+.2f} | "
                    f"adjusted_priority={item.evidence_adjusted_priority_score:.2f}/100"
                )
            print(f"  evidence_bundle={item.evidence_bundle_id}")

        print("\nModifier sensitivity")
        print("-" * 78)
        for item in sensitivity:
            print(f"{item.modifier_set:<20} status={item.status} ranking={item.ranking}")
        print("\nMedical risk score: NEVER PRODUCED")
        print(f"Saved derived artifact: {args.output}")
        return 0
    except (Day5ArtifactError, SiteEvidenceError, OSError, ValueError) as exc:
        print(f"DAY 6 FAILED: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
