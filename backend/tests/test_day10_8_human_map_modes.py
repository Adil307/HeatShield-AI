from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
FRONTEND=ROOT/"frontend/dashboard"
def read(name): return (FRONTEND/name).read_text(encoding="utf-8")

def test_day10_8_exposes_exactly_two_clear_map_view_buttons():
    html=read("index.html")
    assert 'id="satelliteBasemapButton"' in html
    assert 'id="streetBasemapButton"' in html
    assert "Satellite" in html
    assert "Simple Map" in html

def test_day10_8_map_controls_are_above_leaflet_layers():
    html=read("index.html")
    assert ".map-controls{" in html
    assert "z-index:650 !important" in html

def test_day10_8_recommendations_do_not_render_backend_enum_codes():
    js=read("app.js")
    assert "recommendationKind" in js
    assert "Verify first" in js
    assert "Assess next" in js
    assert "Review if applicable" in js
    assert '${esc(r.priority_tier||"CONTROLLED")} — ${esc(r.action_type||"ASSESS")}' not in js

def test_day10_8_humanizes_machine_status_tokens():
    js=read("app.js")
    assert "humanizeToken" in js
    assert "humanStatus" in js
    assert '.toUpperCase();$("selectedScore")' not in js

def test_day10_8_keeps_real_runtime_data_paths():
    js=read("app.js")
    assert 'fetch("/api/v1/dashboard/overview")' in js
    assert 'fetch("/api/v1/copilot/status")' in js
    assert 'fetch("/api/v1/copilot/ask"' in js
    assert "highest_priority_score" in js
    assert "historical_air_temperature_celsius" in js

def test_day10_8_still_has_no_hardcoded_demo_metrics_in_html():
    html=read("index.html")
    for literal in ["33.14°C","38.2°C","70.29","55.3%","Tile 137","Hotspot 2"]:
        assert literal not in html
