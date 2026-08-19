from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
FRONTEND=ROOT/"frontend/dashboard"
def read(name): return (FRONTEND/name).read_text(encoding="utf-8")

def test_day10_7_sidebar_is_styled_as_product_navigation():
    html=read("index.html")
    for token in ["nav-section-label",".nav .nav-link",".nav .nav-link.active",".nav .nav-link:hover","linear-gradient"]:
        assert token in html

def test_day10_7_satellite_is_default_with_simple_map_fallback():
    html=read("index.html");js=read("app.js")
    assert 'id="satelliteBasemapButton"' in html
    assert 'id="streetBasemapButton"' in html
    assert ">Satellite<" in html or "Satellite" in html
    assert "Simple Map" in html
    assert 'activeBasemap:"satellite"' in js
    assert "World_Imagery/MapServer/tile" in js
    assert "tile.openstreetmap.org" in js
    assert 'setBasemap("satellite")' in js
    assert 'setBasemap("streets")' in js

def test_day10_7_does_not_add_dummy_dashboard_values():
    html=read("index.html")
    for literal in ["33.14°C","38.2°C","70.29","55.3%","Tile 137","Hotspot 2"]:
        assert literal not in html

def test_day10_7_removes_visible_escaped_build_comments():
    html=read("index.html")
    assert "&lt;!-- HeatShield Day 10.5 SPA workspace navigation --&gt;" not in html
    assert "&lt;!-- HeatShield Day 10.4 approved production design --&gt;" not in html

def test_day10_7_keeps_assistant_human_and_grounded():
    html=read("index.html").lower();js=read("app.js")
    assert "open assistant" in html
    assert "✦" not in html
    assert 'fetch("/api/v1/copilot/status")' in js
    assert 'fetch("/api/v1/copilot/ask"' in js

def test_day10_7_html_is_clean_utf8_without_mojibake_or_bom():
    raw=(FRONTEND/"index.html").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    html=raw.decode("utf-8")
    for bad in ["â‰","â€¦","ï»¿"]:
        assert bad not in html
