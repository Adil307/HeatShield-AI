from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean, pstdev, stdev
from typing import Any

from app.domain.heat import TemperatureStats, TemperatureTile


class HeatmapValidationError(ValueError):
    """Raised when a provider artifact is structurally invalid or unusable."""


@dataclass(frozen=True, slots=True)
class ParsedHeatmap:
    source_path: str
    provider_status: str | None
    provider_activity_id: str | None
    tiles: tuple[TemperatureTile, ...]
    computed_stats: TemperatureStats
    provider_stats: dict[str, float] | None
    stats_match: dict[str, bool]
    provider_stddev_basis: str | None


def _finite_number(value: Any, *, field: str, tile_id: Any = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        suffix = f" for tile {tile_id!r}" if tile_id is not None else ""
        raise HeatmapValidationError(f"{field} must be a finite number{suffix}.")
    result = float(value)
    if not math.isfinite(result):
        suffix = f" for tile {tile_id!r}" if tile_id is not None else ""
        raise HeatmapValidationError(f"{field} must be finite{suffix}.")
    return result


def _optional_finite_number(value: Any, *, field: str, tile_id: Any) -> float | None:
    if value is None:
        return None
    return _finite_number(value, field=field, tile_id=tile_id)


def _validate_point(point: Any, *, tile_id: Any) -> None:
    if not isinstance(point, list) or len(point) < 2:
        raise HeatmapValidationError(f"Invalid coordinate point for tile {tile_id!r}.")
    lon = _finite_number(point[0], field="longitude", tile_id=tile_id)
    lat = _finite_number(point[1], field="latitude", tile_id=tile_id)
    if not -180.0 <= lon <= 180.0:
        raise HeatmapValidationError(f"Longitude out of range for tile {tile_id!r}.")
    if not -90.0 <= lat <= 90.0:
        raise HeatmapValidationError(f"Latitude out of range for tile {tile_id!r}.")


def _validate_ring(ring: Any, *, tile_id: Any) -> None:
    if not isinstance(ring, list) or len(ring) < 4:
        raise HeatmapValidationError(f"Polygon ring must contain at least 4 points for tile {tile_id!r}.")
    for point in ring:
        _validate_point(point, tile_id=tile_id)
    if ring[0][:2] != ring[-1][:2]:
        raise HeatmapValidationError(f"Polygon ring is not closed for tile {tile_id!r}.")


def _validate_polygon_coordinates(coordinates: Any, *, tile_id: Any) -> None:
    if not isinstance(coordinates, list) or not coordinates:
        raise HeatmapValidationError(f"Polygon has no rings for tile {tile_id!r}.")
    for ring in coordinates:
        _validate_ring(ring, tile_id=tile_id)


def _validate_geometry(geometry: Any, *, tile_id: Any) -> dict[str, Any]:
    if not isinstance(geometry, dict):
        raise HeatmapValidationError(f"geometry must be an object for tile {tile_id!r}.")

    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")

    if geometry_type == "Polygon":
        _validate_polygon_coordinates(coordinates, tile_id=tile_id)
    elif geometry_type == "MultiPolygon":
        if not isinstance(coordinates, list) or not coordinates:
            raise HeatmapValidationError(f"MultiPolygon has no polygons for tile {tile_id!r}.")
        for polygon in coordinates:
            _validate_polygon_coordinates(polygon, tile_id=tile_id)
    else:
        raise HeatmapValidationError(
            f"Unsupported geometry type {geometry_type!r} for tile {tile_id!r}."
        )

    return geometry


def _provider_temperature_stats(stats_data: Any) -> dict[str, float] | None:
    if not isinstance(stats_data, dict):
        return None
    raw = stats_data.get("temperature_stats")
    if not isinstance(raw, dict):
        return None

    required = ("minimum", "maximum", "mean", "standard_deviation")
    if any(name not in raw for name in required):
        return None

    try:
        return {
            name: _finite_number(raw[name], field=f"temperature_stats.{name}")
            for name in required
        }
    except HeatmapValidationError:
        return None


def _compare_stats(
    computed: TemperatureStats,
    provider: dict[str, float] | None,
    *,
    tolerance: float,
) -> tuple[dict[str, bool], str | None]:
    if provider is None:
        return {}, None

    provider_std = provider["standard_deviation"]
    population_match = math.isclose(
        computed.population_standard_deviation,
        provider_std,
        abs_tol=tolerance,
    )
    sample_match = (
        computed.sample_standard_deviation is not None
        and math.isclose(
            computed.sample_standard_deviation,
            provider_std,
            abs_tol=tolerance,
        )
    )

    if sample_match and not population_match:
        stddev_basis = "sample_n_minus_1"
    elif population_match and not sample_match:
        stddev_basis = "population_n"
    elif sample_match and population_match:
        # This happens for zero-variance data. Either convention yields 0.
        stddev_basis = "indistinguishable_zero_variance"
    else:
        stddev_basis = "mismatch"

    return (
        {
            "minimum": math.isclose(computed.minimum, provider["minimum"], abs_tol=tolerance),
            "maximum": math.isclose(computed.maximum, provider["maximum"], abs_tol=tolerance),
            "mean": math.isclose(computed.mean, provider["mean"], abs_tol=tolerance),
            "standard_deviation": population_match or sample_match,
        },
        stddev_basis,
    )


def parse_heatmap_artifact(
    source: str | Path,
    *,
    stats_tolerance: float = 1e-6,
) -> ParsedHeatmap:
    source_path = Path(source)
    if not source_path.exists():
        raise HeatmapValidationError(f"Heatmap artifact not found: {source_path}")

    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise HeatmapValidationError(f"Heatmap artifact is not valid UTF-8: {source_path}") from exc
    except json.JSONDecodeError as exc:
        raise HeatmapValidationError(f"Invalid JSON in {source_path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise HeatmapValidationError("Top-level provider response must be an object.")

    if payload.get("error") is True:
        raise HeatmapValidationError("Provider artifact reports error=true.")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise HeatmapValidationError("Provider response is missing object field 'data'.")

    provider_status = data.get("status") if isinstance(data.get("status"), str) else None
    if provider_status is not None and provider_status.lower() != "completed":
        raise HeatmapValidationError(
            f"Heatmap artifact status must be Completed, got {provider_status!r}."
        )

    result = data.get("result")
    if not isinstance(result, dict):
        raise HeatmapValidationError("Provider response is missing object field 'data.result'.")

    map_data = result.get("map_data")
    if not isinstance(map_data, dict) or map_data.get("type") != "FeatureCollection":
        raise HeatmapValidationError("data.result.map_data must be a GeoJSON FeatureCollection.")

    features = map_data.get("features")
    if not isinstance(features, list):
        raise HeatmapValidationError("data.result.map_data.features must be a list.")
    if not features:
        raise HeatmapValidationError(
            "Heatmap completed but contains zero GeoJSON features; no thermal analysis can be performed."
        )

    tiles: list[TemperatureTile] = []
    seen_tile_ids: set[int | str] = set()

    for index, feature in enumerate(features):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise HeatmapValidationError(f"Feature at index {index} is not a valid GeoJSON Feature.")

        properties = feature.get("properties")
        if not isinstance(properties, dict):
            raise HeatmapValidationError(f"Feature at index {index} has no properties object.")

        tile_id = properties.get("tile_id")
        if isinstance(tile_id, bool) or not isinstance(tile_id, (int, str)) or tile_id == "":
            raise HeatmapValidationError(f"Feature at index {index} has an invalid tile_id.")
        if tile_id in seen_tile_ids:
            raise HeatmapValidationError(f"Duplicate tile_id detected: {tile_id!r}")
        seen_tile_ids.add(tile_id)

        average_temperature = _finite_number(
            properties.get("average_temperature"),
            field="average_temperature",
            tile_id=tile_id,
        )
        min_temperature = _optional_finite_number(
            properties.get("min_temperature"),
            field="min_temperature",
            tile_id=tile_id,
        )
        max_temperature = _optional_finite_number(
            properties.get("max_temperature"),
            field="max_temperature",
            tile_id=tile_id,
        )

        if min_temperature is not None and max_temperature is not None:
            if min_temperature > max_temperature:
                raise HeatmapValidationError(
                    f"min_temperature exceeds max_temperature for tile {tile_id!r}."
                )
            if not (min_temperature <= average_temperature <= max_temperature):
                raise HeatmapValidationError(
                    f"average_temperature falls outside tile min/max for tile {tile_id!r}."
                )

        geometry = _validate_geometry(feature.get("geometry"), tile_id=tile_id)

        tiles.append(
            TemperatureTile(
                tile_id=tile_id,
                average_temperature=average_temperature,
                min_temperature=min_temperature,
                max_temperature=max_temperature,
                geometry=geometry,
                source_index=index,
            )
        )

    temperatures = [tile.average_temperature for tile in tiles]
    computed = TemperatureStats(
        minimum=min(temperatures),
        maximum=max(temperatures),
        mean=fmean(temperatures),
        population_standard_deviation=pstdev(temperatures),
        sample_standard_deviation=(stdev(temperatures) if len(temperatures) > 1 else None),
        count=len(temperatures),
    )

    provider_stats = _provider_temperature_stats(result.get("stats_data"))
    stats_match, provider_stddev_basis = _compare_stats(
        computed, provider_stats, tolerance=stats_tolerance
    )

    return ParsedHeatmap(
        source_path=str(source_path),
        provider_status=provider_status,
        provider_activity_id=(
            data.get("activity_id") if isinstance(data.get("activity_id"), str) else None
        ),
        tiles=tuple(tiles),
        computed_stats=computed,
        provider_stats=provider_stats,
        stats_match=stats_match,
        provider_stddev_basis=provider_stddev_basis,
    )
