from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ai.claim_guard import evaluate_structured_claim, screen_natural_language
from app.main import app
from app.services.explainability import ExplainabilityError, build_explainability_packets


ROOT = Path(__file__).resolve().parents[1]
DAY6 = ROOT / "data/processed/day6_site_evidence_layer.json"
DAY5 = ROOT / "data/processed/day5_planning_priority.json"
DAY44 = ROOT / "data/processed/day44_scenario_replay.json"
DAY7 = ROOT / "data/processed/day7_explainability_guard.json"


def packets():
    return build_explainability_packets(day6_path=DAY6, day5_path=DAY5, day44_path=DAY44)


def packet_dict():
    return packets()[0].to_dict()


def test_day7_builds_one_packet_per_day6_hotspot():
    built = packets()
    d6 = json.loads(DAY6.read_text(encoding="utf-8"))
    assert len(built) == len(d6["results"])
    assert {p.hotspot_rank for p in built} == {item["hotspot_rank"] for item in d6["results"]}


def test_contributions_exactly_reconstruct_priority_score():
    for packet in packets():
        total = round(sum(item.weighted_points for item in packet.contributions), 4)
        assert total == pytest.approx(packet.pre_adaptation_priority_score, abs=0.0002)


def test_packets_preserve_explicit_scenario_scope_and_temporal_gap():
    for packet in packets():
        assert packet.scenario_scope == "historical_hazard_current_context_scenario_replay"
        assert packet.temporal_gap_days > 700
        assert "recurred" in packet.scenario_statement


def test_unknown_operational_evidence_stays_unknown_and_adjusted_priority_withheld():
    for packet in packets():
        assert "verified_operational_vulnerability" in packet.unknowns
        assert "verified_adaptive_capacity" in packet.unknowns
        assert "evidence_adjusted_planning_priority" in packet.withheld
        assert packet.evidence_adjusted_priority_score is None


def test_medical_risk_is_always_withheld_in_ledger():
    for packet in packets():
        entry = next(x for x in packet.evidence_ledger if x.key == "medical_risk_probability")
        assert entry.classification == "withheld"
        assert entry.value is None
        assert entry.status == "never_produced"


def test_structured_guard_approves_exact_observed_metric():
    packet = packet_dict()
    heat = next(x for x in packet["evidence_ledger"] if x["key"] == "historical_heat_index_celsius")
    decision = evaluate_structured_claim(
        packet,
        {"claim_type": "metric_assertion", "metric_key": heat["key"], "claimed_value": heat["value"]},
    )
    assert decision.approved is True
    assert decision.reason_code == "metric_grounded"


def test_structured_guard_rejects_value_mismatch():
    packet = packet_dict()
    decision = evaluate_structured_claim(
        packet,
        {
            "claim_type": "metric_assertion",
            "metric_key": "pre_adaptation_planning_priority",
            "claimed_value": packet["pre_adaptation_priority_score"] + 1,
        },
    )
    assert decision.approved is False
    assert decision.reason_code == "value_mismatch"


def test_structured_guard_rejects_medical_probability_even_if_numeric_value_supplied():
    decision = evaluate_structured_claim(
        packet_dict(),
        {"claim_type": "metric_assertion", "metric_key": "medical_risk_probability", "claimed_value": 70},
    )
    assert decision.approved is False
    assert decision.reason_code == "forbidden_metric"


def test_structured_guard_allows_unknown_status_but_not_unknown_value():
    packet = packet_dict()
    status_decision = evaluate_structured_claim(
        packet,
        {"claim_type": "status_assertion", "metric_key": "verified_operational_vulnerability", "status": "unknown"},
    )
    value_decision = evaluate_structured_claim(
        packet,
        {"claim_type": "metric_assertion", "metric_key": "verified_operational_vulnerability", "claimed_value": 0},
    )
    assert status_decision.approved is True
    assert value_decision.approved is False
    assert value_decision.reason_code == "value_unavailable"


def test_text_guard_rejects_historical_as_current_claim():
    decision = screen_natural_language("The current heat at this hotspot is 38.2 C.")
    assert decision.approved is False
    assert decision.reason_code == "historical_as_current"


def test_text_guard_rejects_mapped_context_as_people_exposure():
    decision = screen_natural_language("302 people are exposed around this hotspot.")
    assert decision.approved is False
    assert decision.reason_code == "mapped_objects_as_people"


def test_text_guard_never_directly_approves_free_text():
    decision = screen_natural_language("The planning priority is high because mapped context is elevated.")
    assert decision.approved is False
    assert decision.decision == "requires_structured_grounding"


def test_lineage_hash_mismatch_fails_closed(tmp_path: Path):
    bad_day5 = tmp_path / "day5.json"
    payload = json.loads(DAY5.read_text(encoding="utf-8"))
    payload["priority_results"][0]["pre_adaptation_priority_score"] += 0.01
    bad_day5.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ExplainabilityError, match="Day 6 -> Day 5 SHA-256 provenance mismatch"):
        build_explainability_packets(day6_path=DAY6, day5_path=bad_day5, day44_path=DAY44)


def test_tile_identity_mismatch_fails_closed(tmp_path: Path):
    # To reach identity validation while retaining provenance, create a modified chain whose hashes agree.
    day44_payload = json.loads(DAY44.read_text(encoding="utf-8"))
    day44_payload["hotspots"][0]["tile_id"] = "tampered"
    day44_path = tmp_path / "day44.json"
    day44_path.write_text(json.dumps(day44_payload), encoding="utf-8")

    import hashlib
    day44_sha = hashlib.sha256(day44_path.read_bytes()).hexdigest()

    day5_payload = json.loads(DAY5.read_text(encoding="utf-8"))
    day5_payload["source"]["day44_artifact_sha256"] = day44_sha
    day5_path = tmp_path / "day5.json"
    day5_path.write_text(json.dumps(day5_payload), encoding="utf-8")
    day5_sha = hashlib.sha256(day5_path.read_bytes()).hexdigest()

    day6_payload = json.loads(DAY6.read_text(encoding="utf-8"))
    day6_payload["source"]["day5_artifact_sha256"] = day5_sha
    day6_payload["source"]["day5_source_day44_sha256"] = day44_sha
    day6_path = tmp_path / "day6.json"
    day6_path.write_text(json.dumps(day6_payload), encoding="utf-8")

    with pytest.raises(ExplainabilityError, match="Tile identity mismatch"):
        build_explainability_packets(day6_path=day6_path, day5_path=day5_path, day44_path=day44_path)


def test_day7_api_returns_packet_and_guard_decision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import app.api.routes_decision as routes_decision

    packet_rows = [item.to_dict() for item in packets()]
    artifact_path = tmp_path / "day7.json"
    artifact_path.write_text(
        json.dumps({"schema_version": "heatshield.day7.explainability_guard.v1", "packets": packet_rows}),
        encoding="utf-8",
    )
    monkeypatch.setattr(routes_decision, "DAY7_PATH", artifact_path)

    client = TestClient(app)
    rank = packet_rows[0]["hotspot_rank"]
    response = client.get(f"/api/v1/decision/explainability/{rank}")
    assert response.status_code == 200
    packet = response.json()
    guard = client.post(
        "/api/v1/decision/claim-guard/evaluate",
        json={
            "hotspot_rank": rank,
            "claim_type": "metric_assertion",
            "metric_key": "pre_adaptation_planning_priority",
            "claimed_value": packet["pre_adaptation_priority_score"],
        },
    )
    assert guard.status_code == 200
    assert guard.json()["approved"] is True


def test_structured_guard_approves_only_exact_scenario_statement():
    packet = packet_dict()
    good = evaluate_structured_claim(
        packet,
        {"claim_type": "scenario_statement", "statement": packet["scenario_statement"]},
    )
    bad = evaluate_structured_claim(
        packet,
        {"claim_type": "scenario_statement", "statement": "This is current live heat."},
    )
    assert good.approved is True
    assert bad.approved is False
    assert bad.reason_code == "scenario_scope_mismatch"
