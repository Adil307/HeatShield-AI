from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "dashboard"

def read(name: str) -> str:
    return (FRONTEND / name).read_text(encoding="utf-8")

def test_current_dashboard_uses_real_map_stack() -> None:
    html = read("index.html")
    js = read("app.js")
    assert "leaflet@1.9.4" in html
    assert "leaflet.heat" in html
    assert "thermalMap" in html
    assert "tile.openstreetmap.org" in js
    assert "L.geoJSON" in js
    assert "L.heatLayer" in js

def test_current_dashboard_uses_day10_4_versioned_app_asset() -> None:
    html = read("index.html")
    assert "app.js?v=10.4.0" in html

def test_current_dashboard_has_professional_decision_layout() -> None:
    html = read("index.html")
    lower = html.lower()
    for token in [
        "Heat Priority Dashboard",
        "kpiHotspots",
        "thermalMap",
        "Priority Composition",
        "Hotspot Comparison",
        "Controlled Recommendations",
        "drawer",
        "copilotForm",
    ]:
        assert token in html
    assert "selected hotspot" in lower

def test_current_dashboard_rejects_reference_only_dummy_claims() -> None:
    text = (read("index.html") + "\n" + read("app.js")).lower()
    forbidden = [
        "population at risk",
        "air quality (aqi)",
        "risk trend (last 7 days)",
        "city center",
        "university town",
        "airport road",
    ]
    for phrase in forbidden:
        assert phrase not in text

def test_current_dashboard_keeps_evidence_scope_visible() -> None:
    text = read("index.html").lower()
    assert "fortyguard" in text
    assert "not live current heat" in text
    assert "medical-risk probability" in text
    assert "current mapped objects are not interpreted as people or occupancy" in text

def test_current_dashboard_keeps_grounded_ai_contract() -> None:
    html = read("index.html")
    js = read("app.js")
    assert "Qwen routes intent locally" in html
    assert "Deterministic HeatShield evidence writes the factual answer" in html
    assert 'fetch("/api/v1/copilot/ask"' in js
