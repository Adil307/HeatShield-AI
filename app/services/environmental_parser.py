from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.domain.environment import EnvironmentalObservation


class EnvironmentalValidationError(ValueError):
    """Raised when a completed environmental-parameters artifact is unusable."""


@dataclass(frozen=True, slots=True)
class ParsedEnvironmentalArtifact:
    source_path: str
    activity_id: str | None
    status: str
    observation: EnvironmentalObservation
    available_parameter_names: tuple[str, ...]


def _number(value: Any, *, field: str) -> float:
    if isinstance(value, bool):
        raise EnvironmentalValidationError(f"{field} must be numeric.")
    if isinstance(value, (int, float)):
        result = float(value)
    elif isinstance(value, str):
        try:
            result = float(value.strip())
        except ValueError as exc:
            raise EnvironmentalValidationError(f"{field} must be numeric.") from exc
    else:
        raise EnvironmentalValidationError(f"{field} must be numeric.")
    if not math.isfinite(result):
        raise EnvironmentalValidationError(f"{field} must be finite.")
    return result


def _optional_first_number(value: Any) -> float | None:
    if not isinstance(value, list) or not value:
        return None
    first = value[0]
    try:
        return _number(first, field="parameter value")
    except EnvironmentalValidationError:
        # The provider documents NUMBER_OR_SENTINEL for some environmental fields.
        # Unknown/sentinel values are represented as missing, never fabricated.
        return None


def parse_environmental_artifact(source: str | Path) -> ParsedEnvironmentalArtifact:
    source_path = Path(source)
    if not source_path.exists():
        raise EnvironmentalValidationError(f"Environmental artifact not found: {source_path}")

    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EnvironmentalValidationError(f"Invalid environmental JSON: {source_path}") from exc

    if not isinstance(payload, dict):
        raise EnvironmentalValidationError("Top-level provider response must be an object.")
    if payload.get("error") is True:
        raise EnvironmentalValidationError("Provider artifact reports error=true.")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise EnvironmentalValidationError("Provider response is missing object field 'data'.")

    status = str(data.get("status", ""))
    if status.lower() not in {"completed", "succeeded"}:
        raise EnvironmentalValidationError(f"Environmental activity is not completed: {status!r}")

    result = data.get("result")
    if not isinstance(result, dict):
        raise EnvironmentalValidationError("Provider response is missing object field 'data.result'.")

    locations = result.get("locations")
    if not isinstance(locations, list) or not locations:
        raise EnvironmentalValidationError("Environmental result contains no locations.")

    location = locations[0]
    if not isinstance(location, dict):
        raise EnvironmentalValidationError("Environmental location must be an object.")

    latitude = _number(location.get("lat"), field="location.lat")
    longitude = _number(location.get("lon"), field="location.lon")
    temperature = _number(location.get("temperature"), field="location.temperature")

    if not -90.0 <= latitude <= 90.0:
        raise EnvironmentalValidationError("location.lat is outside [-90, 90].")
    if not -180.0 <= longitude <= 180.0:
        raise EnvironmentalValidationError("location.lon is outside [-180, 180].")

    parameters = location.get("parameters")
    if parameters is None:
        parameters = {}
    if not isinstance(parameters, dict):
        raise EnvironmentalValidationError("location.parameters must be an object.")

    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    timezone_name = metadata.get("timezone") if isinstance(metadata.get("timezone"), str) else None
    timestamps = metadata.get("timestamps") if isinstance(metadata.get("timestamps"), list) else []
    timestamp = timestamps[0] if timestamps and isinstance(timestamps[0], str) else None

    observation = EnvironmentalObservation(
        latitude=latitude,
        longitude=longitude,
        temperature_celsius=temperature,
        heat_index_celsius=_optional_first_number(parameters.get("heat_index_celsius")),
        apparent_temperature_celsius=_optional_first_number(
            parameters.get("apparent_temperature_celsius")
        ),
        wet_bulb_temperature_celsius=_optional_first_number(
            parameters.get("wet_bulb_temperature_celsius")
        ),
        relative_humidity_percent=_optional_first_number(
            parameters.get("relative_humidity_percent")
        ),
        timezone=timezone_name,
        timestamp=timestamp,
    )

    if all(
        value is None
        for value in (
            observation.heat_index_celsius,
            observation.apparent_temperature_celsius,
            observation.wet_bulb_temperature_celsius,
        )
    ):
        raise EnvironmentalValidationError(
            "No core thermal-stress parameter (heat index, apparent temperature, wet bulb) "
            "was available in the completed response."
        )

    return ParsedEnvironmentalArtifact(
        source_path=str(source_path),
        activity_id=(data.get("activity_id") if isinstance(data.get("activity_id"), str) else None),
        status=status,
        observation=observation,
        available_parameter_names=tuple(sorted(str(name) for name in parameters.keys())),
    )
