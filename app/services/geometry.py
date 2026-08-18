from __future__ import annotations

import math
from typing import Any


class GeometryError(ValueError):
    """Raised when a GeoJSON geometry cannot yield a safe representative point."""


def _finite(value: Any, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GeometryError(f"{field} must be numeric.")
    result = float(value)
    if not math.isfinite(result):
        raise GeometryError(f"{field} must be finite.")
    return result


def _ring_points(ring: Any) -> list[tuple[float, float]]:
    if not isinstance(ring, list) or len(ring) < 4:
        raise GeometryError("Polygon exterior ring must contain at least four points.")

    points: list[tuple[float, float]] = []
    for point in ring:
        if not isinstance(point, list) or len(point) < 2:
            raise GeometryError("Invalid coordinate point.")
        lon = _finite(point[0], field="longitude")
        lat = _finite(point[1], field="latitude")
        if not -180.0 <= lon <= 180.0:
            raise GeometryError("Longitude out of range.")
        if not -90.0 <= lat <= 90.0:
            raise GeometryError("Latitude out of range.")
        points.append((lon, lat))

    if points[0] != points[-1]:
        raise GeometryError("Polygon exterior ring is not closed.")
    return points


def _polygon_area_centroid(ring: Any) -> tuple[float, float, float]:
    """Return planar lon/lat polygon centroid and absolute signed-area magnitude.

    HeatShield uses this only for small provider tiles, where a planar approximation
    is adequate and avoids pulling a heavy geospatial dependency into the hot path.
    """
    points = _ring_points(ring)
    # Translate to a local origin before applying the shoelace formula. This
    # materially reduces floating-point cancellation for small urban tiles whose
    # longitude/latitude coordinates have much larger absolute offsets.
    origin_x, origin_y = points[0]
    shifted = [(x - origin_x, y - origin_y) for x, y in points]

    twice_area = 0.0
    cx_numerator = 0.0
    cy_numerator = 0.0

    for (x0, y0), (x1, y1) in zip(shifted, shifted[1:]):
        cross = x0 * y1 - x1 * y0
        twice_area += cross
        cx_numerator += (x0 + x1) * cross
        cy_numerator += (y0 + y1) * cross

    if abs(twice_area) < 1e-15:
        # Degenerate-but-valid provider tile: fall back to vertex mean excluding
        # the duplicated closing point, rather than dividing by near-zero area.
        open_points = points[:-1]
        lon = sum(point[0] for point in open_points) / len(open_points)
        lat = sum(point[1] for point in open_points) / len(open_points)
        return lon, lat, 0.0

    lon = origin_x + (cx_numerator / (3.0 * twice_area))
    lat = origin_y + (cy_numerator / (3.0 * twice_area))
    return lon, lat, abs(twice_area) / 2.0


def representative_point(geometry: dict[str, Any]) -> tuple[float, float]:
    """Return (latitude, longitude) for a Polygon/MultiPolygon tile in O(v)."""
    if not isinstance(geometry, dict):
        raise GeometryError("geometry must be an object.")

    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")

    if geometry_type == "Polygon":
        if not isinstance(coordinates, list) or not coordinates:
            raise GeometryError("Polygon coordinates are empty.")
        lon, lat, _ = _polygon_area_centroid(coordinates[0])
        return lat, lon

    if geometry_type == "MultiPolygon":
        if not isinstance(coordinates, list) or not coordinates:
            raise GeometryError("MultiPolygon coordinates are empty.")

        best: tuple[float, float, float] | None = None
        for polygon in coordinates:
            if not isinstance(polygon, list) or not polygon:
                raise GeometryError("MultiPolygon contains an empty polygon.")
            lon, lat, area = _polygon_area_centroid(polygon[0])
            if best is None or area > best[2]:
                best = (lon, lat, area)

        assert best is not None
        return best[1], best[0]

    raise GeometryError(f"Unsupported geometry type: {geometry_type!r}")
