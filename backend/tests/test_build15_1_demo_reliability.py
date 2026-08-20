from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "dashboard"


def read(name: str) -> str:
    return (FRONTEND / name).read_text(encoding="utf-8")


def test_build15_1_fixes_stale_scenario_lock_banner() -> None:
    html = read("index.html")
    js = read("app.js")
    assert ".scenario-lock.hidden,.scenario-ready.hidden,.scenario-restore.hidden{display:none!important;}" in html
    assert "locked.classList.toggle('hidden',supported)" in js
    assert "ready.classList.toggle('hidden',!supported)" in js


def test_build15_1_persists_verified_live_baseline_across_refresh_in_same_tab() -> None:
    js = read("app.js")
    assert 'LIVE_DECISION_SESSION_KEY = "heatshield.build15_1.live_decision_state.v1"' in js
    assert "sessionStorage.setItem" in js
    assert "sessionStorage.getItem" in js
    assert "persistLiveDecisionState()" in js
    assert "restorePersistedLiveDecisionState()" in js
    assert "clearPersistedLiveDecisionState()" in js
    assert "live_context_priority" in js
    assert "live_context_request" in js


def test_build15_1_restores_scenario_result_without_new_provider_or_llm_contract() -> None:
    js = read("app.js")
    html = read("index.html")
    assert "live_scenario:state.liveScenario||null" in js
    assert "renderScenarioResult(state.liveScenario,{restored:true})" in js
    assert "Verified baseline restored from this browser tab." in html
    assert "Zero FortyGuard calls" in js
    assert "Zero LLM calls" in js


def test_build15_1_uses_calendar_neutral_judge_facing_labels() -> None:
    html = read("index.html")
    js = read("app.js")
    for phrase in [
        "Live Evidence-to-Scenario Workspace",
        "Live Decision Readiness",
        "Controlled Context Verification",
        "Live Grounded Copilot",
        "CONTROLLED WHAT-IF COMPARISON",
    ]:
        assert phrase in html
    # Build history remains in filenames/tests/docs; the judge-facing workflow no longer
    # presents internal build counters as calendar days.
    for phrase in [
        "Day 12 · Live Decision Readiness",
        "Day 13 · Controlled Context Verification",
        "Day 14 · Live Grounded Copilot",
        "Day 15 · Scenario Studio",
        "DAY 15 · CONTROLLED WHAT-IF COMPARISON",
    ]:
        assert phrase not in html
    assert 'scope:"Scenario estimate · Controlled assumptions"' in js


def test_build15_1_presents_context_source_as_operator_evidence_reference() -> None:
    html = read("index.html")
    assert "Operator evidence reference:" in html
    assert "Source type: Authorized operator input" in html
    assert "app.js?v=15.1.0" in html
