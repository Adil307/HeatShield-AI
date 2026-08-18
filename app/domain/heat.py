from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TemperatureTile:
    tile_id: int | str
    average_temperature: float
    min_temperature: float | None
    max_temperature: float | None
    geometry: dict[str, Any]
    source_index: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TemperatureStats:
    minimum: float
    maximum: float
    mean: float
    population_standard_deviation: float
    sample_standard_deviation: float | None
    count: int

    @property
    def standard_deviation(self) -> float:
        """AOI-population standard deviation used for internal z-scores."""
        return self.population_standard_deviation

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HotspotCandidate:
    rank: int
    tile_id: int | str
    average_temperature: float
    z_score: float
    relative_intensity: float
    relative_band: str
    evidence_id: str
    geometry: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
