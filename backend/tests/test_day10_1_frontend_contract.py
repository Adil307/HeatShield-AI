from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "dashboard"


def test_professional_dashboard_files_exist() -> None:
    assert (FRONTEND / "index.html").exists()
    assert (FRONTEND / "styles.css").exists()
    assert (FRONTEND / "app.js").exists()


def test_dashboard_has_operations_information_architecture() -> None:
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    required = [
        "sidebar",
        "kpiHotspots",
        "heatmapSvg",
        "rankingList",
        "detailTitle",
        "metricGrid",
        "actionList",
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
    assert "position: fixed" in css


def test_frontend_keeps_evidence_scope_language() -> None:
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    text = html.lower()
    assert "fortyguard" in text
    assert "planning priority" in text
    assert "medical risk" in text
