from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "dashboard"


def read(name: str) -> str:
    return (FRONTEND / name).read_text(encoding="utf-8")


def test_day12_live_workspace_exposes_controlled_enrichment_step() -> None:
    html = read("index.html")
    assert "Day 12 · Live Decision Readiness" in html
    assert 'id="liveEnrichButton"' in html
    assert "Enrich Hottest Tile" in html
    assert 'id="liveDecisionResult"' in html
    for label in ["OBSERVED", "DERIVED", "RECOMMENDED", "PLANNING PRIORITY"]:
        assert label in html


def test_day12_frontend_uses_heatshield_backend_only() -> None:
    js = read("app.js")
    assert 'fetch("/api/v1/dashboard/live-analysis/top-hotspot-enrichment"' in js
    assert 'fetch("https://api.fortyguard.com' not in js
    assert "state.liveRequest" in js
    assert "Run the fresh thermal analysis first" in js


def test_day12_keeps_missing_context_and_medical_boundary_visible() -> None:
    html = read("index.html").lower()
    js = read("app.js").lower()
    for phrase in ["planning priority remains withheld", "operational vulnerability", "adaptive capacity", "medical-risk probability"]:
        assert phrase in html
    assert "withheld · context required" in js
    assert "thermal-stress evidence" in js


def test_day12_updates_frontend_asset_version() -> None:
    assert "app.js?v=14.0.0" in read("index.html")
