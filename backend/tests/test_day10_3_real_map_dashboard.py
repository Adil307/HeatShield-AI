from __future__ import annotations
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
FRONTEND=ROOT/"frontend/dashboard"
def read(name): return (FRONTEND/name).read_text(encoding="utf-8")

def test_current_dashboard_uses_real_map_stack():
    html=read("index.html"); js=read("app.js")
    assert "leaflet@1.9.4" in html
    assert "leaflet.heat" in html
    assert "thermalMap" in html
    assert "tile.openstreetmap.org" in js
    assert "L.geoJSON" in js
    assert "L.heatLayer" in js

def test_current_dashboard_uses_current_versioned_app_asset():
    assert "app.js?v=10.6.0" in read("index.html")

def test_current_dashboard_keeps_real_evidence_scope():
    text=read("index.html").lower()
    assert "fortyguard" in text
    assert "not live current heat" in text
    assert "medical-risk probability" in text
    assert "current mapped objects are not interpreted as people or occupancy" in text

def test_current_dashboard_keeps_grounded_assistant_contract():
    html=read("index.html").lower(); js=read("app.js")
    assert "heatshield assistant" in html
    assert "answers are written from heatshield" in html
    assert 'fetch("/api/v1/copilot/ask"' in js
