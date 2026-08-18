from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class EnvironmentalObservation:
    latitude: float
    longitude: float
    temperature_celsius: float
    heat_index_celsius: float | None
    apparent_temperature_celsius: float | None
    wet_bulb_temperature_celsius: float | None
    relative_humidity_percent: float | None
    timezone: str | None
    timestamp: str | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class EnvironmentalEnrichment:
    hotspot_rank: int
    tile_id: int | str
    thermal_evidence_id: str
    environmental_evidence_id: str
    request_fingerprint: str
    representative_latitude: float
    representative_longitude: float
    observed: EnvironmentalObservation
    apparent_minus_air_celsius: float | None
    heat_index_minus_air_celsius: float | None
    core_metric_completeness: float

    def to_dict(self) -> dict:
        return asdict(self)
