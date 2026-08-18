from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.providers.openstreetmap import OverpassClient, OverpassError
from app.services.context_intelligence import (
    ContextValidationError,
    build_hotspot_contexts,
    merge_context_places,
    parse_overpass_context,
)
from app.services.context_taxonomy import CATEGORY_ORDER
from app.services.evidence import sha256_file
from app.services.operational_baseline import cache_is_fresh
from app.services.scenario_replay import (
    ScenarioReplayError,
    build_current_context_query_bundle,
    coverage_status,
    load_scenario_replay_source,
    scenario_query_bundle_sha256,
    temporal_gap_days,
)


ATTRIBUTION = "© OpenStreetMap contributors"
ODBL_URL = "https://www.openstreetmap.org/copyright"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Replay the verified historical FortyGuard thermal event against current mapped OSM context. "
            "This is a planning scenario, not a claim of current heat conditions."
        )
    )
    parser.add_argument("--day3-artifact", default="data/processed/day3_environmental_enrichment.json")
    parser.add_argument("--hotspot-limit", type=int, default=3)
    parser.add_argument("--radius-meters", type=float, default=500.0)
    parser.add_argument("--raw-dir", default="data/raw/day44")
    parser.add_argument("--output", default="data/processed/day44_scenario_replay.json")
    parser.add_argument("--osm-cache-ttl-minutes", type=float, default=60.0)
    parser.add_argument("--force-refresh", action="store_true")
    return parser


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _safe_error(exc: Exception) -> str:
    return str(exc).replace("\n", " ").strip()[:700]


async def run(args: argparse.Namespace) -> int:
    if not 1 <= args.hotspot_limit <= 10:
        print("DAY 4.4 FAILED: --hotspot-limit must be between 1 and 10.")
        return 1
    if not 100 <= args.radius_meters <= 2_000:
        print("DAY 4.4 FAILED: --radius-meters must be between 100 and 2000.")
        return 1

    generated_at = datetime.now(timezone.utc)
    raw_dir = Path(args.raw_dir)
    output = Path(args.output)

    try:
        source = load_scenario_replay_source(args.day3_artifact, hotspot_limit=args.hotspot_limit)
        heatmap_path = Path(source.heatmap_artifact_path)
        if not heatmap_path.exists():
            raise ScenarioReplayError(f"Verified heatmap artifact not found: {heatmap_path}")
        actual_heatmap_sha = sha256_file(heatmap_path)
        if actual_heatmap_sha != source.heatmap_artifact_sha256:
            raise ScenarioReplayError(
                "Day 3 provenance mismatch: verified heatmap artifact SHA-256 changed."
            )

        context_inputs = tuple(item.context_input for item in source.hotspots)
        plans, bbox = build_current_context_query_bundle(
            context_inputs,
            radius_meters=args.radius_meters,
        )
        bundle_sha = scenario_query_bundle_sha256(plans)
        settings = get_settings()
        client = OverpassClient(settings)

        category_status: dict[str, str] = {}
        category_meta: dict[str, Any] = {}
        place_groups = []
        total_http_requests = 0
        semantic_rejections = 0
        cache_hits = 0
        attempted_endpoints: set[str] = set()
        osm_base_values: list[str] = []

        print(
            "[strategy] scenario replay: verified historical hazard + current OSM context; "
            "5 small category queries, no new FortyGuard heatmap calls"
        )

        for plan in plans:
            cache = raw_dir / f"osm_current_{plan.category}_{plan.query_sha256[:16]}.json"
            wrapper = None
            cache_hit = False
            if not args.force_refresh and cache_is_fresh(
                cache,
                ttl_minutes=args.osm_cache_ttl_minutes,
                now_utc=generated_at,
            ):
                try:
                    candidate = json.loads(cache.read_text(encoding="utf-8"))
                    parse_overpass_context(candidate)
                    wrapper = candidate
                    cache_hit = True
                except (OSError, json.JSONDecodeError, ContextValidationError):
                    wrapper = None

            if wrapper is None:
                try:
                    result = await client.query(plan.query)
                except OverpassError as exc:
                    category_status[plan.category] = "unavailable_provider_failure"
                    category_meta[plan.category] = {
                        "status": "unavailable_provider_failure",
                        "query_sha256": plan.query_sha256,
                        "cache_hit": False,
                        "error": _safe_error(exc),
                    }
                    print(f"[unavailable] {plan.category:<17} {_safe_error(exc)}")
                    continue

                total_http_requests += result.request_count
                semantic_rejections += result.semantic_rejections
                attempted_endpoints.update(result.attempted_endpoints)
                wrapper = {
                    "provider": "OpenStreetMap Overpass API",
                    "endpoint": result.endpoint,
                    "category": plan.category,
                    "query_sha256": plan.query_sha256,
                    "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
                    "mode": "current_context_for_scenario_replay",
                    "attribution": ATTRIBUTION,
                    "license": "ODbL 1.0",
                    "response_semantically_valid": True,
                    "response": result.response,
                }
                _write_json(cache, wrapper)
            else:
                cache_hits += 1

            places, osm_base = parse_overpass_context(wrapper)
            place_groups.append(places)
            if osm_base:
                osm_base_values.append(osm_base)
            category_status[plan.category] = "observed"
            category_meta[plan.category] = {
                "status": "observed",
                "query_sha256": plan.query_sha256,
                "cache_hit": cache_hit,
                "objects": len(places),
                "endpoint": wrapper.get("endpoint"),
            }
            print(
                f"[ok] {plan.category:<17} objects={len(places):<4} "
                f"cache_hit={cache_hit} endpoint={wrapper.get('endpoint')}"
            )

        status = coverage_status(category_status)
        if status == "unavailable":
            raise ScenarioReplayError(
                "Current mapped context is unavailable across all categories; scenario replay cannot be evidenced."
            )

        places = merge_context_places(place_groups)
        day3_sha = sha256_file(args.day3_artifact)
        contexts = build_hotspot_contexts(
            hotspots=context_inputs,
            places=places,
            radius_meters=args.radius_meters,
            day3_sha256=day3_sha,
            query_sha256=bundle_sha,
            category_status=category_status,
        )
        context_by_rank = {item.hotspot_rank: item for item in contexts}

        hotspots = []
        for hazard in source.hotspots:
            context = context_by_rank[hazard.context_input.rank]
            hotspots.append(
                {
                    "hotspot_rank": hazard.context_input.rank,
                    "tile_id": hazard.context_input.tile_id,
                    "thermal_evidence_id": hazard.context_input.thermal_evidence_id,
                    "environmental_evidence_id": hazard.context_input.environmental_evidence_id,
                    "context_evidence_id": context.context_evidence_id,
                    "historical_hazard": {
                        "observed_timestamp": hazard.context_input.observed_timestamp,
                        "temperature_celsius": hazard.temperature_celsius,
                        "heat_index_celsius": hazard.heat_index_celsius,
                        "apparent_temperature_celsius": hazard.apparent_temperature_celsius,
                        "wet_bulb_temperature_celsius": hazard.wet_bulb_temperature_celsius,
                        "relative_humidity_percent": hazard.relative_humidity_percent,
                    },
                    "current_context": {
                        "representative_latitude": hazard.context_input.latitude,
                        "representative_longitude": hazard.context_input.longitude,
                        "radius_meters": args.radius_meters,
                        "category_counts": context.category_counts,
                        "category_status": context.category_status,
                        "nearby_place_count": len(context.nearby_places),
                        "nearest_context_places": [item.to_dict() for item in context.nearby_places[:10]],
                    },
                }
            )

        context_timestamp = generated_at.isoformat()
        gap_days = temporal_gap_days(
            hazard_timestamp=source.hazard_timestamp,
            context_timestamp_utc=context_timestamp,
        )

        artifact = {
            "schema_version": "heatshield.day4_4.scenario_replay.v1",
            "generated_at_utc": context_timestamp,
            "mode": "historical_hazard_current_context_scenario_replay",
            "scenario_statement": (
                "Planning replay: if the verified historical FortyGuard thermal event recurred, "
                "which currently mapped urban contexts would fall near the same thermal hotspots?"
            ),
            "classification": {
                "observed_historical": "FortyGuard heatmap and environmental measurements from the verified Day 1-3 event",
                "observed_current": "Current OpenStreetMap mapped context fetched for scenario planning",
                "derived": "HeatShield provenance verification, spatial assignment, distances, category coverage and cross-time scenario overlay",
                "inferred": None,
                "recommended": None,
            },
            "provenance": {
                "day3_artifact_path": str(args.day3_artifact),
                "day3_artifact_sha256": day3_sha,
                "heatmap_artifact_path": source.heatmap_artifact_path,
                "heatmap_artifact_sha256": actual_heatmap_sha,
                "hazard_observed_timestamp_utc": source.hazard_timestamp,
                "current_context_fetched_at_utc": context_timestamp,
                "temporal_gap_days": gap_days,
                "new_fortyguard_heatmap_submissions": 0,
            },
            "context": {
                "provider": "OpenStreetMap via Overpass API",
                "attribution": ATTRIBUTION,
                "license": "ODbL 1.0",
                "license_url": ODBL_URL,
                "query_mode": "current_data_split_category_queries",
                "query_bundle_sha256": bundle_sha,
                "bbox": {
                    "south": bbox.south,
                    "west": bbox.west,
                    "north": bbox.north,
                    "east": bbox.east,
                },
                "radius_meters": args.radius_meters,
                "coverage_status": status,
                "category_status": category_status,
                "category_execution": category_meta,
                "objects_fetched_unique": len(places),
                "http_requests_this_run": total_http_requests,
                "semantic_rejections_this_run": semantic_rejections,
                "cache_hits": cache_hits,
                "attempted_endpoints": sorted(attempted_endpoints),
                "osm_base_timestamps": sorted(set(osm_base_values)),
            },
            "hotspots": hotspots,
            "limitations": [
                "This is a deliberate scenario replay, not a live heat map and not a claim about current temperature.",
                "Historical thermal/environmental observations and current mapped context come from different dates; the temporal gap is explicit and must remain visible in the UI.",
                "Mapped place presence does not establish occupancy, population, individual vulnerability, or clinical risk.",
                "A category marked unavailable_provider_failure is unknown, never zero.",
                "The replay provides decision-support context for a repeated heat pattern; it is not historical exposure reconstruction.",
                "Vulnerability, adaptive capacity, intervention effectiveness and final prioritization remain later-stage components.",
            ],
        }

        _write_json(output, artifact)

    except (ScenarioReplayError, ContextValidationError, OverpassError, ValueError) as exc:
        print(f"DAY 4.4 FAILED: {_safe_error(exc)}")
        return 1

    print("\nHEATSHIELD - DAY 4.4 SCENARIO REPLAY BASELINE")
    print("=" * 76)
    print("Mode: verified historical hazard + current mapped context")
    print(f"Historical hazard timestamp: {source.hazard_timestamp}")
    print(f"Current context fetched at: {context_timestamp}")
    print(f"Temporal gap: {gap_days:.3f} days (explicit scenario mismatch)")
    print("New FortyGuard heatmap submissions: 0")
    print(f"Context coverage: {status}")
    print(f"Unique current OSM objects: {len(places)}")
    print(f"OSM HTTP requests this run: {total_http_requests} | cache_hits={cache_hits}")
    print(f"Semantic errors rejected: {semantic_rejections}")
    print(f"Category status: {json.dumps(category_status, sort_keys=True)}")

    for item in hotspots:
        print("\n" + "-" * 76)
        print(f"Rank #{item['hotspot_rank']} | tile={item['tile_id']}")
        hz = item["historical_hazard"]
        ctx = item["current_context"]
        print(
            f"Historical thermal evidence: air={hz['temperature_celsius']} C | "
            f"heat_index={hz['heat_index_celsius']} | apparent={hz['apparent_temperature_celsius']} | "
            f"wet_bulb={hz['wet_bulb_temperature_celsius']}"
        )
        print(f"Current mapped contexts within {args.radius_meters:.0f} m: {ctx['nearby_place_count']}")
        print(f"Category counts: {json.dumps(ctx['category_counts'], sort_keys=True)}")
        for nearby in ctx["nearest_context_places"][:5]:
            place = nearby["place"]
            print(
                f"   {nearby['distance_meters']:.2f} m | {place['category']:<16} | "
                f"{place.get('name') or place['subcategory']} | {place['osm_ref']}"
            )

    print(f"\nSaved scenario replay artifact: {output}")
    return 0


def main() -> int:
    return asyncio.run(run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
