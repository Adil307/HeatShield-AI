from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.providers.openstreetmap import OverpassClient, OverpassError
from app.services.context_intelligence import (
    ContextValidationError,
    build_context_query,
    build_hotspot_contexts,
    parse_overpass_context,
    query_fingerprint,
    raw_cache_fingerprint,
)
from app.services.day3_artifact import Day3ArtifactError, load_day3_artifact, resolve_osm_snapshot_utc
from app.services.evidence import sha256_file


ATTRIBUTION = "© OpenStreetMap contributors"
ODBL_URL = "https://www.openstreetmap.org/copyright"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Enrich Day-3 thermal/environmental evidence with time-aligned OpenStreetMap "
            "context candidates without inferring occupancy, vulnerability or risk."
        )
    )
    parser.add_argument(
        "--input",
        default="data/processed/day3_environmental_enrichment.json",
        help="Day-3 environmental artifact.",
    )
    parser.add_argument(
        "--output",
        default="data/processed/day4_exposure_context.json",
        help="Derived Day-4 context artifact.",
    )
    parser.add_argument(
        "--raw-dir",
        default="data/raw/day4",
        help="Local ignored cache for raw Overpass responses.",
    )
    parser.add_argument("--limit", type=int, default=3, help="Number of Day-3 hotspots to analyze.")
    parser.add_argument(
        "--radius-meters",
        type=float,
        default=500.0,
        help="Context search radius around each hotspot (100-2000m).",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Ignore a valid local OSM response cache and query Overpass again.",
    )
    return parser


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContextValidationError(f"Invalid cached OSM JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ContextValidationError("Cached OSM payload is not an object.")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


async def run(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    output_path = Path(args.output)
    raw_dir = Path(args.raw_dir)

    if args.limit < 1 or args.limit > 15:
        print("DAY 4 FAILED: --limit must be between 1 and 15.")
        return 1

    try:
        day3 = load_day3_artifact(input_path)
        day3_sha = sha256_file(input_path)

        heatmap_path = Path(day3.heatmap_artifact_path)
        if not heatmap_path.exists():
            raise Day3ArtifactError(
                f"Day-3 source heatmap no longer exists locally: {heatmap_path}"
            )
        if sha256_file(heatmap_path) != day3.heatmap_artifact_sha256:
            raise Day3ArtifactError(
                "Day-3 provenance verification failed: source heatmap SHA-256 changed."
            )

        selected = day3.hotspots[: min(args.limit, len(day3.hotspots))]
        snapshot_utc, snapshot_basis = resolve_osm_snapshot_utc(day3)
        query, bbox = build_context_query(
            selected,
            radius_meters=args.radius_meters,
            snapshot_utc=snapshot_utc,
        )
        query_sha = query_fingerprint(query)
        cache_key = raw_cache_fingerprint(query_sha256=query_sha)
        cache_path = raw_dir / f"osm_context_{cache_key[:16]}.json"

        cache_hit = False
        provider_endpoint: str | None = None
        if cache_path.exists() and not args.force_refresh:
            wrapper = _read_json(cache_path)
            if wrapper.get("query_sha256") == query_sha and isinstance(wrapper.get("response"), dict):
                parse_overpass_context(wrapper)
                cache_hit = True
                provider_endpoint = wrapper.get("endpoint") if isinstance(wrapper.get("endpoint"), str) else None
            else:
                wrapper = {}
        else:
            wrapper = {}

        if not cache_hit:
            print(
                f"[submit] historical OSM context snapshot={snapshot_utc.isoformat()} "
                f"hotspots={len(selected)} radius={args.radius_meters:.0f}m"
            )
            result = await OverpassClient(get_settings()).query(query)
            provider_endpoint = result.endpoint
            wrapper = {
                "provider": "OpenStreetMap Overpass API",
                "endpoint": result.endpoint,
                "query_sha256": query_sha,
                "query_snapshot_utc": snapshot_utc.isoformat(),
                "attribution": ATTRIBUTION,
                "license": "ODbL 1.0",
                "response": result.response,
            }
            _write_json(cache_path, wrapper)
        else:
            print(f"[cache] using {cache_path}")

        places, osm_base = parse_overpass_context(wrapper)
        contexts = build_hotspot_contexts(
            hotspots=selected,
            places=places,
            radius_meters=args.radius_meters,
            day3_sha256=day3_sha,
            query_sha256=query_sha,
        )

    except (Day3ArtifactError, ContextValidationError, OverpassError, ValueError) as exc:
        print(f"DAY 4 FAILED: {exc}")
        if isinstance(exc, OverpassError) and exc.response_body:
            print("Provider response:")
            print(exc.response_body)
        return 1

    unique_assigned_refs = {
        item.place.osm_ref
        for context in contexts
        for item in context.nearby_places
    }

    artifact = {
        "schema_version": "heatshield.day4.context.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "classification": {
            "observed": (
                "OpenStreetMap objects and tags returned by a historical Overpass snapshot; "
                "Day-3 coordinates and evidence identifiers"
            ),
            "derived": (
                "HeatShield context taxonomy, query bounding box, exact geodesic distances, "
                "category counts, spatial assignments and evidence linkage"
            ),
            "inferred": None,
            "recommended": None,
        },
        "source": {
            "day3_artifact_path": str(input_path),
            "day3_artifact_sha256": day3_sha,
            "heatmap_artifact_path": day3.heatmap_artifact_path,
            "heatmap_artifact_sha256": day3.heatmap_artifact_sha256,
            "openstreetmap": {
                "provider": "OpenStreetMap via Overpass API",
                "endpoint": provider_endpoint,
                "attribution": ATTRIBUTION,
                "license": "ODbL 1.0",
                "license_url": ODBL_URL,
                "requested_snapshot_utc": snapshot_utc.isoformat(),
                "snapshot_basis": snapshot_basis,
                "osm_base": osm_base,
                "query_sha256": query_sha,
            },
        },
        "execution": {
            "hotspots_analyzed": len(contexts),
            "radius_meters": args.radius_meters,
            "overpass_queries_this_run": 0 if cache_hit else 1,
            "cache_hits": 1 if cache_hit else 0,
            "query_strategy": "single_historical_bbox_query_then_local_spatial_assignment",
            "bbox": {
                "south": bbox.south,
                "west": bbox.west,
                "north": bbox.north,
                "east": bbox.east,
            },
            "relevant_osm_objects_fetched": len(places),
            "unique_context_places_within_any_hotspot_radius": len(unique_assigned_refs),
        },
        "context_policy": {
            "semantic_label": "exposure_context_candidates",
            "categories": [
                "healthcare",
                "education",
                "transit_waiting",
                "outdoor_public",
                "civic_public",
            ],
            "absence_semantics": (
                "No mapped result is treated as unknown/not-observed, not proof that a facility or activity is absent."
            ),
            "no_population_inference": True,
            "no_occupancy_inference": True,
            "no_vulnerability_inference": True,
        },
        "hotspot_contexts": [item.to_dict() for item in contexts],
        "limitations": [
            "Day 4 identifies mapped exposure-context candidates; it does not estimate people exposed, occupancy, vulnerability or health risk.",
            "OpenStreetMap completeness and tagging quality vary by place and historical date; absence of a mapped object is not evidence of real-world absence.",
            "Ways and relations use the Overpass bounding-box center for proximity calculations; that center is a representative point and may not lie inside the mapped geometry.",
            "Historical alignment uses the provider observation timestamp when available; otherwise the Day-3 source date/time is treated as UTC and explicitly labeled as such.",
            "Context categories are deterministic engineering taxonomy labels, not epidemiological weights.",
            "OpenStreetMap attribution and ODbL license information must remain visible wherever these context data are presented to users or judges.",
        ],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\nHEATSHIELD - DAY 4 EXPOSURE CONTEXT INTELLIGENCE")
    print("=" * 66)
    print(f"Day-3 artifact SHA-256: {day3_sha}")
    print(f"Historical OSM snapshot: {snapshot_utc.isoformat()} ({snapshot_basis})")
    print(f"Hotspots analyzed: {len(contexts)}")
    print(f"Context radius: {args.radius_meters:.0f} m")
    print(f"Relevant OSM objects fetched: {len(places)}")
    print(f"Unique assigned context places: {len(unique_assigned_refs)}")
    print(f"Overpass queries this run: {0 if cache_hit else 1}")
    print(f"Cache hits: {1 if cache_hit else 0}")
    print(f"Attribution: {ATTRIBUTION} | ODbL 1.0")

    for context in contexts:
        print("\n" + "-" * 66)
        print(f"Rank #{context.hotspot_rank} | tile={context.tile_id}")
        print(f"Context evidence: {context.context_evidence_id}")
        print("Category counts: " + json.dumps(context.category_counts, sort_keys=True))
        nearest = context.nearby_places[:5]
        if not nearest:
            print("Nearest mapped context: none observed within radius")
        else:
            print("Nearest mapped context candidates:")
            for item in nearest:
                label = item.place.name or item.place.subcategory
                print(
                    f"  {item.distance_meters:7.2f} m | {item.place.category:<16} | "
                    f"{label} | {item.place.osm_ref}"
                )

    print(f"\nSaved derived artifact: {output_path}")
    return 0


def main() -> int:
    return asyncio.run(run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
