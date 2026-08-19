from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "dashboard"


def test_professional_dashboard_files_exist() -> None:
    assert (FRONTEND / "index.html").exists()
    assert (FRONTEND / "styles.css").exists()
    assert (FRONTEND / "app.js").exists()


def test_dashboard_has_professional_decision_information_architecture() -> None:
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")

    # Test stable UX capabilities, not old Day-10.1 implementation IDs.
    required = [
        "sidebar",
        "kpiHotspots",
        "heatmapSvg",
        "Selected Hotspot",
        "Priority Composition",
        "Hotspot Comparison",
        "Recommendations",
        "copilotDrawer",
        "copilotForm",
    ]
    for token in required:
        assert token in html


def test_copilot_is_drawer_not_full_page_block() -> None:
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    css = (FRONTEND / "styles.css").read_text(encoding="utf-8")

    assert "copilot-drawer" in html
    assert ".copilot-drawer" in css
    assert re.search(r"\.copilot-drawer\s*\{[^}]*position\s*:\s*fixed", css, re.S)


def test_frontend_keeps_evidence_scope_language() -> None:
    html = (FRONTEND / "index.html").read_text(encoding="utf-8").lower()

    assert "fortyguard" in html
    assert "planning priority" in html
    assert "medical risk" in html or "medical-risk" in html
    assert "not live current heat" in html
