from __future__ import annotations

import json

import pytest

from app.services.day5_artifact import Day5ArtifactError, Day5PriorityInput, load_day5_evidence_source
from app.services.site_evidence_engine import (
    ADAPTIVE_CAPACITY_LEVELS,
    VULNERABILITY_LEVELS,
    EvidenceProfile,
    SiteEvidenceError,
    build_unknown_profile,
    evidence_adjusted_score,
    load_evidence_profiles,
    modifier_sensitivity,
    score_site_evidence,
)


def _priority(rank: int = 1, score: float = 70.0) -> Day5PriorityInput:
    return Day5PriorityInput(
        hotspot_rank=rank,
        tile_id=100 + rank,
        priority_evidence_id=f"hs_priority_{rank:020d}",
        pre_adaptation_priority_score=score,
        pre_adaptation_priority_band="high_planning_priority",
    )


def _verified_factor(level: str, source_ref: str = "assessment-001") -> dict:
    return {
        "status": "verified",
        "level": level,
        "source_type": "site_assessment",
        "source_ref": source_ref,
        "observed_at": "2026-08-19T00:00:00+00:00",
        "notes": None,
    }


def _unknown_factor() -> dict:
    return {
        "status": "unknown",
        "level": None,
        "source_type": None,
        "source_ref": None,
        "observed_at": None,
        "notes": None,
    }


def _profile(rank: int = 1, *, complete: bool = True) -> EvidenceProfile:
    if complete:
        vulnerability = {
            "physical_exertion": _verified_factor("high"),
            "acclimatization_gap": _verified_factor("partial"),
            "heat_trapping_ppe_or_clothing": _verified_factor("some"),
        }
        adaptive = {
            "potable_water_access": _verified_factor("adequate"),
            "shaded_or_cooled_recovery": _verified_factor("partial"),
            "work_rest_controls": _verified_factor("adequate"),
            "heat_training_and_monitoring": _verified_factor("partial"),
        }
    else:
        vulnerability = {key: _unknown_factor() for key in VULNERABILITY_LEVELS}
        adaptive = {key: _unknown_factor() for key in ADAPTIVE_CAPACITY_LEVELS}
    return EvidenceProfile(
        hotspot_rank=rank,
        tile_id=100 + rank,
        profile_type="operational_worksite_v1",
        vulnerability=vulnerability,
        adaptive_capacity=adaptive,
    )


def _day5_artifact() -> dict:
    return {
        "schema_version": "heatshield.day5.planning_priority.v1",
        "scope": "scenario_planning_priority_not_medical_risk",
        "source": {"day44_artifact_sha256": "a" * 64},
        "priority_results": [
            {
                "hotspot_rank": 1,
                "tile_id": 101,
                "priority_evidence_id": "hs_priority_00000000000000000001",
                "pre_adaptation_priority_score": 70.0,
                "pre_adaptation_priority_band": "high_planning_priority",
            }
        ],
    }


def test_day5_loader_accepts_verified_schema(tmp_path):
    path = tmp_path / "day5.json"
    path.write_text(json.dumps(_day5_artifact()), encoding="utf-8")
    source = load_day5_evidence_source(path)
    assert source.priority_results[0].pre_adaptation_priority_score == 70.0


def test_day5_loader_rejects_medical_scope(tmp_path):
    payload = _day5_artifact()
    payload["scope"] = "medical_risk"
    path = tmp_path / "day5.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(Day5ArtifactError):
        load_day5_evidence_source(path)


def test_unknown_profile_does_not_unlock_adjusted_priority():
    result = score_site_evidence(_priority(), _profile(complete=False), day5_sha256="b" * 64)
    assert result.vulnerability_score is None
    assert result.adaptive_capacity_score is None
    assert result.evidence_adjusted_priority_score is None
    assert result.medical_risk_score is None
    assert result.vulnerability_completeness == 0.0
    assert result.adaptive_capacity_completeness == 0.0


def test_complete_verified_profile_unlocks_planning_adjustment_only():
    result = score_site_evidence(_priority(), _profile(complete=True), day5_sha256="b" * 64)
    assert result.vulnerability_score == pytest.approx((100 + 50 + 50) / 3, abs=1e-4)
    assert result.adaptive_capacity_score == pytest.approx((100 + 50 + 100 + 50) / 4, abs=1e-4)
    assert result.evidence_adjusted_priority_score is not None
    assert result.medical_risk_score is None
    assert result.evidence_complete is True


def test_adjustment_is_symmetric_and_bounded():
    high_v_low_a, adjustment = evidence_adjusted_score(
        pre_adaptation_priority_score=90,
        vulnerability_score=100,
        adaptive_capacity_score=0,
        modifier_strength=0.20,
    )
    low_v_high_a, _ = evidence_adjusted_score(
        pre_adaptation_priority_score=10,
        vulnerability_score=0,
        adaptive_capacity_score=100,
        modifier_strength=0.20,
    )
    assert high_v_low_a == 100.0
    assert adjustment == 20.0
    assert low_v_high_a == 0.0


def test_verified_evidence_requires_source_and_timestamp():
    profile = _profile(complete=True)
    bad = dict(profile.vulnerability["physical_exertion"])
    bad["source_ref"] = ""
    vulnerability = dict(profile.vulnerability)
    vulnerability["physical_exertion"] = bad
    broken = EvidenceProfile(
        hotspot_rank=profile.hotspot_rank,
        tile_id=profile.tile_id,
        profile_type=profile.profile_type,
        vulnerability=vulnerability,
        adaptive_capacity=profile.adaptive_capacity,
    )
    with pytest.raises(SiteEvidenceError):
        score_site_evidence(_priority(), broken, day5_sha256="b" * 64)


def test_unknown_evidence_cannot_carry_level():
    profile = _profile(complete=False)
    bad = dict(profile.vulnerability["physical_exertion"])
    bad["level"] = "high"
    vulnerability = dict(profile.vulnerability)
    vulnerability["physical_exertion"] = bad
    broken = EvidenceProfile(
        hotspot_rank=profile.hotspot_rank,
        tile_id=profile.tile_id,
        profile_type=profile.profile_type,
        vulnerability=vulnerability,
        adaptive_capacity=profile.adaptive_capacity,
    )
    with pytest.raises(SiteEvidenceError):
        score_site_evidence(_priority(), broken, day5_sha256="b" * 64)


def test_profile_identity_must_match_priority():
    with pytest.raises(SiteEvidenceError):
        score_site_evidence(_priority(rank=1), _profile(rank=2), day5_sha256="b" * 64)


def test_template_contains_all_required_factors():
    payload = build_unknown_profile([_priority()])
    item = payload["hotspots"][0]
    assert set(item["vulnerability"]) == set(VULNERABILITY_LEVELS)
    assert set(item["adaptive_capacity"]) == set(ADAPTIVE_CAPACITY_LEVELS)
    assert all(value["status"] == "unknown" for value in item["vulnerability"].values())


def test_load_evidence_profiles_rejects_duplicate_rank(tmp_path):
    payload = build_unknown_profile([_priority()])
    payload["hotspots"].append(dict(payload["hotspots"][0]))
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SiteEvidenceError):
        load_evidence_profiles(path)


def test_modifier_sensitivity_is_withheld_when_evidence_incomplete():
    priorities = [_priority(1, 70), _priority(2, 69)]
    profiles = {1: _profile(1, complete=False), 2: _profile(2, complete=False)}
    results = modifier_sensitivity(priorities, profiles, day5_sha256="c" * 64)
    assert len(results) == 3
    assert all(item.ranking is None for item in results)
    assert all(item.status == "withheld_incomplete_evidence" for item in results)


def test_modifier_sensitivity_computes_when_all_profiles_verified():
    priorities = [_priority(1, 70), _priority(2, 69)]
    profiles = {1: _profile(1, complete=True), 2: _profile(2, complete=True)}
    results = modifier_sensitivity(priorities, profiles, day5_sha256="c" * 64)
    assert len(results) == 3
    assert all(item.ranking is not None for item in results)
    assert all(item.status == "computed_complete_verified_evidence" for item in results)
