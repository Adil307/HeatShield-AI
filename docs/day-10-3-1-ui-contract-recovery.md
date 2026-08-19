# Day 10.3.1 — UI Contract Recovery

## Root cause

The Day 10.3 production dashboard itself was applied correctly. Three regression
tests were still coupled to earlier Day 10.1/10.2 markup details:

1. `heatmapSvg` assumed the map would remain an SVG renderer.
2. `Selected Hotspot` was checked with case-sensitive text matching even though
   the production heading is rendered as `SELECTED HOTSPOT`.
3. The Day 10.2 reference contract had the same case-sensitive heading check.

Day 10.3 intentionally replaced the SVG-only heat field with a Leaflet +
OpenStreetMap renderer, so retaining `heatmapSvg` purely to satisfy an old test
would make the implementation less accurate.

## Fix

The regression contracts now validate durable product capabilities instead of
obsolete DOM details:

- real map container exists;
- Leaflet/OpenStreetMap integration exists;
- selected-hotspot capability exists regardless of heading capitalization;
- priority composition, comparison, recommendations and Copilot remain present;
- cache-versioning, evidence scope and safety language remain enforced;
- reference-only dummy claims remain prohibited.

No HeatShield evidence value, FortyGuard integration, priority computation,
recommendation logic, or Qwen behavior is changed.
