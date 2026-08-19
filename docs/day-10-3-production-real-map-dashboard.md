# Day 10.3 — Production-Grade Real Map Dashboard

## Goal

Replace the synthetic-looking thermal grid presentation with a professional decision dashboard built around a real geographic basemap.

## Key UX upgrade

Day 10.3 uses:
- Leaflet for the interactive map;
- OpenStreetMap as the actual basemap;
- the verified FortyGuard GeoJSON as a semi-transparent thermal overlay;
- verified hotspot tiles as interactive map markers;
- actual HeatShield priority scores and evidence only.

No city-center labels, population-at-risk values, AQI, fake trend charts, fake dates, or other reference-image-only content are introduced.

## Information hierarchy

1. Six evidence-backed KPIs
2. Real map + selected hotspot panel
3. Priority composition
4. Hotspot comparison
5. Controlled recommendations
6. Evidence completeness
7. Local grounded Copilot drawer

## Safety

The UI keeps these boundaries visible:
- scenario replay, not live current heat;
- planning priority, not medical risk;
- mapped objects are not people or occupancy;
- UNKNOWN and WITHHELD remain explicit states.
