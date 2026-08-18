from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from app.services.heatmap_parser import HeatmapValidationError, parse_heatmap_artifact
from app.services.hotspot_detector import detect_relative_hotspots


def polygon(x: float) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [
            [[x, 0.0], [x + 0.1, 0.0], [x + 0.1, 0.1], [x, 0.1], [x, 0.0]]
        ],
    }


def write_artifact(
    path: Path,
    temperatures: list[float],
    *,
    duplicate: bool = False,
    provider_mean_offset: float = 0.0,
    provider_std_basis: str = "sample",
) -> None:
    mean = sum(temperatures) / len(temperatures)
    population_variance = sum((value - mean) ** 2 for value in temperatures) / len(temperatures)
    population_std = math.sqrt(population_variance)

    if len(temperatures) > 1:
        sample_variance = sum((value - mean) ** 2 for value in temperatures) / (len(temperatures) - 1)
        sample_std = math.sqrt(sample_variance)
    else:
        sample_std = 0.0

    provider_std = sample_std if provider_std_basis == "sample" else population_std
    features = []

    for index, temperature in enumerate(temperatures):
        tile_id = 0 if duplicate and index == len(temperatures) - 1 else index
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "tile_id": tile_id,
                    "average_temperature": temperature,
                    "min_temperature": temperature,
                    "max_temperature": temperature,
                },
                "geometry": polygon(float(index)),
            }
        )

    payload = {
        "error": False,
        "data": {
            "activity_id": "test-activity",
            "status": "Completed",
            "result": {
                "map_data": {"type": "FeatureCollection", "features": features},
                "stats_data": {
                    "temperature_stats": {
                        "minimum": min(temperatures),
                        "maximum": max(temperatures),
                        "mean": mean + provider_mean_offset,
                        "standard_deviation": provider_std,
                    }
                },
            },
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_parser_validates_real_provider_sample_stddev_convention(tmp_path: Path) -> None:
    path = tmp_path / "heatmap.json"
    write_artifact(path, [30.0, 31.0, 32.0, 33.0], provider_std_basis="sample")

    parsed = parse_heatmap_artifact(path)

    assert len(parsed.tiles) == 4
    assert parsed.computed_stats.minimum == 30.0
    assert parsed.computed_stats.maximum == 33.0
    assert parsed.computed_stats.mean == 31.5
    assert parsed.provider_stddev_basis == "sample_n_minus_1"
    assert all(parsed.stats_match.values())


def test_parser_accepts_population_stddev_if_provider_convention_changes(tmp_path: Path) -> None:
    path = tmp_path / "heatmap.json"
    write_artifact(path, [30.0, 31.0, 32.0, 33.0], provider_std_basis="population")

    parsed = parse_heatmap_artifact(path)

    assert parsed.provider_stddev_basis == "population_n"
    assert parsed.stats_match["standard_deviation"] is True


def test_parser_rejects_duplicate_tile_ids(tmp_path: Path) -> None:
    path = tmp_path / "heatmap.json"
    write_artifact(path, [30.0, 31.0, 32.0], duplicate=True)

    with pytest.raises(HeatmapValidationError, match="Duplicate tile_id"):
        parse_heatmap_artifact(path)


def test_parser_rejects_empty_completed_heatmap(tmp_path: Path) -> None:
    path = tmp_path / "heatmap.json"
    payload = {
        "data": {
            "status": "Completed",
            "result": {
                "map_data": {"type": "FeatureCollection", "features": []},
                "stats_data": {},
            },
        }
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(HeatmapValidationError, match="zero GeoJSON features"):
        parse_heatmap_artifact(path)


def test_parser_rejects_unclosed_polygon(tmp_path: Path) -> None:
    path = tmp_path / "heatmap.json"
    write_artifact(path, [30.0])
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["data"]["result"]["map_data"]["features"][0]["geometry"]["coordinates"][0][-1] = [99.0, 99.0]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(HeatmapValidationError, match="not closed|Latitude out of range"):
        parse_heatmap_artifact(path)


def test_parser_exposes_provider_stat_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "heatmap.json"
    write_artifact(path, [30.0, 31.0, 32.0], provider_mean_offset=0.5)

    parsed = parse_heatmap_artifact(path)

    assert parsed.stats_match["mean"] is False
    assert parsed.stats_match["minimum"] is True


def test_hotspot_detector_returns_expected_top_k(tmp_path: Path) -> None:
    path = tmp_path / "heatmap.json"
    write_artifact(path, [30.0, 31.0, 32.0, 33.0, 34.0, 35.0, 36.0, 37.0, 38.0, 39.0])
    parsed = parse_heatmap_artifact(path)

    analysis = detect_relative_hotspots(
        parsed.tiles,
        parsed.computed_stats,
        source_sha256="a" * 64,
        top_ratio=0.20,
    )

    assert analysis.selected_count == 2
    assert [candidate.average_temperature for candidate in analysis.candidates] == [39.0, 38.0]
    assert analysis.cutoff_temperature == 38.0


def test_hotspot_detector_is_deterministic_for_ties(tmp_path: Path) -> None:
    path = tmp_path / "heatmap.json"
    write_artifact(path, [35.0, 35.0, 35.0, 35.0])
    parsed = parse_heatmap_artifact(path)

    first = detect_relative_hotspots(
        parsed.tiles,
        parsed.computed_stats,
        source_sha256="b" * 64,
        top_ratio=0.50,
    )
    second = detect_relative_hotspots(
        parsed.tiles,
        parsed.computed_stats,
        source_sha256="b" * 64,
        top_ratio=0.50,
    )

    assert [c.tile_id for c in first.candidates] == [0, 1]
    assert [c.tile_id for c in first.candidates] == [c.tile_id for c in second.candidates]
    assert all(c.z_score == 0.0 for c in first.candidates)
