from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class OperationalBaselineError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OperationalRequestTime:
    timezone_name: str
    start_date: str
    start_time: str
    local_datetime: datetime
    expected_utc: datetime

    def to_dict(self) -> dict[str, str]:
        return {
            "timezone_name": self.timezone_name,
            "start_date": self.start_date,
            "start_time": self.start_time,
            "local_datetime": self.local_datetime.isoformat(),
            "expected_utc_estimate": self.expected_utc.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class HeatmapCacheInspection:
    state: Literal["usable", "completed_empty", "invalid"]
    feature_count: int | None
    activity_id: str | None


def resolve_operational_request_time(
    *,
    now_utc: datetime,
    timezone_name: str,
    lag_hours: int = 1,
) -> OperationalRequestTime:
    if now_utc.tzinfo is None:
        raise OperationalBaselineError("now_utc must be timezone-aware.")
    if not 1 <= lag_hours <= 72:
        raise OperationalBaselineError("lag_hours must be between 1 and 72.")

    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise OperationalBaselineError(f"Unknown IANA timezone: {timezone_name}") from exc

    local_now = now_utc.astimezone(zone)
    completed_local_hour = local_now.replace(minute=0, second=0, microsecond=0) - timedelta(
        hours=lag_hours
    )
    return OperationalRequestTime(
        timezone_name=timezone_name,
        start_date=completed_local_hour.strftime("%Y-%m-%d"),
        start_time=completed_local_hour.strftime("%H:%M"),
        local_datetime=completed_local_hour,
        expected_utc=completed_local_hour.astimezone(timezone.utc),
    )


def resolve_operational_request_candidates(
    *,
    now_utc: datetime,
    timezone_name: str,
    primary_lag_hours: int,
    fallback_lag_hours: int,
) -> tuple[tuple[int, OperationalRequestTime], ...]:
    lags = tuple(dict.fromkeys((primary_lag_hours, fallback_lag_hours)))
    return tuple(
        (
            lag,
            resolve_operational_request_time(
                now_utc=now_utc,
                timezone_name=timezone_name,
                lag_hours=lag,
            ),
        )
        for lag in lags
    )


def canonical_sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_aware_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OperationalBaselineError(f"Invalid provider timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise OperationalBaselineError("Provider timestamp is timezone-naive.")
    return parsed


def verify_observation_alignment(
    *,
    observed_timestamp: str | None,
    expected_utc: datetime,
    tolerance_seconds: float = 90.0,
) -> float:
    """Strict UTC alignment helper retained for sources with defined timezone semantics."""
    if not observed_timestamp:
        raise OperationalBaselineError("Environmental response contains no observed timestamp.")
    if expected_utc.tzinfo is None:
        raise OperationalBaselineError("expected_utc must be timezone-aware.")
    observed_utc = parse_aware_timestamp(observed_timestamp).astimezone(timezone.utc)
    skew_seconds = abs((observed_utc - expected_utc.astimezone(timezone.utc)).total_seconds())
    if skew_seconds > tolerance_seconds:
        raise OperationalBaselineError(
            "FortyGuard environmental timestamp does not align with the expected UTC hour: "
            f"observed={observed_utc.isoformat()} expected={expected_utc.isoformat()} "
            f"skew={skew_seconds:.1f}s"
        )
    return skew_seconds


def verify_observation_wall_clock_alignment(
    *,
    observed_timestamp: str | None,
    requested_date: str,
    requested_time: str,
    tolerance_seconds: float = 90.0,
) -> float:
    """Validate the provider's returned local wall-clock hour without inventing timezone semantics.

    FortyGuard documents the environmental result timestamp/offset, but its heatmap request docs only
    specify an HH:MM start_time and do not define an IANA timezone contract. Therefore the provider's
    returned aware timestamp is retained as the source of truth for offset/UTC conversion, while this
    check verifies that its local date/time matches the requested wall-clock date/time.
    """
    if not observed_timestamp:
        raise OperationalBaselineError("Environmental response contains no observed timestamp.")
    observed = parse_aware_timestamp(observed_timestamp)
    try:
        requested = datetime.strptime(f"{requested_date} {requested_time}", "%Y-%m-%d %H:%M")
    except ValueError as exc:
        raise OperationalBaselineError("Requested date/time is invalid.") from exc

    observed_wall_clock = observed.replace(tzinfo=None)
    skew_seconds = abs((observed_wall_clock - requested).total_seconds())
    if skew_seconds > tolerance_seconds:
        raise OperationalBaselineError(
            "FortyGuard environmental timestamp does not match the requested wall-clock hour: "
            f"observed={observed.isoformat()} requested={requested_date}T{requested_time} "
            f"skew={skew_seconds:.1f}s"
        )
    return skew_seconds


def inspect_heatmap_cache(path: str | Path) -> HeatmapCacheInspection:
    cache_path = Path(path)
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return HeatmapCacheInspection("invalid", None, None)
    if not isinstance(payload, dict):
        return HeatmapCacheInspection("invalid", None, None)

    data = payload.get("data")
    if not isinstance(data, dict):
        return HeatmapCacheInspection("invalid", None, None)
    activity_id = data.get("activity_id") if isinstance(data.get("activity_id"), str) else None
    status = str(data.get("status", "")).strip().lower()
    if status not in {"completed", "succeeded"}:
        return HeatmapCacheInspection("invalid", None, activity_id)

    result = data.get("result")
    if not isinstance(result, dict):
        return HeatmapCacheInspection("invalid", None, activity_id)
    map_data = result.get("map_data")
    if not isinstance(map_data, dict):
        return HeatmapCacheInspection("invalid", None, activity_id)
    features = map_data.get("features")
    if not isinstance(features, list):
        return HeatmapCacheInspection("invalid", None, activity_id)
    if not features:
        return HeatmapCacheInspection("completed_empty", 0, activity_id)
    return HeatmapCacheInspection("usable", len(features), activity_id)


def recent_completed_empty_heatmap(
    raw_dir: str | Path,
    *,
    now_utc: datetime,
    window_minutes: float,
) -> Path | None:
    if window_minutes <= 0:
        return None
    if now_utc.tzinfo is None:
        raise OperationalBaselineError("now_utc must be timezone-aware.")

    root = Path(raw_dir)
    newest: tuple[float, Path] | None = None
    for path in root.glob("heatmap_*.json"):
        if inspect_heatmap_cache(path).state != "completed_empty":
            continue
        try:
            modified_utc = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        age_seconds = (now_utc.astimezone(timezone.utc) - modified_utc).total_seconds()
        if not 0 <= age_seconds <= window_minutes * 60.0:
            continue
        if newest is None or modified_utc.timestamp() > newest[0]:
            newest = (modified_utc.timestamp(), path)
    return newest[1] if newest else None


def cache_is_fresh(
    path: str | Path,
    *,
    ttl_minutes: float,
    now_utc: datetime,
) -> bool:
    if ttl_minutes <= 0:
        return False
    cache_path = Path(path)
    if not cache_path.exists():
        return False
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, OSError):
        return False
    if not isinstance(payload, dict):
        return False
    fetched_at = payload.get("fetched_at_utc")
    if not isinstance(fetched_at, str):
        return False
    try:
        fetched = parse_aware_timestamp(fetched_at).astimezone(timezone.utc)
    except OperationalBaselineError:
        return False
    age_seconds = (now_utc.astimezone(timezone.utc) - fetched).total_seconds()
    return 0 <= age_seconds <= ttl_minutes * 60.0
