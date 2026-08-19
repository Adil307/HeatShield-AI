from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "dashboard"
ROUTES = ROOT / "backend" / "app" / "api" / "routes_dashboard.py"


def read(name: str) -> str:
    return (FRONTEND / name).read_text(encoding="utf-8")


def test_day13_live_workspace_requires_explicit_context_fields() -> None:
    html = read("index.html")
    assert "Day 13 · Controlled Context Verification" in html
    assert 'id="liveContextForm"' in html
    assert 'id="liveContextSourceRef"' in html
    for element_id in [
        "liveExposureLevel",
        "liveSensitiveUse",
        "livePhysicalExertion",
        "liveAcclimatizationGap",
        "liveHeatPpe",
        "liveWaterAccess",
        "liveRecovery",
        "liveWorkRest",
        "liveTrainingMonitoring",
    ]:
        assert f'id="{element_id}"' in html
    assert "Do not enter personal medical information" in html


def test_day13_frontend_posts_context_to_heatshield_backend_only() -> None:
    js = read("app.js")
    assert 'fetch("/api/v1/dashboard/live-analysis/context-priority"' in js
    assert "authorized_operator_input" in js
    assert "new Date().toISOString()" in js
    assert 'fetch("https://api.fortyguard.com' not in js


def test_day13_result_keeps_transparent_classification_and_medical_boundary() -> None:
    html = read("index.html")
    js = read("app.js")
    for label in ["OBSERVED", "DERIVED", "RECOMMENDED", "Evidence-adjusted priority", "Controlled action catalog"]:
        assert label in html
    assert "not a medical-risk probability" in html
    assert "Zero provider calls for this context step" in js


def test_day13_backend_route_exists_and_asset_version_is_bumped() -> None:
    routes = ROUTES.read_text(encoding="utf-8")
    assert '@router.post("/live-analysis/context-priority")' in routes
    assert "run_live_context_priority" in routes
    assert "app.js?v=15.0.0" in read("index.html")
