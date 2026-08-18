import pytest
from pydantic import ValidationError

from app.schemas.fortyguard import HeatmapRequest


def base_payload():
    return {
        "polygon_aoi": {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [71.5150, 34.0100],
                        [71.5250, 34.0100],
                        [71.5250, 34.0180],
                        [71.5150, 34.0180],
                        [71.5150, 34.0100],
                    ]],
                },
            }],
        },
        "date_time": {
            "start_date": "2026-08-18",
            "start_time": "14:00",
            "filter_type": 1,
        },
        "granularity": 100,
        "analytic_type": "tcm",
    }


def test_valid_tcm_request():
    req = HeatmapRequest.model_validate(base_payload())
    payload = req.to_provider_payload()

    assert payload["analytic_type"] == "tcm"
    assert payload["granularity"] == 100
    assert "threshold" not in payload
    assert "direction" not in payload


def test_exceedance_keeps_threshold_and_direction():
    data = base_payload()
    data["analytic_type"] = "exceedance"
    data["threshold"] = 40.0
    data["direction"] = "above"

    payload = HeatmapRequest.model_validate(data).to_provider_payload()

    assert payload["threshold"] == 40.0
    assert payload["direction"] == "above"


def test_single_hour_requires_start_time():
    data = base_payload()
    data["date_time"].pop("start_time")

    with pytest.raises(ValidationError):
        HeatmapRequest.model_validate(data)


def test_only_documented_granularity_is_allowed():
    data = base_payload()
    data["granularity"] = 50

    with pytest.raises(ValidationError):
        HeatmapRequest.model_validate(data)
