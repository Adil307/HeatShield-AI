from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "frontend" / "dashboard" / "index.html"


def test_dashboard_assets_are_versioned_to_avoid_stale_cache() -> None:
    html = INDEX.read_text(encoding="utf-8")

    style = re.search(r'href="\./styles\.css\?v=([^"]+)"', html)
    script = re.search(r'src="\./app\.js\?v=([^"]+)"', html)

    assert style is not None
    assert script is not None
    assert style.group(1) == script.group(1)
    assert style.group(1).strip()
