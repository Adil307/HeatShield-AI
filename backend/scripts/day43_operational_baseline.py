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
from app.providers.fortyguard import FortyGuardClient, FortyGuardError
from app.providers.openstreetmap import OverpassClient, OverpassError
from app.schemas.fortyguard import (
    DateTimeConfig,
    EnvironmentalDateTimeConfig,
    EnvironmentalParametersRequest,
    GeoJSONFeature,
    Geometry,
    HeatmapRequest,
    PolygonAOI,
)
from app.services.context_intelligence import (
    ContextValidationError,
    build_hotspot_contexts,
    parse_overpass_context,
)
from app.services.context_taxonomy import CATEGORY_ORDER
from app.services.day3_artifact import Day3ContextInput
from app.services.environmental_enrichment import build_environmental_enrichment
from app.services.environmental_parser import (
    EnvironmentalValidationError,
    parse_environmental_artifact,
)
from app.services.evidence import sha256_file
from app.services.geometry import GeometryError, representative_point
from app.services.heatmap_parser import HeatmapValidationError, parse_heatmap_artifact
from app.services.hotspot_detector import HotspotDetectionError, detect_relative_hotspots
from app.services.operational_baseline import (
    OperationalBaselineError,
    cache_is_fresh,
    canonical_sha256,
    inspect_heatmap_cache,
    recent_completed_empty_heatmap,
    resolve_operational_request_candidates,
    verify_observation_wall_clock_alignment,
)
from app.services.operational_context import build_current_context_query


NYC_DEMO_RING = [
    [-74.0170, 40.7050],
    [-74.0030, 40.7050],
    [-74.0030, 40.7180],
    [-74.0170, 40.7180],
    [-74.0170, 40.7050],
]

ATTRIBUTION = "© OpenStreetMap contributors"
ODBL_URL = "https://www.openstreetmap.org/copyright"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a near-current HeatShield operational evidence baseline: current FortyGuard "
            "heatmap, deterministic hotspots, environmental thermal context, and current OSM context."
        )
    )
    parser.add_argument("--timezone", default="America/New_York")
    parser.add_argument("--lag-hours", type=int, default=1)
    parser.add_argument("--fallback-lag-hours", type=int, default=24)
    parser.add_argument("--max-new-heatmap-submissions", type=int, default=2)
    parser.add_argument("--empty-backoff-minutes", type=float, default=180.0)
    parser.add_argument("--hotspot-limit", type=int, default=3)
    parser.add_argument("--radius-meters", type=float, default=500.0)
    parser.add_argument("--raw-dir", default="data/raw/day43")
    parser.add_argument("--output", default="data/processed/day43_operational_baseline.json")
    parser.add_argument("--osm-cache-ttl-minutes", type=float, default=30.0)
    parser.add_argument("--force-refresh", action="store_true")
    return parser


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _activity_id(response: dict[str, Any], *, operation: str) -> str:
    data = response.get("data")
    activity_id = data.get("activity_id") if isinstance(data, dict) else None
    if not isinstance(activity_id, str) or not activity_id:
        raise FortyGuardError(
            f"FortyGuard {operation} submission returned no activity_id.",
            response_body=response,
        )
    return activity_id


def _heatmap_request(*, start_date: str, start_time: str) -> HeatmapRequest:
    return HeatmapRequest(
        polygon_aoi=PolygonAOI(
            features=[
                GeoJSONFeature(
                    geometry=Geometry(coordinates=[[list(point) for point in NYC_DEMO_RING]])
                )
            ]
        ),
        date_time=DateTimeConfig(
            start_date=start_date,
            start_time=start_time,
            filter_type=1,
        ),
        granularity=100,
        analytic_type="tcm",
    )


def _safe_error(exc: Exception) -> str:
    text = str(exc).replace("\n", " ").strip()
    return text[:500]


async def run(args: argparse.Namespace) -> int:
    if not 1 <= args.hotspot_limit <= 10:
        print("DAY 4.3 FAILED: --hotspot-limit must be between 1 and 10.")
        return 1
    if not 100 <= args.radius_meters <= 2_000:
        print("DAY 4.3 FAILED: --radius-meters must be between 100 and 2000.")
        return 1

    now_utc = datetime.now(timezone.utc)
    raw_dir = Path(args.raw_dir)
    output_path = Path(args.output)

    try:
        request_candidates = resolve_operational_request_candidates(
            now_utc=now_utc,
            timezone_name=args.timezone,
            primary_lag_hours=args.lag_hours,
            fallback_lag_hours=args.fallback_lag_hours,
        )
        if not 1 <= args.max_new_heatmap_submissions <= 4:
            raise OperationalBaselineError("--max-new-heatmap-submissions must be between 1 and 4.")
        if args.empty_backoff_minutes < 0:
            raise OperationalBaselineError("--empty-backoff-minutes cannot be negative.")

        settings = get_settings()
        fg_client: FortyGuardClient | None = None

        # ------------------------------------------------------------
        # Stage 1: availability-safe operational heatmap selection
        # ------------------------------------------------------------
        recent_empty = None if args.force_refresh else recent_completed_empty_heatmap(
            raw_dir,
            now_utc=now_utc,
            window_minutes=args.empty_backoff_minutes,
        )
        if recent_empty is not None:
            print(
                f"[backoff] recent completed-empty heatmap detected: {recent_empty.name}; "
                "skip another near-current probe to protect credits"
            )

        parsed_heatmap = None
        request_time = None
        selected_lag_hours = None
        heatmap_request_sha = None
        heatmap_cache = None
        heatmap_activity_id: str | None = None
        heatmap_cache_hit = False
        heatmap_new_submissions = 0
        heatmap_completed_empty = 0
        heatmap_negative_cache_skips = 0
        heatmap_attempts: list[dict[str, Any]] = []

        for candidate_index, (candidate_lag, candidate_time) in enumerate(request_candidates):
            heatmap_request = _heatmap_request(
                start_date=candidate_time.start_date,
                start_time=candidate_time.start_time,
            )
            heatmap_payload = heatmap_request.to_provider_payload()
            candidate_sha = canonical_sha256(heatmap_payload)
            candidate_cache = raw_dir / f"heatmap_{candidate_sha[:16]}.json"
            attempt = {
                "lag_hours": candidate_lag,
                "request": candidate_time.to_dict(),
                "request_sha256": candidate_sha,
                "cache_path": str(candidate_cache),
            }

            if candidate_cache.exists() and not args.force_refresh:
                inspection = inspect_heatmap_cache(candidate_cache)
                if inspection.state == "usable":
                    parsed_heatmap = parse_heatmap_artifact(candidate_cache)
                    request_time = candidate_time
                    selected_lag_hours = candidate_lag
                    heatmap_request_sha = candidate_sha
                    heatmap_cache = candidate_cache
                    heatmap_activity_id = inspection.activity_id
                    heatmap_cache_hit = True
                    attempt["outcome"] = "usable_cache"
                    heatmap_attempts.append(attempt)
                    print(f"[cache] usable heatmap lag={candidate_lag}h {candidate_cache.name}")
                    break
                if inspection.state == "completed_empty":
                    heatmap_negative_cache_skips += 1
                    attempt["outcome"] = "completed_empty_cache_skipped"
                    attempt["activity_id"] = inspection.activity_id
                    heatmap_attempts.append(attempt)
                    print(
                        f"[skip-empty-cache] lag={candidate_lag}h {candidate_cache.name}; "
                        "will not resubmit the same completed-empty request"
                    )
                    continue

            # If the provider very recently completed an empty near-current heatmap,
            # avoid probing another same-day near-current hour and go straight to fallback.
            if (
                recent_empty is not None
                and candidate_index == 0
                and candidate_lag <= 6
                and not args.force_refresh
            ):
                attempt["outcome"] = "skipped_recent_empty_backoff"
                heatmap_attempts.append(attempt)
                print(f"[backoff] skipping lag={candidate_lag}h near-current candidate")
                continue

            if heatmap_new_submissions >= args.max_new_heatmap_submissions:
                attempt["outcome"] = "skipped_submission_budget"
                heatmap_attempts.append(attempt)
                print(f"[budget] skipping lag={candidate_lag}h; heatmap submission budget exhausted")
                continue

            print(
                "[submit] FortyGuard heatmap "
                f"local={candidate_time.start_date} {candidate_time.start_time} "
                f"{candidate_time.timezone_name} lag={candidate_lag}h"
            )
            if fg_client is None:
                fg_client = FortyGuardClient(settings)
            submitted = await fg_client.submit_heatmap(heatmap_request)
            activity_id = _activity_id(submitted, operation="heatmap")
            heatmap_new_submissions += 1
            print(f"         activity_id={activity_id}")
            completed = await fg_client.wait_for_completion(activity_id)
            _write_json(candidate_cache, completed)
            inspection = inspect_heatmap_cache(candidate_cache)
            attempt["activity_id"] = activity_id
            attempt["feature_count"] = inspection.feature_count

            if inspection.state == "completed_empty":
                heatmap_completed_empty += 1
                attempt["outcome"] = "completed_empty_provider_response"
                heatmap_attempts.append(attempt)
                print(
                    f"[empty] provider completed lag={candidate_lag}h with zero GeoJSON features; "
                    "negative result cached and never interpreted as thermal evidence"
                )
                continue
            if inspection.state != "usable":
                attempt["outcome"] = "invalid_provider_artifact"
                heatmap_attempts.append(attempt)
                raise HeatmapValidationError(
                    f"Completed heatmap artifact has an unexpected schema for lag={candidate_lag}h."
                )

            parsed_heatmap = parse_heatmap_artifact(candidate_cache)
            request_time = candidate_time
            selected_lag_hours = candidate_lag
            heatmap_request_sha = candidate_sha
            heatmap_cache = candidate_cache
            heatmap_activity_id = activity_id
            attempt["outcome"] = "usable_provider_response"
            heatmap_attempts.append(attempt)
            break

        if parsed_heatmap is None or request_time is None or heatmap_cache is None or heatmap_request_sha is None:
            raise HeatmapValidationError(
                "No usable operational heatmap was available within the bounded candidate strategy. "
                "Completed-empty responses were cached as unavailable evidence, not retried or treated as zero heat."
            )

        stats_consistent = bool(parsed_heatmap.stats_match) and all(parsed_heatmap.stats_match.values())
        if parsed_heatmap.provider_stats is not None and not stats_consistent:
            raise HeatmapValidationError("Operational heatmap provider statistics failed independent verification.")

        heatmap_sha = sha256_file(heatmap_cache)
        hotspot_analysis = detect_relative_hotspots(
            parsed_heatmap.tiles,
            parsed_heatmap.computed_stats,
            source_sha256=heatmap_sha,
            top_ratio=0.10,
            max_hotspots=50,
        )
        selected_hotspots = hotspot_analysis.candidates[: args.hotspot_limit]

        # ------------------------------------------------------------
        # Stage 2: time-aligned environmental enrichment
        # ------------------------------------------------------------
        environmental = []
        env_cache_hits = 0
        env_provider_submissions = 0
        max_timestamp_skew_seconds = 0.0

        for hotspot in selected_hotspots:
            latitude, longitude = representative_point(hotspot.geometry)
            env_request = EnvironmentalParametersRequest(
                latitude=latitude,
                longitude=longitude,
                temperature=hotspot.average_temperature,
                date_time=EnvironmentalDateTimeConfig(
                    start_date=request_time.start_date,
                    start_time=request_time.start_time,
                    filter_type=1,
                ),
            )
            env_payload = env_request.to_provider_payload()
            env_request_sha = canonical_sha256(env_payload)
            safe_tile = str(hotspot.tile_id).replace("/", "_").replace("\\", "_")
            env_cache = raw_dir / f"env_tile_{safe_tile}_{env_request_sha[:12]}.json"

            parsed_env = None
            if env_cache.exists() and not args.force_refresh:
                try:
                    parsed_env = parse_environmental_artifact(env_cache)
                    env_cache_hits += 1
                    print(f"[cache] env rank={hotspot.rank} tile={hotspot.tile_id}")
                except EnvironmentalValidationError:
                    parsed_env = None

            if parsed_env is None:
                if fg_client is None:
                    fg_client = FortyGuardClient(settings)
                print(
                    f"[submit] env rank={hotspot.rank} tile={hotspot.tile_id} "
                    f"lat={latitude:.6f} lon={longitude:.6f}"
                )
                submitted = await fg_client.submit_environmental_parameters(env_request)
                activity_id = _activity_id(submitted, operation="environmental")
                env_provider_submissions += 1
                print(f"         activity_id={activity_id}")
                completed = await fg_client.wait_for_completion(activity_id)
                _write_json(env_cache, completed)
                parsed_env = parse_environmental_artifact(env_cache)

            observation = parsed_env.observation
            if abs(observation.latitude - latitude) > 0.01 or abs(observation.longitude - longitude) > 0.01:
                raise EnvironmentalValidationError(
                    f"Provider location differs materially from request for tile {hotspot.tile_id!r}."
                )
            if abs(observation.temperature_celsius - hotspot.average_temperature) > 0.05:
                raise EnvironmentalValidationError(
                    f"Provider temperature differs from heatmap tile for tile {hotspot.tile_id!r}."
                )

            skew = verify_observation_wall_clock_alignment(
                observed_timestamp=observation.timestamp,
                requested_date=request_time.start_date,
                requested_time=request_time.start_time,
            )
            max_timestamp_skew_seconds = max(max_timestamp_skew_seconds, skew)

            environmental.append(
                build_environmental_enrichment(
                    hotspot_rank=hotspot.rank,
                    tile_id=hotspot.tile_id,
                    thermal_evidence_id=hotspot.evidence_id,
                    request_hash=env_request_sha,
                    representative_latitude=latitude,
                    representative_longitude=longitude,
                    activity_id=parsed_env.activity_id,
                    observation=observation,
                )
            )

        # ------------------------------------------------------------
        # Stage 3: current OSM context (no attic/historical date)
        # ------------------------------------------------------------
        context_inputs = tuple(
            Day3ContextInput(
                rank=item.hotspot_rank,
                tile_id=item.tile_id,
                thermal_evidence_id=item.thermal_evidence_id,
                environmental_evidence_id=item.environmental_evidence_id,
                latitude=item.representative_latitude,
                longitude=item.representative_longitude,
                observed_timestamp=item.observed.timestamp,
            )
            for item in environmental
        )
        context_query = build_current_context_query(
            context_inputs,
            radius_meters=args.radius_meters,
        )
        osm_cache = raw_dir / f"osm_current_{context_query.query_sha256[:16]}.json"
        osm_cache_hit = False
        osm_wrapper: dict[str, Any] | None = None

        if not args.force_refresh and cache_is_fresh(
            osm_cache,
            ttl_minutes=args.osm_cache_ttl_minutes,
            now_utc=now_utc,
        ):
            try:
                candidate = json.loads(osm_cache.read_text(encoding="utf-8"))
                parse_overpass_context(candidate)
                osm_wrapper = candidate
                osm_cache_hit = True
                print(f"[cache] current OSM context {osm_cache.name}")
            except (OSError, json.JSONDecodeError, ContextValidationError):
                osm_wrapper = None

        osm_http_requests = 0
        osm_semantic_rejections = 0
        osm_attempted_endpoints: list[str] = []
        if osm_wrapper is None:
            print("[submit] current OSM context (single bounded union query; no historical attic lookup)")
            osm_client = OverpassClient(settings)
            osm_result = await osm_client.query(context_query.query)
            osm_http_requests = osm_result.request_count
            osm_semantic_rejections = osm_result.semantic_rejections
            osm_attempted_endpoints = list(osm_result.attempted_endpoints)
            osm_wrapper = {
                "provider": "OpenStreetMap Overpass API",
                "endpoint": osm_result.endpoint,
                "query_sha256": context_query.query_sha256,
                "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
                "mode": "current_operational",
                "attribution": ATTRIBUTION,
                "license": "ODbL 1.0",
                "response_semantically_valid": True,
                "response": osm_result.response,
            }
            _write_json(osm_cache, osm_wrapper)

        places, osm_base = parse_overpass_context(osm_wrapper)
        category_status = {category: "observed" for category in CATEGORY_ORDER}
        environment_bundle_sha = canonical_sha256(
            {
                "heatmap_sha256": heatmap_sha,
                "environmental_evidence_ids": [item.environmental_evidence_id for item in environmental],
            }
        )
        contexts = build_hotspot_contexts(
            hotspots=context_inputs,
            places=places,
            radius_meters=args.radius_meters,
            day3_sha256=environment_bundle_sha,
            query_sha256=context_query.query_sha256,
            category_status=category_status,
        )

    except (
        OperationalBaselineError,
        FortyGuardError,
        HeatmapValidationError,
        HotspotDetectionError,
        GeometryError,
        EnvironmentalValidationError,
        ContextValidationError,
        OverpassError,
        ValueError,
    ) as exc:
        print(f"DAY 4.3 FAILED: {_safe_error(exc)}")
        if isinstance(exc, FortyGuardError) and exc.response_body is not None:
            print("FortyGuard response:")
            print(json.dumps(exc.response_body, indent=2) if isinstance(exc.response_body, dict) else exc.response_body)
        if isinstance(exc, OverpassError) and exc.response_body:
            print("Overpass response:")
            print(exc.response_body)
        return 1

    context_by_rank = {item.hotspot_rank: item for item in contexts}
    combined_hotspots = []
    for env in environmental:
        context = context_by_rank[env.hotspot_rank]
        combined_hotspots.append(
            {
                "hotspot_rank": env.hotspot_rank,
                "tile_id": env.tile_id,
                "thermal_evidence_id": env.thermal_evidence_id,
                "environmental_evidence_id": env.environmental_evidence_id,
                "context_evidence_id": context.context_evidence_id,
                "temperature_celsius": env.observed.temperature_celsius,
                "heat_index_celsius": env.observed.heat_index_celsius,
                "apparent_temperature_celsius": env.observed.apparent_temperature_celsius,
                "wet_bulb_temperature_celsius": env.observed.wet_bulb_temperature_celsius,
                "relative_humidity_percent": env.observed.relative_humidity_percent,
                "observed_timestamp": env.observed.timestamp,
                "representative_latitude": env.representative_latitude,
                "representative_longitude": env.representative_longitude,
                "context_category_counts": context.category_counts,
                "nearby_place_count": len(context.nearby_places),
                "nearest_context_places": [item.to_dict() for item in context.nearby_places[:10]],
            }
        )

    artifact = {
        "schema_version": "heatshield.day4_3.operational.v1.1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": (
            "near_current_operational_baseline"
            if selected_lag_hours is not None and selected_lag_hours <= 6
            else "recent_operational_fallback"
        ),
        "classification": {
            "observed": "FortyGuard heatmap/environmental values and current OpenStreetMap mapped objects",
            "derived": "HeatShield validation, relative hotspot ranking, representative points, distances, provenance and temporal alignment checks",
            "inferred": None,
            "recommended": None,
        },
        "time_alignment": {
            "request": request_time.to_dict(),
            "strategy": "bounded availability-aware candidate selection",
            "primary_lag_hours": args.lag_hours,
            "fallback_lag_hours": args.fallback_lag_hours,
            "selected_lag_hours": selected_lag_hours,
            "provider_timezone_semantics": (
                "Provider environmental timestamp/offset retained as source of truth; "
                "request docs do not define an IANA timezone contract for start_time."
            ),
            "max_environmental_wall_clock_skew_seconds": max_timestamp_skew_seconds,
            "osm_mode": "current OSM dataset; not attic/history",
            "osm_base": osm_base,
        },
        "heatmap": {
            "request_sha256": heatmap_request_sha,
            "artifact_path": str(heatmap_cache),
            "artifact_sha256": heatmap_sha,
            "activity_id": parsed_heatmap.provider_activity_id or heatmap_activity_id,
            "cache_hit": heatmap_cache_hit,
            "tile_count": len(parsed_heatmap.tiles),
            "provider_statistics_consistent": stats_consistent,
            "temperature_stats": parsed_heatmap.computed_stats.to_dict(),
            "hotspot_method": hotspot_analysis.method,
            "candidate_count": hotspot_analysis.selected_count,
            "availability": {
                "new_provider_submissions": heatmap_new_submissions,
                "completed_empty_responses_this_run": heatmap_completed_empty,
                "negative_cache_skips": heatmap_negative_cache_skips,
                "recent_empty_backoff_applied": recent_empty is not None,
                "max_new_submissions": args.max_new_heatmap_submissions,
                "attempts": heatmap_attempts,
            },
        },
        "environmental": {
            "hotspots_enriched": len(environmental),
            "provider_submissions": env_provider_submissions,
            "cache_hits": env_cache_hits,
        },
        "context": {
            "provider": "OpenStreetMap via Overpass API",
            "attribution": ATTRIBUTION,
            "license": "ODbL 1.0",
            "license_url": ODBL_URL,
            "radius_meters": args.radius_meters,
            "query_sha256": context_query.query_sha256,
            "query_mode": "current_data_single_bounded_union_query",
            "cache_hit": osm_cache_hit,
            "cache_ttl_minutes": args.osm_cache_ttl_minutes,
            "http_requests_this_run": osm_http_requests,
            "semantic_rejections_this_run": osm_semantic_rejections,
            "attempted_endpoints": osm_attempted_endpoints,
            "objects_fetched": len(places),
            "category_status": {category: "observed" for category in CATEGORY_ORDER},
        },
        "hotspots": combined_hotspots,
        "limitations": [
            "This is a near-current operational baseline, not a clinical or individual health-risk score.",
            "Current OpenStreetMap context represents mapped place presence, not occupancy, population counts, or vulnerability.",
            "Operational heatmap freshness is evidence-based: a recent completed-empty provider response triggers bounded fallback rather than fake data or repeated identical submissions.",
            "A fallback up to the configured lag may be used when near-current data is unavailable; the selected lag is explicit in the artifact and UI must not label fallback data as live.",
            "FortyGuard start_time timezone semantics are not assumed beyond the documented wall-clock input; environmental response timestamps/offsets are retained as provider truth.",
            "OSM current data can lag edits by minutes; the returned osm_base timestamp is retained when available.",
            "Exposure, vulnerability and adaptive capacity scoring remain separate later-stage components.",
        ],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output_path, artifact)

    print("\nHEATSHIELD - DAY 4.3 AVAILABILITY-SAFE OPERATIONAL BASELINE")
    print("=" * 72)
    print(
        f"Selected hour: {request_time.start_date} {request_time.start_time} "
        f"{request_time.timezone_name} | selected_lag={selected_lag_hours}h"
    )
    print(
        f"Heatmap availability: new_submissions={heatmap_new_submissions} "
        f"empty_completed={heatmap_completed_empty} negative_cache_skips={heatmap_negative_cache_skips}"
    )
    print(f"Heatmap tiles: {len(parsed_heatmap.tiles)} | cache_hit={heatmap_cache_hit}")
    print(f"Thermal candidates: {hotspot_analysis.selected_count}")
    print(f"Hotspots enriched: {len(environmental)}")
    print(f"Environmental provider submissions: {env_provider_submissions} | cache_hits={env_cache_hits}")
    print(f"Max environmental wall-clock skew: {max_timestamp_skew_seconds:.1f}s")
    print(f"Current OSM objects fetched: {len(places)} | cache_hit={osm_cache_hit}")
    print(f"Current OSM HTTP requests this run: {osm_http_requests}")
    print(f"OSM semantic errors rejected: {osm_semantic_rejections}")
    print(f"OSM base timestamp: {osm_base}")

    for item in combined_hotspots:
        print("\n" + "-" * 72)
        print(f"Rank #{item['hotspot_rank']} | tile={item['tile_id']}")
        print(f"Temperature: {item['temperature_celsius']:.4f} C")
        print(f"Heat index: {item['heat_index_celsius']}")
        print(f"Apparent temperature: {item['apparent_temperature_celsius']}")
        print(f"Wet bulb: {item['wet_bulb_temperature_celsius']}")
        print(f"Relative humidity: {item['relative_humidity_percent']}")
        print(f"Nearby mapped contexts: {item['nearby_place_count']}")
        print(f"Category counts: {json.dumps(item['context_category_counts'], sort_keys=True)}")
        for nearby in item["nearest_context_places"][:5]:
            place = nearby["place"]
            print(
                f"   {nearby['distance_meters']:.2f} m | {place['category']:<16} | "
                f"{place.get('name') or place['subcategory']} | {place['osm_ref']}"
            )

    print(f"\nSaved operational artifact: {output_path}")
    return 0


def main() -> int:
    return asyncio.run(run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
