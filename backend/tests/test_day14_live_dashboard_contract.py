from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "dashboard"
ROUTES = ROOT / "backend" / "app" / "api" / "routes_dashboard.py"


def read(name: str) -> str:
    return (FRONTEND / name).read_text(encoding="utf-8")


def test_day14_live_copilot_route_is_backend_only() -> None:
    routes = ROUTES.read_text(encoding="utf-8")
    js = read("app.js")
    assert '@router.post("/live-analysis/copilot")' in routes
    assert "answer_live_copilot" in routes
    assert 'fetch("/api/v1/dashboard/live-analysis/copilot"' in js
    assert 'fetch("https://api.fortyguard.com' not in js


def test_day14_frontend_preserves_exact_verified_context_request_for_copilot() -> None:
    js = read("app.js")
    assert "liveContextRequest" in js
    assert "context_request:state.liveContextRequest" in js
    assert "deterministic_live_evidence_renderer" not in js  # renderer remains server-side


def test_day14_ui_explains_live_grounding_and_llm_boundary() -> None:
    html = read("index.html")
    assert "Day 14 · Live Grounded Copilot" in html
    assert 'id="liveAskAssistant"' in html
    assert "Qwen routes intent only" in html
    assert "deterministic evidence renderer" in html
    assert "medical-risk probability" in html


def test_day14_asset_version_and_overflow_polish() -> None:
    html = read("index.html")
    assert "app.js?v=15.0.0" in html
    assert "overflow-x:hidden" in html
