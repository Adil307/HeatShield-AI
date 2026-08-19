from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "dashboard"


def _read(name: str) -> str:
    return (FRONTEND / name).read_text(encoding="utf-8")


def test_professional_dashboard_files_exist() -> None:
    assert (FRONTEND / "index.html").exists()
    assert (FRONTEND / "styles.css").exists()
    assert (FRONTEND / "app.js").exists()


def test_dashboard_has_professional_decision_information_architecture() -> None:
    html = _read("index.html")
    lower = html.lower()

    # Stable product capabilities only. Do not couple this regression
    # test to an old renderer implementation such as an SVG-only map.
    required_case_sensitive = [
        "sidebar",
        "kpiHotspots",
        "realMap",
        "Priority Composition",
        "Hotspot Comparison",
        "Recommendations",
        "copilotDrawer",
        "copilotForm",
    ]
    for token in required_case_sensitive:
        assert token in html

    assert "selected hotspot" in lower


def test_copilot_is_drawer_not_full_page_block() -> None:
    html = _read("index.html")
    css = _read("styles.css")

    assert "copilot-drawer" in html
    assert ".copilot-drawer" in css
    assert re.search(r"\.copilot-drawer\s*\{[^}]*position\s*:\s*fixed", css, re.S)


def test_frontend_keeps_evidence_scope_language() -> None:
    html = _read("index.html").lower()

    assert "fortyguard" in html
    assert "planning priority" in html
    assert "medical risk" in html or "medical-risk" in html
    assert "not live current heat" in html
    assert "mapped objects are not people" in html
