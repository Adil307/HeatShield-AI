from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "dashboard"


def read(name: str) -> str:
    return (FRONTEND / name).read_text(encoding="utf-8")


def test_final_approved_dashboard_contract() -> None:
    html = read("index.html")
    lower = html.lower()

    for token in [
        "Heat Priority Dashboard",
        "kpiHotspots",
        "thermalMap",
        "Selected Hotspot",
        "Priority Composition",
        "Hotspot Comparison",
        "Recommended Next Checks",
        "What the Priority Is Based On",
        "copilotMain",
        "copilotForm",
    ]:
        assert token in html

    assert "heatshield assistant" in lower
