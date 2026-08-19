from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "frontend" / "dashboard" / "index.html"


def test_dashboard_assets_are_versioned_to_avoid_stale_cache() -> None:
    html = INDEX.read_text(encoding="utf-8")
    assert 'styles.css?v=10.1.1' in html
    assert 'app.js?v=10.1.1' in html
