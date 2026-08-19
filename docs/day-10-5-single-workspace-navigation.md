# Day 10.5 — Single-Workspace Dashboard Navigation

Day 10.5 converts the approved dashboard from one long scrolling page into an app-like single-workspace experience.

## Navigation behavior

- Overview: evidence-backed KPIs plus priority composition, hotspot comparison, ranking, and compact actions.
- Thermal Map: the real OpenStreetMap + FortyGuard GeoJSON/derived heat visualization and selected hotspot panel.
- Hotspots: selected hotspot intelligence plus comparison/ranking graphs; the map is intentionally removed from this view.
- Explainability: priority composition, verified evidence, UNKNOWN/WITHHELD states, and safety semantics.
- Recommendations: full controlled recommendation catalog for the selected hotspot.
- AI Copilot: full main-workspace grounded chat with quick prompts and active grounding context. It is no longer an overlay drawer.

The implementation uses vanilla CSS and JavaScript view routing, preserves the same backend APIs, and does not introduce dummy metrics or unsupported claims.
