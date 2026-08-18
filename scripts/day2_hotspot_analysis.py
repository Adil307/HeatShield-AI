from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from app.services.evidence import sha256_file
from app.services.heatmap_parser import HeatmapValidationError, parse_heatmap_artifact
from app.services.hotspot_detector import HotspotDetectionError, detect_relative_hotspots


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a completed FortyGuard heatmap and derive deterministic "
            "AOI-relative thermal hotspot candidates."
        )
    )
    parser.add_argument(
        "--input",
        default="data/raw/official_heatmap_completed.json",
        help="Completed FortyGuard heatmap JSON artifact.",
    )
    parser.add_argument(
        "--output",
        default="data/processed/day2_hotspot_analysis.json",
        help="HeatShield derived hotspot artifact.",
    )
    parser.add_argument(
        "--top-ratio",
        type=float,
        default=0.10,
        help="Fraction of hottest tiles to retain (default: 0.10).",
    )
    parser.add_argument(
        "--max-hotspots",
        type=int,
        default=50,
        help="Safety cap on retained hotspot candidates (default: 50).",
    )
    parser.add_argument(
        "--allow-provider-stat-mismatch",
        action="store_true",
        help="Continue even if locally recomputed provider statistics disagree.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    try:
        parsed = parse_heatmap_artifact(input_path)
        source_hash = sha256_file(input_path)

        stats_consistent = bool(parsed.stats_match) and all(parsed.stats_match.values())
        if parsed.provider_stats is not None and not stats_consistent:
            if not args.allow_provider_stat_mismatch:
                mismatched = [name for name, matched in parsed.stats_match.items() if not matched]
                raise HeatmapValidationError(
                    "Provider statistics differ from local recomputation for: "
                    + ", ".join(mismatched)
                )

        analysis = detect_relative_hotspots(
            parsed.tiles,
            parsed.computed_stats,
            source_sha256=source_hash,
            top_ratio=args.top_ratio,
            max_hotspots=args.max_hotspots,
        )
    except (HeatmapValidationError, HotspotDetectionError) as exc:
        print(f"DAY 2 FAILED: {exc}")
        return 1

    artifact = {
        "schema_version": "heatshield.day2.hotspot.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "classification": {
            "observed": "FortyGuard tile temperatures and geometry",
            "derived": "HeatShield validation, statistics, ranking, z-score, relative intensity",
            "inferred": None,
            "recommended": None,
        },
        "source": {
            "provider": "FortyGuard",
            "artifact_path": str(input_path),
            "artifact_sha256": source_hash,
            "activity_id": parsed.provider_activity_id,
            "provider_status": parsed.provider_status,
        },
        "validation": {
            "tile_count": len(parsed.tiles),
            "provider_stats_available": parsed.provider_stats is not None,
            "provider_stats_match": parsed.stats_match,
            "provider_stats_consistent": stats_consistent,
            "provider_standard_deviation_basis": parsed.provider_stddev_basis,
        },
        "computed_temperature_stats": parsed.computed_stats.to_dict(),
        "provider_temperature_stats": parsed.provider_stats,
        "hotspot_analysis": analysis.to_dict(),
        "limitations": [
            "Candidates are AOI-relative thermal hotspots, not a clinical or population heat-risk score.",
            "No exposure, vulnerability, adaptive-capacity, demographic, or behavioral factors are included on Day 2.",
            "Relative bands use standardized difference within this AOI and are not universal danger thresholds.",
        ],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")

    print("\nHEATSHIELD - DAY 2 THERMAL HOTSPOT INTELLIGENCE")
    print("=" * 56)
    print(f"Source: {input_path}")
    print(f"Tiles validated: {len(parsed.tiles)}")
    print(
        "Temperature range: "
        f"{parsed.computed_stats.minimum:.4f} C -> {parsed.computed_stats.maximum:.4f} C"
    )
    print(f"Mean: {parsed.computed_stats.mean:.4f} C")
    print(f"AOI population std dev: {parsed.computed_stats.population_standard_deviation:.6f}")
    if parsed.computed_stats.sample_standard_deviation is not None:
        print(f"Sample std dev (n-1): {parsed.computed_stats.sample_standard_deviation:.6f}")
    print(f"Provider std dev basis: {parsed.provider_stddev_basis}")
    print(f"Provider statistics consistent: {stats_consistent}")
    print(f"Raw artifact SHA-256: {source_hash}")
    print(f"Hotspot method: {analysis.method}")
    print(f"Candidates retained: {analysis.selected_count}/{analysis.total_tiles}")
    print(f"Cutoff temperature: {analysis.cutoff_temperature:.4f} C")

    print("\nTop candidates")
    print("-" * 56)
    for candidate in analysis.candidates[:10]:
        print(
            f"#{candidate.rank:<2} tile={candidate.tile_id!s:<8} "
            f"temp={candidate.average_temperature:.4f} C "
            f"z={candidate.z_score:+.3f} "
            f"relative={candidate.relative_intensity:.3f} "
            f"band={candidate.relative_band}"
        )

    print(f"\nSaved derived artifact: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
