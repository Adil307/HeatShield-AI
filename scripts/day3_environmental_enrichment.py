from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.providers.fortyguard import FortyGuardClient, FortyGuardError
from app.schemas.fortyguard import EnvironmentalDateTimeConfig, EnvironmentalParametersRequest
from app.services.day2_artifact import Day2ArtifactError, load_day2_artifact
from app.services.environmental_enrichment import (
    build_environmental_enrichment,
    request_fingerprint,
)
from app.services.environmental_parser import (
    EnvironmentalValidationError,
    parse_environmental_artifact,
)
from app.services.evidence import sha256_file
from app.services.geometry import GeometryError, representative_point


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Enrich Day-2 thermal hotspot candidates with FortyGuard environmental "
            "parameters using cached, provenance-preserving provider calls."
        )
    )
    parser.add_argument(
        "--input",
        default="data/processed/day2_hotspot_analysis.json",
        help="Day-2 hotspot artifact.",
    )
    parser.add_argument(
        "--output",
        default="data/processed/day3_environmental_enrichment.json",
        help="Derived Day-3 environmental artifact.",
    )
    parser.add_argument(
        "--raw-dir",
        default="data/raw/day3",
        help="Local ignored directory for completed provider responses.",
    )
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD matching the source heatmap.")
    parser.add_argument("--start-time", required=True, help="HH:MM matching the source heatmap.")
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Number of highest-ranked hotspots to enrich (default: 3).",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Ignore valid local environmental cache and submit provider calls again.",
    )
    return parser


def _extract_activity_id(response: dict[str, Any]) -> str:
    data = response.get("data")
    activity_id = data.get("activity_id") if isinstance(data, dict) else None
    if not isinstance(activity_id, str) or not activity_id:
        raise FortyGuardError(
            "FortyGuard environmental submission returned no activity_id.",
            response_body=response,
        )
    return activity_id


def _cache_path(raw_dir: Path, *, tile_id: int | str, request_hash: str) -> Path:
    safe_tile = str(tile_id).replace("/", "_").replace("\\", "_")
    return raw_dir / f"env_tile_{safe_tile}_{request_hash[:12]}.json"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


async def run(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    output_path = Path(args.output)
    raw_dir = Path(args.raw_dir)

    if args.limit < 1 or args.limit > 15:
        print("DAY 3 FAILED: --limit must be between 1 and 15.")
        return 1

    try:
        day2 = load_day2_artifact(input_path)

        source_heatmap = Path(day2.source_artifact_path)
        if not source_heatmap.exists():
            raise Day2ArtifactError(
                f"Day-2 source heatmap no longer exists locally: {source_heatmap}"
            )

        current_source_hash = sha256_file(source_heatmap)
        if current_source_hash != day2.source_artifact_sha256:
            raise Day2ArtifactError(
                "Day-2 artifact is stale: source heatmap SHA-256 no longer matches."
            )

        selected = day2.hotspots[: min(args.limit, len(day2.hotspots))]
        client: FortyGuardClient | None = None
        enrichments = []
        cache_hits = 0
        provider_submissions = 0

        for hotspot in selected:
            latitude, longitude = representative_point(hotspot.geometry)
            request = EnvironmentalParametersRequest(
                latitude=latitude,
                longitude=longitude,
                temperature=hotspot.average_temperature,
                date_time=EnvironmentalDateTimeConfig(
                    start_date=args.start_date,
                    start_time=args.start_time,
                    filter_type=1,
                ),
            )
            request_payload = request.to_provider_payload()
            request_hash = request_fingerprint(request_payload)
            cache_path = _cache_path(
                raw_dir,
                tile_id=hotspot.tile_id,
                request_hash=request_hash,
            )

            parsed = None
            if cache_path.exists() and not args.force_refresh:
                try:
                    parsed = parse_environmental_artifact(cache_path)
                    cache_hits += 1
                    print(
                        f"[cache] rank={hotspot.rank} tile={hotspot.tile_id} "
                        f"activity={parsed.activity_id}"
                    )
                except EnvironmentalValidationError:
                    # Corrupt/old cache is never trusted; submit a fresh provider job.
                    parsed = None

            if parsed is None:
                print(
                    f"[submit] rank={hotspot.rank} tile={hotspot.tile_id} "
                    f"lat={latitude:.6f} lon={longitude:.6f} "
                    f"temp={hotspot.average_temperature:.4f} C"
                )
                if client is None:
                    client = FortyGuardClient(get_settings())
                submitted = await client.submit_environmental_parameters(request)
                activity_id = _extract_activity_id(submitted)
                provider_submissions += 1
                print(f"         activity_id={activity_id}")
                completed = await client.wait_for_completion(activity_id)
                _write_json(cache_path, completed)
                parsed = parse_environmental_artifact(cache_path)

            observation = parsed.observation
            if abs(observation.latitude - latitude) > 0.01 or abs(observation.longitude - longitude) > 0.01:
                raise EnvironmentalValidationError(
                    f"Provider location differs materially from request for tile {hotspot.tile_id!r}."
                )
            if abs(observation.temperature_celsius - hotspot.average_temperature) > 0.05:
                raise EnvironmentalValidationError(
                    f"Provider temperature differs from Day-2 tile temperature for tile {hotspot.tile_id!r}."
                )

            enrichments.append(
                build_environmental_enrichment(
                    hotspot_rank=hotspot.rank,
                    tile_id=hotspot.tile_id,
                    thermal_evidence_id=hotspot.evidence_id,
                    request_hash=request_hash,
                    representative_latitude=latitude,
                    representative_longitude=longitude,
                    activity_id=parsed.activity_id,
                    observation=observation,
                )
            )

    except (
        Day2ArtifactError,
        GeometryError,
        EnvironmentalValidationError,
        FortyGuardError,
        ValueError,
    ) as exc:
        print(f"DAY 3 FAILED: {exc}")
        if isinstance(exc, FortyGuardError) and exc.response_body is not None:
            print("Provider response:")
            print(json.dumps(exc.response_body, indent=2) if isinstance(exc.response_body, dict) else exc.response_body)
        return 1

    artifact = {
        "schema_version": "heatshield.day3.environment.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "classification": {
            "observed": (
                "FortyGuard Day-2 tile temperature plus completed environmental-parameter values"
            ),
            "derived": (
                "HeatShield tile representative point, request fingerprint, metric deltas, "
                "completeness and evidence linkage"
            ),
            "inferred": None,
            "recommended": None,
        },
        "source": {
            "day2_artifact_path": str(input_path),
            "heatmap_artifact_path": day2.source_artifact_path,
            "heatmap_artifact_sha256": day2.source_artifact_sha256,
            "date_time": {
                "start_date": args.start_date,
                "start_time": args.start_time,
                "filter_type": 1,
            },
        },
        "execution": {
            "requested_hotspots": args.limit,
            "enriched_hotspots": len(enrichments),
            "provider_submissions": provider_submissions,
            "cache_hits": cache_hits,
            "cache_policy": "request-fingerprint completed-response cache",
        },
        "environmental_enrichments": [item.to_dict() for item in enrichments],
        "limitations": [
            "Day 3 adds environmental thermal context; it is not yet a population or clinical heat-risk score.",
            "Core thermal metrics are preserved as provider observations and are not re-invented locally.",
            "Representative points use a planar centroid approximation appropriate for small heatmap tiles.",
            "Missing or provider-sentinel environmental values remain missing; HeatShield does not impute them on Day 3.",
            "The composite exposure/vulnerability/adaptive-capacity risk engine is intentionally deferred to later stages.",
        ],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")

    print("\nHEATSHIELD - DAY 3 ENVIRONMENTAL THERMAL CONTEXT")
    print("=" * 62)
    print(f"Day-2 source integrity verified: {day2.source_artifact_sha256}")
    print(f"Hotspots enriched: {len(enrichments)}")
    print(f"Provider submissions this run: {provider_submissions}")
    print(f"Cache hits: {cache_hits}")

    for item in enrichments:
        obs = item.observed
        print("\n" + "-" * 62)
        print(f"Rank #{item.hotspot_rank} | tile={item.tile_id}")
        print(f"Air temperature: {obs.temperature_celsius:.4f} C")
        print(f"Heat index: {obs.heat_index_celsius}")
        print(f"Apparent temperature: {obs.apparent_temperature_celsius}")
        print(f"Wet bulb: {obs.wet_bulb_temperature_celsius}")
        print(f"Relative humidity: {obs.relative_humidity_percent}")
        print(f"Core metric completeness: {item.core_metric_completeness:.2f}")
        print(f"Environmental evidence: {item.environmental_evidence_id}")

    print(f"\nSaved derived artifact: {output_path}")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
