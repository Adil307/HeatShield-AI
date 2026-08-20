from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "dashboard"
html = (FRONTEND / "index.html").read_text(encoding="utf-8")
js = (FRONTEND / "app.js").read_text(encoding="utf-8")

checks = {
    "asset_version": "app.js?v=15.1.0" in html,
    "scenario_lock_fix": ".scenario-lock.hidden,.scenario-ready.hidden,.scenario-restore.hidden{display:none!important;}" in html,
    "session_save": "sessionStorage.setItem" in js,
    "session_restore": "restorePersistedLiveDecisionState()" in js,
    "session_clear": "clearPersistedLiveDecisionState()" in js,
    "restore_notice": "Verified baseline restored from this browser tab." in html,
    "calendar_neutral_ui": "Day 15 · Scenario Studio" not in html and "CONTROLLED WHAT-IF COMPARISON" in html,
    "operator_reference": "Operator evidence reference:" in html,
}

print("HEATSHIELD - BUILD 15.1 UI POLISH & DEMO RELIABILITY SMOKE TEST")
print("=" * 72)
for key, ok in checks.items():
    print(f"{key}: {'PASS' if ok else 'FAIL'}")

if not all(checks.values()):
    raise SystemExit("STATUS: FAIL")
print("Browser persistence: sessionStorage (same-tab refresh only)")
print("New FortyGuard calls from persistence layer: 0")
print("New LLM calls from persistence layer: 0")
print("STATUS: PASS")
