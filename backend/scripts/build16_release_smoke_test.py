from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
DEMO = ROOT / "demo"
FRONTEND = ROOT / "frontend" / "dashboard"
RUNNER = ROOT / "RUN_29AUG_FINAL_READINESS.ps1"
FINAL_DASHBOARD = ROOT / "RUN_FINAL_DASHBOARD.ps1"


def has(path: Path, phrase: str) -> bool:
    return phrase in path.read_text(encoding="utf-8")


checks = {
    "readme_final_product": has(README, "Explainable urban heat decision intelligence"),
    "readme_safety": has(README, "not a clinically validated medical-risk score"),
    "readme_final_gate": has(README, "RUN_29AUG_FINAL_READINESS.ps1"),
    "demo_script": (DEMO / "DEMO_SCRIPT.md").exists(),
    "judge_qa": (DEMO / "JUDGE_QA.md").exists(),
    "rehearsal_checklist": (DEMO / "REHEARSAL_CHECKLIST.md").exists(),
    "run_log": (DEMO / "DEMO_RUN_LOG_TEMPLATE.md").exists(),
    "readiness_runner": RUNNER.exists(),
    "final_dashboard_runner": FINAL_DASHBOARD.exists(),
    "api_key_not_in_frontend": all(
        "FORTYGUARD_API_KEY" not in path.read_text(encoding="utf-8", errors="ignore")
        for path in FRONTEND.glob("*")
        if path.is_file()
    ),
}

print("HEATSHIELD - BUILD 16 FINAL RELEASE / DOCUMENTATION SMOKE TEST")
print("=" * 72)
for key, value in checks.items():
    print(f"{key}: {'PASS' if value else 'FAIL'}")

if not all(checks.values()):
    raise SystemExit("STATUS: FAIL")
print("STATUS: PASS")
