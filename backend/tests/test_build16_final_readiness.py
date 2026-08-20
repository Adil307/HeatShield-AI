from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
DEMO = ROOT / "demo"
SCRIPTS = ROOT / "backend" / "scripts"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_build16_readme_is_final_product_documentation() -> None:
    readme = text(README)
    for phrase in [
        "Explainable urban heat decision intelligence",
        "Judge-ready workflow",
        "Final verification",
        "AI evaluation metrics",
        "Safety and evidence boundaries",
        "Demo reliability strategy",
        "Known limitations",
        "Official 18-30 August execution mapping",
    ]:
        assert phrase in readme
    assert "not a clinically validated medical-risk score" in readme
    assert "RUN_29AUG_FINAL_READINESS.ps1" in readme


def test_build16_demo_rehearsal_pack_exists_and_has_fallback() -> None:
    demo_script = text(DEMO / "DEMO_SCRIPT.md")
    checklist = text(DEMO / "REHEARSAL_CHECKLIST.md")
    qa = text(DEMO / "JUDGE_QA.md")
    log = text(DEMO / "DEMO_RUN_LOG_TEMPLATE.md")
    assert "Historical replay" in demo_script
    assert "Fresh live path" in demo_script
    assert "Fallback" in demo_script
    assert "three successful rehearsals" in checklist.lower()
    assert "Why not use FortyGuard directly?" in qa
    assert "Medical" in qa
    assert "Run #" in log


def test_build16_ai_evaluation_covers_blueprint_metrics() -> None:
    source = text(SCRIPTS / "build16_final_ai_evaluation.py")
    for metric in [
        "grounding_pass_rate_percent",
        "unsupported_claim_rate_percent",
        "evidence_citation_coverage_percent",
        "consistency_pass",
        "missing_data_behavior_pass",
        "tool_intent_selection_accuracy_percent",
        "latency_ms_median",
        "latency_ms_p95",
    ]:
        assert metric in source
    assert "real_fortyguard_calls" in source
    assert '"llm_calls": 0' in source


def test_build16_release_scripts_are_windows_powershell_safe_ascii() -> None:
    for name in ["RUN_29AUG_FINAL_READINESS.ps1", "RUN_FINAL_DASHBOARD.ps1"]:
        payload = (ROOT / name).read_bytes()
        # UTF-8 BOM is allowed; all actual script characters must be ASCII.
        if payload.startswith(b"\xef\xbb\xbf"):
            payload = payload[3:]
        assert all(byte < 128 for byte in payload)
        assert b"\xe2\x80\x94" not in payload


def test_build16_frontend_does_not_embed_provider_secret_name() -> None:
    for path in (ROOT / "frontend" / "dashboard").glob("*"):
        if path.is_file():
            assert "FORTYGUARD_API_KEY" not in path.read_text(encoding="utf-8", errors="ignore")
