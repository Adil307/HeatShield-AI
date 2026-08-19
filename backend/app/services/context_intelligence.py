from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from app.domain.context import ContextPlace, HotspotContext, NearbyContextPlace
from app.services.context_taxonomy import CATEGORY_ORDER, classify_context, overpass_filters_for_category
from app.services.day3_artifact import Day3ContextInput


EARTH_RADIUS_M = 6_371_008.8


class ContextValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BoundingBox:
    south: float
    west: float
    north: float
    east: float

    def as_overpass(self) -> str:
        return f"{self.south:.7f},{self.west:.7f},{self.north:.7f},{self.east:.7f}"


@dataclass(frozen=True, slots=True)
class ContextQueryPlan:
    category: str
    query: str
    query_sha256: str


def query_fingerprint(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()


def query_bundle_fingerprint(plans: Iterable[ContextQueryPlan]) -> str:
    canonical = "\n".join(f"{plan.category}:{plan.query_sha256}" for plan in plans)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def expanded_bbox(points: Iterable[tuple[float, float]], radius_meters: float) -> BoundingBox:
    point_list = list(points)
    if not point_list:
        raise ContextValidationError("At least one hotspot point is required.")
    if not math.isfinite(radius_meters) or not 100 <= radius_meters <= 2_000:
        raise ContextValidationError("Context radius must be between 100 and 2000 meters.")

    latitudes = [lat for lat, _ in point_list]
    longitudes = [lon for _, lon in point_list]
    for lat, lon in point_list:
        if (
            not math.isfinite(lat)
            or not math.isfinite(lon)
            or not -90 <= lat <= 90
            or not -180 <= lon <= 180
        ):
            raise ContextValidationError("Invalid hotspot coordinate.")

    mean_lat = sum(latitudes) / len(latitudes)
    lat_padding = radius_meters / 111_320.0
    lon_scale = max(0.05, math.cos(math.radians(mean_lat)))
    lon_padding = radius_meters / (111_320.0 * lon_scale)

    return BoundingBox(
        south=max(-90.0, min(latitudes) - lat_padding),
        west=max(-180.0, min(longitudes) - lon_padding),
        north=min(90.0, max(latitudes) + lat_padding),
        east=min(180.0, max(longitudes) + lon_padding),
    )


def build_context_query_bundle(
    hotspots: Iterable[Day3ContextInput],
    *,
    radius_meters: float,
    snapshot_utc: datetime,
) -> tuple[tuple[ContextQueryPlan, ...], BoundingBox]:
    """Build five bounded historical queries instead of one large union query.

    This trades a small number of sequential requests for lower per-query server cost,
    clearer category-level completeness, and safer partial degradation.
    """
    selected = list(hotspots)
    bbox = expanded_bbox(((item.latitude, item.longitude) for item in selected), radius_meters)
    snapshot = snapshot_utc.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    plans: list[ContextQueryPlan] = []
    for category in CATEGORY_ORDER:
        filters = "\n  ".join(overpass_filters_for_category(category))
        query = (
            f'[out:json][timeout:25][date:"{snapshot}"][bbox:{bbox.as_overpass()}];\n'
            "(\n"
            f"  {filters}\n"
            ");\n"
            "out center tags qt;"
        )
        plans.append(
            ContextQueryPlan(
                category=category,
                query=query,
                query_sha256=query_fingerprint(query),
            )
        )
    return tuple(plans), bbox


def _extract_coordinate(element: dict[str, Any]) -> tuple[float, float] | None:
    if element.get("type") == "node":
        lat, lon = element.get("lat"), element.get("lon")
    else:
        center = element.get("center")
        if not isinstance(center, dict):
            return None
        lat, lon = center.get("lat"), center.get("lon")

    if (
        isinstance(lat, bool)
        or isinstance(lon, bool)
        or not isinstance(lat, (int, float))
        or not isinstance(lon, (int, float))
    ):
        return None
    lat_f, lon_f = float(lat), float(lon)
    if (
        not math.isfinite(lat_f)
        or not math.isfinite(lon_f)
        or not -90 <= lat_f <= 90
        or not -180 <= lon_f <= 180
    ):
        return None
    return lat_f, lon_f


def parse_overpass_context(payload: dict[str, Any]) -> tuple[tuple[ContextPlace, ...], str | None]:
    response = payload.get("response") if isinstance(payload.get("response"), dict) else payload
    if not isinstance(response, dict):
        raise ContextValidationError("Overpass response is not an object.")

    elements = response.get("elements")
    if not isinstance(elements, list):
        raise ContextValidationError("Overpass response contains no elements list.")

    remark = response.get("remark")
    if isinstance(remark, str) and remark.strip():
        raise ContextValidationError(
            f"Overpass response is not semantically valid: {remark.strip()}"
        )

    osm3s = response.get("osm3s")
    osm_base = osm3s.get("timestamp_osm_base") if isinstance(osm3s, dict) else None

    deduped: dict[tuple[str, int], ContextPlace] = {}
    for element in elements:
        if not isinstance(element, dict):
            continue
        osm_type = element.get("type")
        osm_id = element.get("id")
        tags = element.get("tags")
        if osm_type not in {"node", "way", "relation"} or isinstance(osm_id, bool) or not isinstance(osm_id, int):
            continue
        if not isinstance(tags, dict):
            continue

        clean_tags = {
            str(k): str(v)
            for k, v in tags.items()
            if isinstance(k, str) and isinstance(v, (str, int, float))
        }
        classification = classify_context(clean_tags)
        coordinate = _extract_coordinate(element)
        if classification is None or coordinate is None:
            continue

        category, subcategory = classification
        lat, lon = coordinate
        key = (osm_type, osm_id)
        deduped[key] = ContextPlace(
            osm_type=osm_type,
            osm_id=osm_id,
            name=clean_tags.get("name"),
            category=category,
            subcategory=subcategory,
            latitude=lat,
            longitude=lon,
            tags=clean_tags,
        )

    places = tuple(sorted(deduped.values(), key=lambda p: (p.osm_type, p.osm_id)))
    return places, osm_base if isinstance(osm_base, str) else None


def merge_context_places(groups: Iterable[Iterable[ContextPlace]]) -> tuple[ContextPlace, ...]:
    deduped: dict[str, ContextPlace] = {}
    for group in groups:
        for place in group:
            deduped[place.osm_ref] = place
    return tuple(sorted(deduped.values(), key=lambda p: (p.osm_type, p.osm_id)))


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


class _HotspotSpatialIndex:
    def __init__(self, hotspots: Iterable[Day3ContextInput], radius_meters: float) -> None:
        self.hotspots = tuple(hotspots)
        if not self.hotspots:
            raise ContextValidationError("No hotspots supplied to context index.")
        self.radius_meters = radius_meters
        self.reference_latitude = sum(item.latitude for item in self.hotspots) / len(self.hotspots)
        self._cos_reference = max(0.05, math.cos(math.radians(self.reference_latitude)))
        self._buckets: dict[tuple[int, int], list[Day3ContextInput]] = defaultdict(list)
        for hotspot in self.hotspots:
            self._buckets[self._cell(hotspot.latitude, hotspot.longitude)].append(hotspot)

    def _xy(self, latitude: float, longitude: float) -> tuple[float, float]:
        y = math.radians(latitude) * EARTH_RADIUS_M
        x = math.radians(longitude) * EARTH_RADIUS_M * self._cos_reference
        return x, y

    def _cell(self, latitude: float, longitude: float) -> tuple[int, int]:
        x, y = self._xy(latitude, longitude)
        size = self.radius_meters
        return math.floor(x / size), math.floor(y / size)

    def candidates(self, latitude: float, longitude: float) -> Iterable[Day3ContextInput]:
        cell_x, cell_y = self._cell(latitude, longitude)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                yield from self._buckets.get((cell_x + dx, cell_y + dy), ())


def context_evidence_id(*, day3_sha256: str, query_sha256: str, hotspot: Day3ContextInput) -> str:
    raw = (
        f"osm-context|{day3_sha256}|{query_sha256}|{hotspot.environmental_evidence_id}|"
        f"{hotspot.tile_id}|{hotspot.rank}"
    )
    return "hs_ctx_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def build_hotspot_contexts(
    *,
    hotspots: Iterable[Day3ContextInput],
    places: Iterable[ContextPlace],
    radius_meters: float,
    day3_sha256: str,
    query_sha256: str,
    category_status: Mapping[str, str] | None = None,
) -> tuple[HotspotContext, ...]:
    selected = tuple(hotspots)
    index = _HotspotSpatialIndex(selected, radius_meters)
    assignments: dict[int, list[NearbyContextPlace]] = {item.rank: [] for item in selected}

    for place in places:
        seen_ranks: set[int] = set()
        for hotspot in index.candidates(place.latitude, place.longitude):
            if hotspot.rank in seen_ranks:
                continue
            seen_ranks.add(hotspot.rank)
            distance = haversine_meters(
                hotspot.latitude,
                hotspot.longitude,
                place.latitude,
                place.longitude,
            )
            if distance <= radius_meters:
                assignments[hotspot.rank].append(
                    NearbyContextPlace(place=place, distance_meters=round(distance, 2))
                )

    statuses = {
        category: (category_status.get(category, "observed") if category_status else "observed")
        for category in CATEGORY_ORDER
    }

    results: list[HotspotContext] = []
    for hotspot in selected:
        nearby = assignments[hotspot.rank]
        nearby.sort(
            key=lambda item: (
                item.distance_meters,
                item.place.category,
                item.place.osm_type,
                item.place.osm_id,
            )
        )
        counts_raw = Counter(item.place.category for item in nearby)
        counts = {category: counts_raw.get(category, 0) for category in CATEGORY_ORDER}
        results.append(
            HotspotContext(
                hotspot_rank=hotspot.rank,
                tile_id=hotspot.tile_id,
                thermal_evidence_id=hotspot.thermal_evidence_id,
                environmental_evidence_id=hotspot.environmental_evidence_id,
                context_evidence_id=context_evidence_id(
                    day3_sha256=day3_sha256,
                    query_sha256=query_sha256,
                    hotspot=hotspot,
                ),
                representative_latitude=hotspot.latitude,
                representative_longitude=hotspot.longitude,
                radius_meters=radius_meters,
                category_counts=counts,
                nearby_places=tuple(nearby),
                category_status=dict(statuses),
            )
        )

    return tuple(sorted(results, key=lambda item: item.hotspot_rank))


def raw_cache_fingerprint(*, query_sha256: str, endpoint_family: str = "overpass-global-v2") -> str:
    raw = f"{endpoint_family}|{query_sha256}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
