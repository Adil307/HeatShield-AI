from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "dashboard"


def read(name: str) -> str:
    return (FRONTEND / name).read_text(encoding="utf-8")


def test_day10_6_is_responsive_across_breakpoints() -> None:
    css = read("index.html")
    for bp in ["1320px", "1080px", "760px", "480px"]:
        assert f"max-width: {bp}" in css


def test_day10_6_removes_ai_sparkle_signs_and_hype_labels() -> None:
    html = read("index.html")
    visible = html.lower()
    assert "✦ ai copilot" not in visible
    assert ">ai copilot<" not in visible
    assert "local grounded ai" not in visible
    assert "heatshield assistant" in visible


def test_day10_6_has_no_static_demo_metric_values() -> None:
    text = read("index.html")
    for literal in ["33.14°C", "38.2°C", "70.29", "55.3%", "Tile 137", "Hotspot 2"]:
        assert literal not in text


def test_day10_6_quick_prompts_use_selected_real_hotspot() -> None:
    html = read("index.html")
    js = read("app.js")
    assert "data-intent=" in html
    assert 'data-prompt="Why is Hotspot 2 prioritized?"' not in html
    assert "queryForIntent" in js
    assert "state.selectedRank" in js


def test_day10_6_status_placeholders_are_not_fake_final_values() -> None:
    html = read("index.html")
    assert 'id="vulnStatus">Loading…<' in html
    assert 'id="capacityStatus">Loading…<' in html
    assert 'id="medicalStatus">Loading…<' in html


def test_day10_6_real_values_still_come_from_backend() -> None:
    js = read("app.js")
    assert 'fetch("/api/v1/dashboard/overview")' in js

    # The implementation aliases state.snapshot.summary to `s`.
    # Validate the live backend fields actually consumed by the renderer,
    # rather than requiring one exact variable name.
    assert "highest_priority_score" in js
    assert "max_historical_air_temperature_celsius" in js
    assert "historical_air_temperature_celsius" in js
    assert "historical_heat_index_celsius" in js
    assert "historical_relative_humidity_percent" in js
    assert "heatmap_feature_count" in js


def test_day10_6_assistant_uses_real_backend_status_and_answers() -> None:
    js = read("app.js")
    assert 'fetch("/api/v1/copilot/status")' in js
    assert 'fetch("/api/v1/copilot/ask"' in js
    assert "payload.model" in js or "payload.configured_model" in js
