from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "dashboard"


def read(name: str) -> str:
    return (FRONTEND / name).read_text(encoding="utf-8")


def test_day11_exposes_separate_live_analysis_workspace() -> None:
    html = read("index.html")
    assert 'data-view="live"' in html
    assert 'id="liveAnalysisPanel"' in html
    assert 'id="liveAnalysisForm"' in html
    assert 'id="liveRunButton"' in html
    assert "Run a New Thermal Analysis" in html
    assert "temperature evidence and relative hottest tiles" in html


def test_day11_frontend_calls_heatshield_dashboard_contract_not_provider_directly() -> None:
    js = read("app.js")
    assert 'fetch("/api/v1/dashboard/live-analysis/status")' in js
    assert 'fetch("/api/v1/dashboard/live-analysis"' in js
    assert 'fetch("https://api.fortyguard.com' not in js
    assert 'analytic_type:"tcm"' in js
    assert 'filter_type:1' in js


def test_day11_live_mode_keeps_decision_scope_explicit() -> None:
    html = read("index.html")
    js = read("app.js")
    for phrase in ["planning priority", "medical risk", "occupancy"]:
        assert phrase in html.lower()
    assert "no planning priority or medical-risk score is inferred" in js
    assert "relative hottest tiles only" in js


def test_day11_updates_frontend_asset_version() -> None:
    assert "app.js?v=15.0.0" in read("index.html")
