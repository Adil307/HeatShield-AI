from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
FRONTEND=ROOT/"frontend/dashboard"

def read(name): return (FRONTEND/name).read_text(encoding="utf-8")

def test_day10_5_sidebar_switches_main_workspace_views():
    html=read("index.html"); js=read("app.js")
    for view in ["overview","thermal","hotspots","evidence","actions","copilot"]:
        assert f'data-view="{view}"' in html or f'"{view}"' in js
    assert 'activateView' in js
    assert 'content.dataset.view=view' in js

def test_day10_5_copilot_is_main_workspace_not_overlay_drawer():
    html=read("index.html")
    assert 'id="copilotMain"' in html
    assert 'id="drawer"' not in html
    assert 'id="scrim"' not in html

def test_day10_5_overview_keeps_real_graphs_and_no_dummy_claims():
    text=(read("index.html")+"\n"+read("app.js")).lower()
    assert "priority composition" in text
    assert "hotspot comparison" in text
    for phrase in ["population at risk","air quality (aqi)","risk trend (last 7 days)","city center","university town","airport road"]:
        assert phrase not in text

def test_day10_5_map_still_uses_verified_real_stack():
    html=read("index.html"); js=read("app.js")
    assert "leaflet@1.9.4" in html
    assert "leaflet.heat" in html
    assert "tile.openstreetmap.org" in js
    assert "L.geoJSON" in js
    assert "L.heatLayer" in js

def test_day10_5_copilot_stays_grounded():
    html=read("index.html"); js=read("app.js")
    assert "deterministic evidence renderer" in html.lower()
    assert 'fetch("/api/v1/copilot/ask"' in js
