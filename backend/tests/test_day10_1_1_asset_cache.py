from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HTML=(ROOT/"frontend/dashboard/index.html").read_text(encoding="utf-8")
def test_dashboard_app_asset_is_versioned():
    assert "app.js?v=10.4.0" in HTML
