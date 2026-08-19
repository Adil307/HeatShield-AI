from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
FRONTEND=ROOT/"frontend/dashboard"
def test_dashboard_keeps_reference_grade_scope_without_dummy_claims():
    text=((FRONTEND/"index.html").read_text(encoding="utf-8")+"\n"+(FRONTEND/"app.js").read_text(encoding="utf-8")).lower()
    assert "fortyguard" in text
    assert "not live current heat" in text
    for phrase in ["population at risk","air quality (aqi)","risk trend (last 7 days)","city center","university town","airport road"]:
        assert phrase not in text
