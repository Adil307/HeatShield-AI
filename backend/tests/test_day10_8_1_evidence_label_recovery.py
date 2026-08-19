from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "dashboard"


def read(name: str) -> str:
    return (FRONTEND / name).read_text(encoding="utf-8")


def test_day10_8_1_restores_legacy_evidence_semantics_without_machine_codes():
    html = read("index.html")
    assert "Operational Vulnerability" in html
    assert "Adaptive Capacity" in html
    assert "Medical Risk Probability" in html
    assert "medical-risk probability" in html.lower()
    assert "Current mapped objects are not interpreted as people or occupancy" in html


def test_day10_8_1_preserves_two_human_map_modes():
    html = read("index.html")
    assert 'id="satelliteBasemapButton"' in html
    assert 'id="streetBasemapButton"' in html
    assert "Satellite" in html
    assert "Simple Map" in html
    assert "app.js?v=11.0.0" in html
