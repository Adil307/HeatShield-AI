from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "dashboard"


def text(name: str) -> str:
    return (FRONTEND / name).read_text(encoding="utf-8")


def test_reference_grade_information_architecture_is_preserved() -> None:
    html = text("index.html")
    lower = html.lower()

    for token in [
        "Heat Priority Dashboard",
        "FortyGuard",
        "kpiHeatIndex",
        "Priority Composition",
        "Hotspot Comparison",
        "Recommendations",
        "copilotDrawer",
    ]:
        assert token in html

    assert "selected hotspot" in lower


def test_dashboard_does_not_claim_population_or_live_current_risk() -> None:
    html = text("index.html").lower()

    assert "population at risk" not in html
    assert "real-time hyperlocal heat intelligence and risk assessment" not in html
    assert "not live current heat" in html


def test_dashboard_assets_remain_cache_versioned() -> None:
    html = text("index.html")

    style = re.search(r'href="\./styles\.css\?v=([^"]+)"', html)
    script = re.search(r'src="\./app\.js\?v=([^"]+)"', html)

    assert style is not None
    assert script is not None
    assert style.group(1) == script.group(1)


def test_copilot_grounded_contract_is_visible() -> None:
    html = text("index.html")

    assert "Qwen routes intent locally" in html
    assert "Deterministic HeatShield evidence writes the factual answer" in html
