from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Iterable

from app.domain.heat import HotspotCandidate, TemperatureStats, TemperatureTile
from app.services.evidence import thermal_evidence_id


class HotspotDetectionError(ValueError):
    """Raised when hotspot configuration or input data is invalid."""


@dataclass(frozen=True, slots=True)
class HotspotAnalysis:
    method: str
    top_ratio: float
    selected_count: int
    total_tiles: int
    cutoff_temperature: float
    candidates: tuple[HotspotCandidate, ...]

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "top_ratio": self.top_ratio,
            "selected_count": self.selected_count,
            "total_tiles": self.total_tiles,
            "cutoff_temperature": self.cutoff_temperature,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


def _relative_band(z_score: float) -> str:
    if z_score >= 2.0:
        return "very_high_relative"
    if z_score >= 1.0:
        return "high_relative"
    if z_score >= 0.5:
        return "elevated_relative"
    return "hotspot_candidate"


def _relative_intensity(value: float, stats: TemperatureStats) -> float:
    span = stats.maximum - stats.minimum
    if span <= 0:
        return 0.0
    return (value - stats.minimum) / span


def detect_relative_hotspots(
    tiles: Iterable[TemperatureTile],
    stats: TemperatureStats,
    *,
    source_sha256: str,
    top_ratio: float = 0.10,
    min_hotspots: int = 1,
    max_hotspots: int = 50,
) -> HotspotAnalysis:
    if not (0.0 < top_ratio <= 1.0):
        raise HotspotDetectionError("top_ratio must be in the interval (0, 1].")
    if min_hotspots < 1:
        raise HotspotDetectionError("min_hotspots must be >= 1.")
    if max_hotspots < min_hotspots:
        raise HotspotDetectionError("max_hotspots must be >= min_hotspots.")
    if len(source_sha256) != 64:
        raise HotspotDetectionError("source_sha256 must be a 64-character SHA-256 hex digest.")

    tile_list = list(tiles)
    n = len(tile_list)
    if n == 0:
        raise HotspotDetectionError("Cannot detect hotspots from an empty tile collection.")

    requested = max(min_hotspots, math.ceil(n * top_ratio))
    k = min(n, max_hotspots, requested)

    # Keep only k elements in the heap. For exact temperature ties we keep the
    # earlier provider feature, making the result deterministic without a full sort.
    indexed = list(enumerate(tile_list))
    hottest_indexed = heapq.nlargest(
        k,
        indexed,
        key=lambda item: (item[1].average_temperature, -item[0]),
    )
    hottest_indexed.sort(key=lambda item: (-item[1].average_temperature, item[0]))

    candidates: list[HotspotCandidate] = []
    std = stats.population_standard_deviation

    for rank, (_, tile) in enumerate(hottest_indexed, start=1):
        z_score = 0.0 if std == 0 else (tile.average_temperature - stats.mean) / std
        candidates.append(
            HotspotCandidate(
                rank=rank,
                tile_id=tile.tile_id,
                average_temperature=tile.average_temperature,
                z_score=z_score,
                relative_intensity=_relative_intensity(tile.average_temperature, stats),
                relative_band=_relative_band(z_score),
                evidence_id=thermal_evidence_id(source_sha256, tile.tile_id),
                geometry=tile.geometry,
            )
        )

    return HotspotAnalysis(
        method="relative_top_k_temperature_v1",
        top_ratio=top_ratio,
        selected_count=k,
        total_tiles=n,
        cutoff_temperature=candidates[-1].average_temperature,
        candidates=tuple(candidates),
    )
