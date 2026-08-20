from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "dashboard"
ROUTES = ROOT / "backend" / "app" / "api" / "routes_dashboard.py"


def read(name: str) -> str:
    return (FRONTEND / name).read_text(encoding="utf-8")


def test_day15_scenario_route_is_backend_only() -> None:
    routes = ROUTES.read_text(encoding="utf-8")
    js = read("app.js")
    assert '@router.post("/live-analysis/scenario")' in routes
    assert "run_live_scenario_studio" in routes
    assert "fetch('/api/v1/dashboard/live-analysis/scenario'" in js
    assert 'fetch("https://api.fortyguard.com' not in js


def test_day15_ui_has_dedicated_scenario_workspace_and_live_bridge() -> None:
    html = read("index.html")
    assert 'data-view="scenario"' in html
    assert 'id="scenarioMain"' in html
    assert 'id="liveOpenScenario"' in html
    assert "Scenario Studio" in html
    assert "Run Scenario Comparison" in html


def test_day15_ui_makes_assumption_and_temperature_boundaries_visible() -> None:
    html = read("index.html")
    assert "SCENARIO ESTIMATE" in html
    assert "ASSUMED" in html
    assert "holds verified thermal hazard constant" in html
    assert "no temperature reduction is estimated" in html
    assert "no medical-risk probability" in html


def test_day15_frontend_reuses_exact_verified_context_request() -> None:
    js = read("app.js")
    assert "context_request:state.liveContextRequest" in js
    assert "scenarioPresetChanges" in js
    assert "temperature_change_celsius" not in js  # physical outcome remains server-controlled


def test_day15_asset_version() -> None:
    assert "app.js?v=15.1.0" in read("index.html")
