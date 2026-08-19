from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "dashboard"


def read(name: str) -> str:
    return (FRONTEND / name).read_text(encoding="utf-8")


def test_day10_3_uses_real_map_stack() -> None:
    html = read("index.html")
    js = read("app.js")

    assert "leaflet@1.9.4" in html
    assert "OpenStreetMap basemap" in html
    assert "tile.openstreetmap.org" in js
    assert "L.geoJSON" in js


def test_day10_3_uses_versioned_matching_assets() -> None:
    html = read("index.html")

    assert "styles.css?v=10.3.0" in html
    assert "app.js?v=10.3.0" in html


def test_day10_3_has_professional_decision_layout() -> None:
    html = read("index.html")
    lower = html.lower()

    for token in [
        "Heat Priority Dashboard",
        "kpiHotspots",
        "realMap",
        "Priority Composition",
        "Hotspot Comparison",
        "Recommendations",
        "copilotDrawer",
        "copilotForm",
    ]:
        assert token in html

    assert "selected hotspot" in lower


def test_day10_3_rejects_reference_only_dummy_claims() -> None:
    text = read("index.html").lower()

    forbidden = [
        "population at risk",
        "air quality (aqi)",
        "12 aug",
        "risk trend (last 7 days)",
        "city center",
        "university town",
        "airport road",
    ]
    for phrase in forbidden:
        assert phrase not in text


def test_day10_3_keeps_evidence_scope_visible() -> None:
    text = read("index.html").lower()

    assert "fortyguard" in text
    assert "not live current heat" in text
    assert "planning priority, not medical risk" in text
    assert "mapped objects are not people" in text


def test_day10_3_copilot_is_fixed_drawer() -> None:
    css = read("styles.css")

    assert re.search(r"\.copilot-drawer\s*\{[^}]*position\s*:\s*fixed", css, re.S)
