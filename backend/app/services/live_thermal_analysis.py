from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Protocol

from app.schemas.fortyguard import HeatmapRequest
from app.services.heatmap_parser import HeatmapValidationError, parse_heatmap_artifact
from app.services.hotspot_detector import HotspotDetectionError, detect_relative_hotspots


MAX_DEMO_AOI_SQ_MILES = 10.0
_SQ_KM_PER_SQ_MILE = 2.589988110336
_EARTH_RADIUS_KM = 6371.0088


class LiveThermalAnalysisError(ValueError):
    """Raised when a Day 11 live thermal request cannot be safely completed."""


class FortyGuardLiveClient(Protocol):
    async def submit_heatmap(self, request: HeatmapRequest) -> dict[str, Any]: ...

    async def wait_for_completion(self, activity_id: str) -> dict[str, Any]: ...


def canonical_request_payload(request: HeatmapRequest) -> dict[str, Any]:
    """Return the exact normalized provider payload used for hashing/caching."""
    return request.to_provider_payload()


def live_request_hash(request: HeatmapRequest) -> str:
    payload = canonical_request_payload(request)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _ring_area_sq_km(ring: list[list[float]]) -> float:
    if len(ring) < 4:
        raise LiveThermalAnalysisError("AOI polygon ring must contain at least four coordinates.")

    points = ring[:-1] if ring[0][:2] == ring[-1][:2] else ring
    if len(points) < 3:
        raise LiveThermalAnalysisError("AOI polygon ring must contain at least three unique points.")

    mean_lat = math.radians(sum(float(point[1]) for point in points) / len(points))
    projected: list[tuple[float, float]] = []
    for point in points:
        if len(point) < 2:
            raise LiveThermalAnalysisError("AOI contains an invalid coordinate pair.")
        lon = float(point[0])
        lat = float(point[1])
        if not (math.isfinite(lon) and math.isfinite(lat)):
            raise LiveThermalAnalysisError("AOI coordinates must be finite.")
        x = _EARTH_RADIUS_KM * math.radians(lon) * math.cos(mean_lat)
        y = _EARTH_RADIUS_KM * math.radians(lat)
        projected.append((x, y))

    area_twice = 0.0
    for index, (x1, y1) in enumerate(projected):
        x2, y2 = projected[(index + 1) % len(projected)]
        area_twice += x1 * y2 - x2 * y1
    return abs(area_twice) / 2.0


def approximate_aoi_area_sq_miles(request: HeatmapRequest) -> float:
    total_sq_km = 0.0
    for feature in request.polygon_aoi.features:
        rings = feature.geometry.coordinates
        if not rings:
            continue
        outer = _ring_area_sq_km(rings[0])
        holes = sum(_ring_area_sq_km(ring) for ring in rings[1:])
        total_sq_km += max(0.0, outer - holes)
    return total_sq_km / _SQ_KM_PER_SQ_MILE


def validate_live_request(request: HeatmapRequest, *, max_aoi_sq_miles: float = MAX_DEMO_AOI_SQ_MILES) -> float:
    if request.analytic_type != "tcm":
        raise LiveThermalAnalysisError("Day 11 live mode currently supports TCM temperature analysis only.")
    area_sq_miles = approximate_aoi_area_sq_miles(request)
    if area_sq_miles <= 0:
        raise LiveThermalAnalysisError("AOI area must be greater than zero.")
    if area_sq_miles > max_aoi_sq_miles:
        raise LiveThermalAnalysisError(
            f"AOI is approximately {area_sq_miles:.2f} mi²; demo-safe live mode is limited to {max_aoi_sq_miles:.0f} mi². Zoom in and try again."
        )
    return area_sq_miles


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def _load_cached_completion(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if not isinstance(data, dict) or str(data.get("status", "")).lower() not in {"completed", "succeeded"}:
        return None
    return payload


def _provider_activity_id(submission: dict[str, Any]) -> str | None:
    data = submission.get("data")
    if not isinstance(data, dict):
        return None
    value = data.get("activity_id")
    return str(value) if value else None


def _map_data(completion: dict[str, Any]) -> dict[str, Any]:
    data = completion.get("data")
    result = data.get("result") if isinstance(data, dict) else None
    map_data = result.get("map_data") if isinstance(result, dict) else None
    if not isinstance(map_data, dict) or map_data.get("type") != "FeatureCollection":
        raise LiveThermalAnalysisError("Completed FortyGuard response does not contain map_data FeatureCollection.")
    return map_data


async def run_live_thermal_analysis(
    request: HeatmapRequest,
    *,
    client: FortyGuardLiveClient | None,
    cache_dir: str | Path,
    max_aoi_sq_miles: float = MAX_DEMO_AOI_SQ_MILES,
) -> dict[str, Any]:
    """Run or reuse a fresh FortyGuard TCM job without fabricating decision context.

    Day 11 deliberately stops at verified thermal evidence + relative hottest tiles.
    Planning priority, vulnerability, adaptive capacity, recommendations and medical
    probability remain unsupported until their required context is collected.
    """
    area_sq_miles = validate_live_request(request, max_aoi_sq_miles=max_aoi_sq_miles)
    request_hash = live_request_hash(request)
    cache_path = Path(cache_dir) / f"tcm_{request_hash}.json"

    completion = _load_cached_completion(cache_path)
    cache_hit = completion is not None
    submitted_activity_id: str | None = None

    if completion is None:
        if client is None:
            raise LiveThermalAnalysisError(
                "FORTYGUARD_API_KEY is not configured and no completed cache entry exists for this request."
            )
        submission = await client.submit_heatmap(request)
        submitted_activity_id = _provider_activity_id(submission)
        if not submitted_activity_id:
            raise LiveThermalAnalysisError("FortyGuard submission returned no activity_id.")
        completion = await client.wait_for_completion(submitted_activity_id)
        _atomic_write_json(cache_path, completion)

    try:
        parsed = parse_heatmap_artifact(cache_path)
    except HeatmapValidationError as exc:
        # Do not silently reuse a corrupt provider/cache artifact.
        try:
            cache_path.unlink()
        except OSError:
            pass
        raise LiveThermalAnalysisError(f"FortyGuard completion could not be validated: {exc}") from exc

    source_sha256 = hashlib.sha256(cache_path.read_bytes()).hexdigest()
    try:
        analysis = detect_relative_hotspots(
            parsed.tiles,
            parsed.computed_stats,
            source_sha256=source_sha256,
            top_ratio=0.02,
            min_hotspots=3,
            max_hotspots=3,
        )
    except HotspotDetectionError as exc:
        raise LiveThermalAnalysisError(str(exc)) from exc

    hottest_tiles = [
        {
            "hotspot_rank": candidate.rank,
            "tile_id": candidate.tile_id,
            "temperature_celsius": candidate.average_temperature,
            "relative_band": candidate.relative_band,
            "z_score": candidate.z_score,
            "relative_intensity": candidate.relative_intensity,
            "evidence_id": candidate.evidence_id,
        }
        for candidate in analysis.candidates
    ]

    provider_activity_id = parsed.provider_activity_id or submitted_activity_id
    stats = parsed.computed_stats
    return {
        "schema_version": "heatshield.day11.live_thermal_analysis.v1",
        "analysis": {
            "mode": "fresh_provider_thermal_analysis",
            "thermal_evidence_source": "FortyGuard",
            "analytic_type": request.analytic_type,
            "granularity_meters": request.granularity,
            "date_time": request.date_time.model_dump(exclude_none=True),
            "aoi_area_sq_miles_approx": round(area_sq_miles, 4),
            "request_hash": request_hash,
            "cache_hit": cache_hit,
        },
        "summary": {
            "tile_count": stats.count,
            "minimum_temperature_celsius": stats.minimum,
            "maximum_temperature_celsius": stats.maximum,
            "mean_temperature_celsius": stats.mean,
            "population_standard_deviation_celsius": stats.population_standard_deviation,
            "hottest_tile_count": len(hottest_tiles),
        },
        "hottest_tiles": hottest_tiles,
        "heatmap_geojson": _map_data(completion),
        "provenance": {
            "provider": "FortyGuard",
            "activity_id": provider_activity_id,
            "source_sha256": source_sha256,
            "request_hash": request_hash,
            "cache_hit": cache_hit,
            "new_provider_jobs_for_this_request": 0 if cache_hit else 1,
        },
        "safety": {
            "planning_priority_supported": False,
            "medical_probability_supported": False,
            "occupancy_inferred": False,
            "recommendations_generated": False,
            "scope_note": (
                "Fresh mode shows verified thermal evidence and relative hottest tiles only. "
                "It does not create a planning-priority or medical-risk score without the required context evidence."
            ),
        },
    }
