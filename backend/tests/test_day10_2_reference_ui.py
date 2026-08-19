from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "dashboard"

def text(name: str) -> str:
    return (FRONTEND / name).read_text(encoding="utf-8")

def test_day10_2_reference_grade_information_architecture() -> None:
    html = text("index.html")
    for token in [
        "Heat Priority Dashboard",
        "FortyGuard",
        "kpiHeatIndex",
        "heatmapSvg",
        "Selected Hotspot",
        "Priority Composition",
        "Hotspot Comparison",
        "Recommendations",
        "copilotDrawer",
    ]:
        assert token in html

def test_day10_2_does_not_claim_population_or_live_current_risk() -> None:
    html = text("index.html").lower()
    assert "population at risk" not in html
    assert "real-time hyperlocal heat intelligence and risk assessment" not in html
    assert "scenario replay • not live current heat" in html

def test_day10_2_assets_are_versioned() -> None:
    html = text("index.html")
    assert "styles.css?v=10.2.0" in html
    assert "app.js?v=10.2.0" in html

def test_day10_2_keeps_copilot_grounded_contract_visible() -> None:
    html = text("index.html")
    assert "Qwen routes intent" in html
    assert "Deterministic HeatShield evidence writes the factual answer" in html
