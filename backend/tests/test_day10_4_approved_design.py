from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "dashboard"

def read(name: str) -> str:
    return (FRONTEND / name).read_text(encoding="utf-8")

def test_real_map_and_smooth_derived_visualization():
    html=read("index.html"); js=read("app.js")
    assert "leaflet@1.9.4" in html
    assert "leaflet.heat" in html
    assert "L.geoJSON" in js
    assert "L.heatLayer" in js

def test_dashboard_is_data_driven():
    js=read("app.js")
    assert 'fetch("/api/v1/dashboard/overview")' in js
    assert 'fetch("/api/v1/copilot/ask"' in js
    assert "const responses =" not in js

def test_evidence_semantics_are_visible():
    html=read("index.html")
    lower=html.lower()
    assert "Operational Vulnerability" in html
    assert "Adaptive Capacity" in html
    assert "Medical Risk Probability" in html
    assert "medical-risk probability" in lower
    assert "Current mapped objects are not interpreted as people or occupancy" in html
