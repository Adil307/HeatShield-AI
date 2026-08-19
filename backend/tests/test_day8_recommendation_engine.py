from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.day7_artifact import Day7ArtifactError, load_day7_source
from app.services.recommendation_engine import RecommendationEngineError, build_recommendations
from app.services.recommendation_guard import RecommendationGuardError, validate_controlled_recommendation


ROOT = Path(__file__).resolve().parents[1]
DAY7 = ROOT / "data/processed/day7_explainability_guard.json"
DAY6 = ROOT / "data/processed/day6_site_evidence_layer.json"
DAY5 = ROOT / "data/processed/day5_planning_priority.json"
DAY44 = ROOT / "data/processed/day44_scenario_replay.json"
CATALOG = ROOT / "config/day8_action_catalog.json"


def _payload() -> dict:
    return build_recommendations(
        day7_path=DAY7,
        catalog_path=CATALOG,
        day6_path=DAY6,
        day5_path=DAY5,
        day44_path=DAY44,
    )


def test_day7_loader_accepts_verified_chain() -> None:
    source = load_day7_source(DAY7, day6_path=DAY6, day5_path=DAY5, day44_path=DAY44)
    assert source.payload["schema_version"] == "heatshield.day7.explainability_guard.v1"
    assert len(source.packets) == 3
    assert len(source.sha256) == 64


def test_day7_loader_rejects_wrong_schema(tmp_path: Path) -> None:
    payload = json.loads(DAY7.read_text(encoding="utf-8"))
    payload["schema_version"] = "wrong"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(Day7ArtifactError):
        load_day7_source(path)


def test_day7_loader_rejects_underlying_provenance_mismatch(tmp_path: Path) -> None:
    fake = tmp_path / "day6.json"
    fake.write_text("{}", encoding="utf-8")
    with pytest.raises(Day7ArtifactError, match="SHA-256"):
        load_day7_source(DAY7, day6_path=fake)


def test_catalog_builds_deterministic_recommendations_for_all_hotspots() -> None:
    payload = _payload()
    assert payload["schema_version"] == "heatshield.day8.controlled_recommendations.v1"
    assert payload["summary"]["hotspots_processed"] == 3
    assert payload["summary"]["recommendations_generated"] >= 12
    assert payload["summary"]["new_provider_api_calls"] == 0
    assert payload["summary"]["new_llm_calls"] == 0


def test_current_unknowns_trigger_verification_not_absence_claims() -> None:
    payload = _payload()
    action_ids = {
        rec["action_id"]
        for hotspot in payload["hotspots"]
        for rec in hotspot["recommendations"]
    }
    assert "verify_operational_vulnerability_factors" in action_ids
    assert "verify_adaptive_heat_controls" in action_ids
    text = " ".join(
        rec["recommendation"].lower()
        for hotspot in payload["hotspots"]
        for rec in hotspot["recommendations"]
    )
    assert "controls are absent" not in text
    assert "no water" not in text


def test_public_context_triggers_shade_assessment() -> None:
    payload = _payload()
    for hotspot in payload["hotspots"]:
        ids = {rec["action_id"] for rec in hotspot["recommendations"]}
        assert "assess_public_shade_recovery_options" in ids
        assert "assess_tree_vegetation_shade_feasibility" in ids


def test_worker_action_is_explicitly_conditional() -> None:
    payload = _payload()
    for hotspot in payload["hotspots"]:
        rec = next(item for item in hotspot["recommendations"] if item["action_id"] == "review_worker_heat_practices_if_applicable")
        assert rec["status"] == "conditional_requires_operator_scope"
        assert rec["recommendation"].startswith("If outdoor or hot-environment work occurs")


def test_actions_are_sorted_by_catalog_priority_tier() -> None:
    payload = _payload()
    order = {"P1": 0, "P2": 1, "P3": 2}
    for hotspot in payload["hotspots"]:
        tiers = [order[rec["priority_tier"]] for rec in hotspot["recommendations"]]
        assert tiers == sorted(tiers)


def test_recommendation_ids_are_deterministic() -> None:
    a = _payload()
    b = _payload()
    ids_a = [rec["recommendation_id"] for h in a["hotspots"] for rec in h["recommendations"]]
    ids_b = [rec["recommendation_id"] for h in b["hotspots"] for rec in h["recommendations"]]
    assert ids_a == ids_b
    assert len(ids_a) == len(set(ids_a))


def test_every_action_has_registered_authoritative_basis_and_guard_approval() -> None:
    payload = _payload()
    registry = payload["source_registry"]
    for hotspot in payload["hotspots"]:
        for rec in hotspot["recommendations"]:
            assert rec["guard_status"] == "approved_controlled_catalog_action"
            assert rec["authoritative_basis"]
            assert all(source in registry for source in rec["authoritative_basis"])


def test_guard_rejects_catalog_text_tampering() -> None:
    payload = _payload()
    rec = copy.deepcopy(payload["hotspots"][0]["recommendations"][0])
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    action = next(item for item in catalog["actions"] if item["action_id"] == rec["action_id"])
    rec["recommendation"] = "This area is safe."
    with pytest.raises(RecommendationGuardError):
        validate_controlled_recommendation(rec, catalog_action=action, source_registry=catalog["source_registry"])


def test_guard_rejects_unregistered_source() -> None:
    payload = _payload()
    rec = copy.deepcopy(payload["hotspots"][0]["recommendations"][0])
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    action = copy.deepcopy(next(item for item in catalog["actions"] if item["action_id"] == rec["action_id"]))
    rec["authoritative_basis"] = ["made_up_source"]
    action["authoritative_basis"] = ["made_up_source"]
    with pytest.raises(RecommendationGuardError):
        validate_controlled_recommendation(rec, catalog_action=action, source_registry=catalog["source_registry"])


def test_catalog_rejects_unknown_authoritative_source(tmp_path: Path) -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    catalog["actions"][0]["authoritative_basis"] = ["missing"]
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog), encoding="utf-8")
    with pytest.raises(RecommendationEngineError, match="unknown source"):
        build_recommendations(day7_path=DAY7, catalog_path=path)


def test_no_medical_probability_current_heat_people_exposed_or_effect_size_claims() -> None:
    payload = _payload()
    text = json.dumps(payload, ensure_ascii=False).lower()
    assert "medical risk probability =" not in text
    assert "people are exposed" not in text
    assert "current heat is" not in text
    assert "will reduce by" not in text
    assert payload["policy"]["medical_or_clinical_advice"] is False


def test_trigger_evidence_is_traceable_to_day7_ledger() -> None:
    payload = _payload()
    day7 = json.loads(DAY7.read_text(encoding="utf-8"))
    packet_by_rank = {packet["hotspot_rank"]: packet for packet in day7["packets"]}
    for hotspot in payload["hotspots"]:
        ledger = {item["key"]: item for item in packet_by_rank[hotspot["hotspot_rank"]]["evidence_ledger"]}
        for rec in hotspot["recommendations"]:
            for evidence in rec["trigger_evidence"]:
                assert evidence["key"] in ledger
                assert evidence["classification"] == ledger[evidence["key"]]["classification"]
                assert evidence["value"] == ledger[evidence["key"]]["value"]


def test_api_recommendations_routes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import routes_decision

    artifact = _payload()
    path = tmp_path / "day8.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    monkeypatch.setattr(routes_decision, "DAY8_PATH", path)
    client = TestClient(app)

    response = client.get("/api/v1/decision/recommendations")
    assert response.status_code == 200
    assert response.json()["schema_version"] == "heatshield.day8.controlled_recommendations.v1"

    rank = artifact["hotspots"][0]["hotspot_rank"]
    response = client.get(f"/api/v1/decision/recommendations/{rank}")
    assert response.status_code == 200
    assert response.json()["hotspot_rank"] == rank


def test_api_unknown_hotspot_returns_404(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import routes_decision

    artifact = _payload()
    path = tmp_path / "day8.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    monkeypatch.setattr(routes_decision, "DAY8_PATH", path)
    client = TestClient(app)
    response = client.get("/api/v1/decision/recommendations/999")
    assert response.status_code == 404
