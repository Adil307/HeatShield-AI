# Day 10.6 — Responsive, Humanized, Real-Data Dashboard

Day 10.6 is a UI integrity and usability pass over the single-workspace dashboard.

## Changes

- Fully responsive behavior for desktop, laptop, tablet and phone breakpoints.
- Tablet sidebar becomes a compact navigation rail.
- Mobile sidebar becomes a horizontal product navigation bar.
- KPI, map, hotspot, analytics, evidence, recommendations and assistant layouts reflow without horizontal overflow.
- Removed sparkle/star AI iconography and changed the visible product feature from `AI Copilot` to `HeatShield Assistant`.
- Rewrote user-facing copy in clearer, less robotic language.
- Removed static demo metric values and hard-coded `Hotspot 2` quick prompts from the HTML.
- Status placeholders now load from backend evidence instead of visually pretending to be final values.
- Quick questions are generated from the currently selected real hotspot.
- Model name and assistant readiness come from `/api/v1/copilot/status`.
- Scenario label is populated from the dashboard payload where available.

## Real data contract

Dashboard facts still come from:
- `/api/v1/dashboard/overview`
- actual FortyGuard evidence artifacts
- deterministic HeatShield planning outputs
- controlled recommendation catalog

Assistant answers still use:
- `/api/v1/copilot/ask`
- local Qwen for intent routing
- deterministic evidence rendering for factual output

No population-at-risk value, AQI, fake trends, fake location names, current-live-heat claim, or medical-risk probability is introduced.
