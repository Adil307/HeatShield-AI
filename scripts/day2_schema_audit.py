from __future__ import annotations

import json
from pathlib import Path

from app.services.heatmap_parser import HeatmapValidationError, parse_heatmap_artifact


SOURCE = Path("data/raw/official_heatmap_completed.json")


def main() -> int:
    print("\nDAY 2 - FORTYGUARD RAW ARTIFACT AUDIT")
    print("=" * 46)

    try:
        parsed = parse_heatmap_artifact(SOURCE)
    except HeatmapValidationError as exc:
        print(f"AUDIT FAILED: {exc}")
        return 1

    print(f"Source: {parsed.source_path}")
    print(f"Provider status: {parsed.provider_status}")
    print(f"Activity ID present: {parsed.provider_activity_id is not None}")
    print(f"Feature count: {len(parsed.tiles)}")
    print(f"First tile ID: {parsed.tiles[0].tile_id}")
    print(f"First geometry type: {parsed.tiles[0].geometry.get('type')}")
    print(f"First average temperature: {parsed.tiles[0].average_temperature}")
    print("\nLocally recomputed statistics:")
    print(json.dumps(parsed.computed_stats.to_dict(), indent=2))
    print("\nProvider temperature statistics:")
    print(json.dumps(parsed.provider_stats, indent=2))
    print("\nStatistic agreement:")
    print(json.dumps(parsed.stats_match, indent=2))
    print(f"Provider standard-deviation basis: {parsed.provider_stddev_basis}")
    print("\nAUDIT COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
