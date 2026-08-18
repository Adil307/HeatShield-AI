from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class ContextPlace:
    osm_type: str
    osm_id: int
    name: str | None
    category: str
    subcategory: str
    latitude: float
    longitude: float
    tags: dict[str, str]

    @property
    def osm_ref(self) -> str:
        return f"{self.osm_type}/{self.osm_id}"

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["osm_ref"] = self.osm_ref
        return payload


@dataclass(frozen=True, slots=True)
class NearbyContextPlace:
    place: ContextPlace
    distance_meters: float

    def to_dict(self) -> dict:
        return {
            "place": self.place.to_dict(),
            "distance_meters": self.distance_meters,
        }


@dataclass(frozen=True, slots=True)
class HotspotContext:
    hotspot_rank: int
    tile_id: int | str
    thermal_evidence_id: str
    environmental_evidence_id: str
    context_evidence_id: str
    representative_latitude: float
    representative_longitude: float
    radius_meters: float
    category_counts: dict[str, int]
    nearby_places: tuple[NearbyContextPlace, ...]

    def to_dict(self) -> dict:
        return {
            "hotspot_rank": self.hotspot_rank,
            "tile_id": self.tile_id,
            "thermal_evidence_id": self.thermal_evidence_id,
            "environmental_evidence_id": self.environmental_evidence_id,
            "context_evidence_id": self.context_evidence_id,
            "representative_latitude": self.representative_latitude,
            "representative_longitude": self.representative_longitude,
            "radius_meters": self.radius_meters,
            "category_counts": dict(self.category_counts),
            "nearby_place_count": len(self.nearby_places),
            "nearby_places": [item.to_dict() for item in self.nearby_places],
        }
