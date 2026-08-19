from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
FRONTEND=ROOT/"frontend/dashboard"
def test_final_approved_dashboard_contract():
    html=(FRONTEND/"index.html").read_text(encoding="utf-8")
    for token in ["Heat Priority Dashboard","kpiHotspots","thermalMap","Selected Hotspot","Priority Composition","Hotspot Comparison","Controlled Recommendations","Verified Evidence Behind the Priority","drawer","copilotForm"]:
        assert token in html
