from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pytest

from app.services.day3_artifact import Day3ContextInput
from app.services.operational_baseline import (
    OperationalBaselineError,
    cache_is_fresh,
    canonical_sha256,
    inspect_heatmap_cache,
    recent_completed_empty_heatmap,
    resolve_operational_request_candidates,
    resolve_operational_request_time,
    verify_observation_alignment,
    verify_observation_wall_clock_alignment,
)
from app.services.operational_context import build_current_context_query


def _hotspots() -> tuple[Day3ContextInput, ...]:
    return (
        Day3ContextInput(
            rank=1,
            tile_id=149,
            thermal_evidence_id="hs_thermal_a",
            environmental_evidence_id="hs_env_a",
            latitude=40.717539,
            longitude=-74.003871,
            observed_timestamp="2026-08-18T16:00:00-04:00",
        ),
        Day3ContextInput(
            rank=2,
            tile_id=137,
            thermal_evidence_id="hs_thermal_b",
            environmental_evidence_id="hs_env_b",
            latitude=40.716656,
            longitude=-74.003884,
            observed_timestamp="2026-08-18T16:00:00-04:00",
        ),
    )


def test_resolve_operational_request_time_uses_previous_local_hour() -> None:
    now_utc = datetime(2026, 8, 18, 21, 40, tzinfo=timezone.utc)
    resolved = resolve_operational_request_time(
        now_utc=now_utc,
        timezone_name="America/New_York",
        lag_hours=1,
    )
    assert resolved.start_date == "2026-08-18"
    assert resolved.start_time == "16:00"
    assert resolved.expected_utc == datetime(2026, 8, 18, 20, 0, tzinfo=timezone.utc)


def test_operational_time_allows_24_hour_fallback() -> None:
    now_utc = datetime(2026, 8, 18, 21, 40, tzinfo=timezone.utc)
    resolved = resolve_operational_request_time(
        now_utc=now_utc,
        timezone_name="America/New_York",
        lag_hours=24,
    )
    assert resolved.start_date == "2026-08-17"
    assert resolved.start_time == "17:00"


def test_candidate_lags_are_deduplicated_and_ordered() -> None:
    now_utc = datetime(2026, 8, 18, 21, 40, tzinfo=timezone.utc)
    candidates = resolve_operational_request_candidates(
        now_utc=now_utc,
        timezone_name="America/New_York",
        primary_lag_hours=1,
        fallback_lag_hours=24,
    )
    assert [lag for lag, _ in candidates] == [1, 24]


def test_operational_time_handles_winter_offset() -> None:
    now_utc = datetime(2026, 1, 15, 18, 15, tzinfo=timezone.utc)
    resolved = resolve_operational_request_time(
        now_utc=now_utc,
        timezone_name="America/New_York",
        lag_hours=1,
    )
    assert resolved.start_time == "12:00"
    assert resolved.expected_utc == datetime(2026, 1, 15, 17, 0, tzinfo=timezone.utc)


def test_rejects_invalid_lag() -> None:
    with pytest.raises(OperationalBaselineError):
        resolve_operational_request_time(
            now_utc=datetime.now(timezone.utc),
            timezone_name="America/New_York",
            lag_hours=0,
        )


def test_observation_alignment_accepts_equivalent_offset_timestamp() -> None:
    skew = verify_observation_alignment(
        observed_timestamp="2026-08-18T16:00:00-04:00",
        expected_utc=datetime(2026, 8, 18, 20, 0, tzinfo=timezone.utc),
    )
    assert skew == 0


def test_wall_clock_alignment_accepts_provider_fixed_offset() -> None:
    # Provider offset is retained as truth; the requested 16:00 wall-clock hour still matches.
    skew = verify_observation_wall_clock_alignment(
        observed_timestamp="2026-08-18T16:00:00-05:00",
        requested_date="2026-08-18",
        requested_time="16:00",
    )
    assert skew == 0


def test_wall_clock_alignment_rejects_wrong_hour() -> None:
    with pytest.raises(OperationalBaselineError):
        verify_observation_wall_clock_alignment(
            observed_timestamp="2026-08-18T15:00:00-05:00",
            requested_date="2026-08-18",
            requested_time="16:00",
        )


def test_observation_alignment_rejects_wrong_hour() -> None:
    with pytest.raises(OperationalBaselineError):
        verify_observation_alignment(
            observed_timestamp="2026-08-18T15:00:00-04:00",
            expected_utc=datetime(2026, 8, 18, 20, 0, tzinfo=timezone.utc),
        )


def _write_heatmap(path, *, features):
    path.write_text(
        json.dumps(
            {
                "data": {
                    "activity_id": "activity-1",
                    "status": "Completed",
                    "result": {
                        "map_data": {"type": "FeatureCollection", "features": features},
                        "stats_data": {},
                    },
                }
            }
        ),
        encoding="utf-8",
    )


def test_completed_empty_heatmap_is_negative_cache_not_usable(tmp_path) -> None:
    path = tmp_path / "heatmap_empty.json"
    _write_heatmap(path, features=[])
    inspected = inspect_heatmap_cache(path)
    assert inspected.state == "completed_empty"
    assert inspected.feature_count == 0
    assert inspected.activity_id == "activity-1"


def test_nonempty_heatmap_cache_is_usable(tmp_path) -> None:
    path = tmp_path / "heatmap_ok.json"
    _write_heatmap(path, features=[{"type": "Feature"}])
    inspected = inspect_heatmap_cache(path)
    assert inspected.state == "usable"
    assert inspected.feature_count == 1


def test_recent_empty_heatmap_triggers_backoff(tmp_path) -> None:
    path = tmp_path / "heatmap_recent.json"
    _write_heatmap(path, features=[])
    now = datetime.now(timezone.utc)
    os.utime(path, (now.timestamp(), now.timestamp()))
    assert recent_completed_empty_heatmap(tmp_path, now_utc=now, window_minutes=180) == path


def test_old_empty_heatmap_does_not_trigger_backoff(tmp_path) -> None:
    path = tmp_path / "heatmap_old.json"
    _write_heatmap(path, features=[])
    old = datetime(2026, 8, 17, 0, 0, tzinfo=timezone.utc)
    os.utime(path, (old.timestamp(), old.timestamp()))
    now = datetime(2026, 8, 18, 21, 40, tzinfo=timezone.utc)
    assert recent_completed_empty_heatmap(tmp_path, now_utc=now, window_minutes=180) is None


def test_current_context_query_omits_historical_date_and_uses_one_bbox() -> None:
    plan = build_current_context_query(_hotspots(), radius_meters=500)
    assert '[date:' not in plan.query
    assert '[bbox:' in plan.query
    assert 'amenity"="hospital' in plan.query
    assert 'highway"="bus_stop' in plan.query
    assert 'out center tags qt;' in plan.query
    assert len(plan.query_sha256) == 64


def test_canonical_sha256_is_order_independent() -> None:
    first = canonical_sha256({"a": 1, "b": {"x": 2}})
    second = canonical_sha256({"b": {"x": 2}, "a": 1})
    assert first == second
    assert len(first) == 64


def test_osm_cache_freshness_uses_wrapper_timestamp(tmp_path) -> None:
    path = tmp_path / "osm.json"
    path.write_text(
        json.dumps({"fetched_at_utc": "2026-08-18T21:20:00+00:00", "response": {}}),
        encoding="utf-8",
    )
    now = datetime(2026, 8, 18, 21, 40, tzinfo=timezone.utc)
    assert cache_is_fresh(path, ttl_minutes=30, now_utc=now) is True
    assert cache_is_fresh(path, ttl_minutes=10, now_utc=now) is False
