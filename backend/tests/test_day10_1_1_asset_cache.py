from __future__ import annotations
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HTML=(ROOT/"frontend/dashboard/index.html").read_text(encoding="utf-8")

def test_dashboard_app_asset_is_versioned():
    match=re.search(r'src="\./app\.js\?v=([^"]+)"',HTML)
    assert match is not None
    assert match.group(1)=="15.0.0"
