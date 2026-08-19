from __future__ import annotations

import sys
from pathlib import Path as _BackendPath

sys.path.insert(0, str(_BackendPath(__file__).resolve().parents[1]))

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
    build_context_query_bundle,
    build_hotspot_contexts,
    merge_context_places,
    parse_overpass_context,
    query_bundle_fingerprint,
    raw_cache_fingerprint,
)
from app.services.context_taxonomy import CATEGORY_ORDER
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
        help="Ignore valid local OSM response caches and query Overpass again.",
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Fail unless every context category was successfully observed from Overpass.",
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


def _safe_error(exc: Exception) -> str:
    text = str(exc).strip()
    return text[:700] if text else exc.__class__.__name__


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
        plans, bbox = build_context_query_bundle(
            selected,
            radius_meters=args.radius_meters,
            snapshot_utc=snapshot_utc,
        )
        bundle_sha = query_bundle_fingerprint(plans)

        client = OverpassClient(get_settings())
        place_groups = []
        group_records: dict[str, dict[str, Any]] = {}
        osm_bases: list[str] = []
        total_http_requests = 0
        total_semantic_rejections = 0
        total_cache_hits = 0
        attempted_endpoints: list[str] = []

        print(
            f"[submit] historical OSM context snapshot={snapshot_utc.isoformat()} "
            f"hotspots={len(selected)} radius={args.radius_meters:.0f}m"
        )
        print(f"[strategy] {len(plans)} small category queries; sequential endpoint failover")

        for plan in plans:
            cache_key = raw_cache_fingerprint(query_sha256=plan.query_sha256)
            cache_path = raw_dir / f"osm_context_{plan.category}_{cache_key[:16]}.json"
            wrapper: dict[str, Any] = {}
            cache_hit = False

            if cache_path.exists() and not args.force_refresh:
                candidate = _read_json(cache_path)
                if (
                    candidate.get("query_sha256") == plan.query_sha256
                    and isinstance(candidate.get("response"), dict)
                ):
                    try:
                        places, osm_base = parse_overpass_context(candidate)
                    except ContextValidationError as exc:
                        print(f"[cache-invalid] {plan.category}: {exc}; refreshing")
                    else:
                        cache_hit = True
                        total_cache_hits += 1
                        place_groups.append(places)
                        if osm_base:
                            osm_bases.append(osm_base)
                        group_records[plan.category] = {
                            "status": "observed",
                            "cache_hit": True,
                            "query_sha256": plan.query_sha256,
                            "endpoint": candidate.get("endpoint"),
                            "objects_fetched": len(places),
                            "http_requests": 0,
                            "semantic_rejections": 0,
                            "attempted_endpoints": [],
                        }
                        print(f"[cache] {plan.category:<16} objects={len(places)}")

            if cache_hit:
                continue

            try:
                result = await client.query(plan.query)
            except OverpassError as exc:
                group_records[plan.category] = {
                    "status": "unavailable_provider_failure",
                    "cache_hit": False,
                    "query_sha256": plan.query_sha256,
                    "endpoint": None,
                    "objects_fetched": None,
                    "http_requests": len(client.endpoints),
                    "semantic_rejections": None,
                    "attempted_endpoints": list(client.endpoints),
                    "error": _safe_error(exc),
                }
                total_http_requests += len(client.endpoints)
                for endpoint in client.endpoints:
                    if endpoint not in attempted_endpoints:
                        attempted_endpoints.append(endpoint)
                print(f"[unavailable] {plan.category:<16} {_safe_error(exc)}")
                continue

            total_http_requests += result.request_count
            total_semantic_rejections += result.semantic_rejections
            for endpoint in result.attempted_endpoints:
                if endpoint not in attempted_endpoints:
                    attempted_endpoints.append(endpoint)

            wrapper = {
                "provider": "OpenStreetMap Overpass API",
                "endpoint": result.endpoint,
                "category": plan.category,
                "query_sha256": plan.query_sha256,
                "query_snapshot_utc": snapshot_utc.isoformat(),
                "attribution": ATTRIBUTION,
                "license": "ODbL 1.0",
                "request_count": result.request_count,
                "semantic_rejections": result.semantic_rejections,
                "attempted_endpoints": list(result.attempted_endpoints),
                "response_semantically_valid": True,
                "response": result.response,
            }
            # Only semantically valid responses reach this point and may be cached.
            _write_json(cache_path, wrapper)
            places, osm_base = parse_overpass_context(wrapper)
            place_groups.append(places)
            if osm_base:
                osm_bases.append(osm_base)
            group_records[plan.category] = {
                "status": "observed",
                "cache_hit": False,
                "query_sha256": plan.query_sha256,
                "endpoint": result.endpoint,
                "objects_fetched": len(places),
                "http_requests": result.request_count,
                "semantic_rejections": result.semantic_rejections,
                "attempted_endpoints": list(result.attempted_endpoints),
            }
            print(
                f"[ok] {plan.category:<16} objects={len(places):<4} "
                f"endpoint={result.endpoint}"
            )

        observed_categories = tuple(
            category for category in CATEGORY_ORDER
            if group_records.get(category, {}).get("status") == "observed"
        )
        unavailable_categories = tuple(
            category for category in CATEGORY_ORDER if category not in observed_categories
        )

        if not observed_categories:
            raise OverpassError(
                "All historical context category queries failed across all configured Overpass endpoints. "
                "No zero-context artifact was produced."
            )
        if args.require_complete and unavailable_categories:
            raise OverpassError(
                "Historical context coverage is partial; unavailable categories: "
                + ", ".join(unavailable_categories)
            )

        places = merge_context_places(place_groups)
        category_status = {
            category: (
                "observed" if category in observed_categories else "unavailable_provider_failure"
            )
            for category in CATEGORY_ORDER
        }
        contexts = build_hotspot_contexts(
            hotspots=selected,
            places=places,
            radius_meters=args.radius_meters,
            day3_sha256=day3_sha,
            query_sha256=bundle_sha,
            category_status=category_status,
        )

    except (Day3ArtifactError, ContextValidationError, OverpassError, ValueError) as exc:
        print(f"DAY 4 FAILED: {exc}")
        if isinstance(exc, OverpassError) and exc.response_body:
            print("Provider response:")
            print(exc.response_body)
        return 1

    unique_assigned_refs = {
        item.place.osm_ref for context in contexts for item in context.nearby_places
    }
    coverage_status = "complete" if not unavailable_categories else "partial"

    artifact = {
        "schema_version": "heatshield.day4.context.v1.2",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "classification": {
            "observed": (
                "OpenStreetMap objects and tags returned by successful historical Overpass category queries; "
                "Day-3 coordinates and evidence identifiers"
            ),
            "derived": (
                "HeatShield context taxonomy, query bounding box, exact geodesic distances, "
                "category counts, category availability states, spatial assignments and evidence linkage"
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
                "attribution": ATTRIBUTION,
                "license": "ODbL 1.0",
                "license_url": ODBL_URL,
                "requested_snapshot_utc": snapshot_utc.isoformat(),
                "snapshot_basis": snapshot_basis,
                "osm_base_values": sorted(set(osm_bases)),
                "query_bundle_sha256": bundle_sha,
                "category_queries": {
                    plan.category: plan.query_sha256 for plan in plans
                },
            },
        },
        "execution": {
            "hotspots_analyzed": len(contexts),
            "radius_meters": args.radius_meters,
            "query_strategy": "historical_bbox_split_by_context_category_then_local_spatial_assignment_v2",
            "category_query_count": len(plans),
            "coverage_status": coverage_status,
            "observed_categories": list(observed_categories),
            "unavailable_categories": list(unavailable_categories),
            "category_query_results": group_records,
            "overpass_http_requests_this_run": total_http_requests,
            "overpass_semantic_rejections_this_run": total_semantic_rejections,
            "attempted_endpoints": attempted_endpoints,
            "cache_hits": total_cache_hits,
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
            "categories": list(CATEGORY_ORDER),
            "absence_semantics": (
                "A zero count is interpretable only when that category status is observed. "
                "Unavailable categories are unknown, not zero and not evidence of absence."
            ),
            "no_population_inference": True,
            "no_occupancy_inference": True,
            "no_vulnerability_inference": True,
        },
        "hotspot_contexts": [item.to_dict() for item in contexts],
        "limitations": [
            "Day 4 identifies mapped exposure-context candidates; it does not estimate people exposed, occupancy, vulnerability or health risk.",
            "OpenStreetMap completeness and tagging quality vary by place and historical date; absence of a mapped object is not evidence of real-world absence.",
            "HTTP 200 responses containing a non-empty Overpass remark are provider failures, not valid zero-context evidence.",
            "Provider/network failure is represented per category as unavailable_provider_failure; such categories must not be interpreted as zero exposure context.",
            "Ways and relations use the Overpass center for proximity calculations; that center is a representative point and may not lie inside the mapped geometry.",
            "Historical alignment uses the provider observation timestamp when available.",
            "Context categories are deterministic engineering taxonomy labels, not epidemiological weights.",
            "OpenStreetMap attribution and ODbL license information must remain visible wherever these context data are presented.",
        ],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\nHEATSHIELD - DAY 4 EXPOSURE CONTEXT INTELLIGENCE v1.2")
    print("=" * 72)
    print(f"Day-3 artifact SHA-256: {day3_sha}")
    print(f"Historical OSM snapshot: {snapshot_utc.isoformat()} ({snapshot_basis})")
    print(f"Hotspots analyzed: {len(contexts)}")
    print(f"Context radius: {args.radius_meters:.0f} m")
    print(f"Coverage status: {coverage_status}")
    print("Observed categories: " + ", ".join(observed_categories))
    if unavailable_categories:
        print("Unavailable categories: " + ", ".join(unavailable_categories))
    print(f"Relevant OSM objects fetched: {len(places)}")
    print(f"Unique assigned context places: {len(unique_assigned_refs)}")
    print(f"Overpass HTTP requests this run: {total_http_requests}")
    print(f"Semantic error responses rejected: {total_semantic_rejections}")
    print(f"Cache hits: {total_cache_hits}")
    if attempted_endpoints:
        print("Attempted endpoints: " + ", ".join(attempted_endpoints))
    print(f"Attribution: {ATTRIBUTION} | ODbL 1.0")

    for context in contexts:
        print("\n" + "-" * 72)
        print(f"Rank #{context.hotspot_rank} | tile={context.tile_id}")
        print(f"Context evidence: {context.context_evidence_id}")
        print("Category counts: " + json.dumps(context.category_counts, sort_keys=True))
        print("Category status: " + json.dumps(context.category_status, sort_keys=True))
        nearest = context.nearby_places[:5]
        if not nearest:
            print("Nearest mapped context: none observed among successfully queried categories")
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
