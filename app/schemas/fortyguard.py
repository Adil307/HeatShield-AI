from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class DateTimeConfig(BaseModel):
    start_date: str = Field(..., examples=["2026-08-18"])
    filter_type: Literal[1, 2, 3, 4]
    start_time: str | None = Field(default=None, examples=["14:00"])
    end_time: str | None = None
    end_date: str | None = None

    @model_validator(mode="after")
    def validate_filter_requirements(self):
        if self.filter_type in (1, 2) and not self.start_time:
            raise ValueError("start_time is required for filter_type 1 and 2")
        if self.filter_type == 2 and not self.end_time:
            raise ValueError("end_time is required for filter_type 2")
        if self.filter_type == 4 and not self.end_date:
            raise ValueError("end_date is required for filter_type 4")
        return self


class EnvironmentalDateTimeConfig(BaseModel):
    start_date: str = Field(..., examples=["2024-07-15"])
    filter_type: Literal[1, 2, 3]
    start_time: str | None = Field(default=None, examples=["14:00"])
    end_time: str | None = None
    end_date: str | None = None

    @model_validator(mode="after")
    def validate_filter_requirements(self):
        if self.filter_type in (1, 2) and not self.start_time:
            raise ValueError("start_time is required for environmental filter_type 1 and 2")
        if self.filter_type == 2 and not self.end_time:
            raise ValueError("end_time is required for environmental filter_type 2")
        return self


class Geometry(BaseModel):
    type: Literal["Polygon"] = "Polygon"
    coordinates: list[list[list[float]]]


class GeoJSONFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    properties: dict[str, Any] = Field(default_factory=dict)
    geometry: Geometry


class PolygonAOI(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[GeoJSONFeature] = Field(min_length=1)


class HeatmapRequest(BaseModel):
    polygon_aoi: PolygonAOI
    date_time: DateTimeConfig
    granularity: Literal[60, 80, 100] = 100
    analytic_type: Literal[
        "tcm",
        "time_of_measure",
        "exceedance",
        "persistence",
    ] = "tcm"
    threshold: float | None = None
    direction: Literal["above", "below"] | None = None

    def to_provider_payload(self) -> dict[str, Any]:
        payload = self.model_dump(exclude_none=True)

        if self.analytic_type not in ("exceedance", "persistence"):
            payload.pop("threshold", None)
            payload.pop("direction", None)

        return payload


class EnvironmentalParametersRequest(BaseModel):
    latitude: float
    longitude: float
    temperature: float
    date_time: EnvironmentalDateTimeConfig

    @model_validator(mode="after")
    def validate_finite_coordinates_and_temperature(self):
        values = {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "temperature": self.temperature,
        }
        for name, value in values.items():
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")

        if not -90.0 <= self.latitude <= 90.0:
            raise ValueError("latitude must be in [-90, 90]")
        if not -180.0 <= self.longitude <= 180.0:
            raise ValueError("longitude must be in [-180, 180]")
        return self

    def to_provider_payload(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)
