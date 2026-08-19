from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "frontend" / "dashboard" / "index.html"

def test_dashboard_app_asset_is_versioned() -> None:
    html = INDEX.read_text(encoding="utf-8")
    match = re.search(r'src="\./app\.js\?v=([^"]+)"', html)
    assert match is not None
    assert match.group(1) == "10.5.0"
