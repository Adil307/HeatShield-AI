# Day 10.8 — Two Map Views and Human-Facing Recommendation Labels

## Why this pass exists

HeatShield is being prepared for hackathon judging, so the interface should not
surface internal enum strings or code-like labels.

## Map views

The Thermal Map now exposes two clear user-facing modes:

- **Satellite** — Esri World Imagery for geographic context.
- **Simple Map** — OpenStreetMap for a clean conventional map view.

Satellite remains the default. The two-mode control is explicitly raised above
Leaflet's map panes so it stays visible and clickable.

FortyGuard thermal evidence and HeatShield's derived thermal overlay remain the
same in both modes.

## Human-facing labels

Internal backend values are no longer printed directly when they look like
machine codes.

Examples:

- `HIGH_PLANNING_PRIORITY` → `High Planning Priority`
- `unknown` → `Unknown`
- `withheld` → `Withheld`
- recommendation enum/tier strings such as `P1 — evidence_verification` are not
  rendered directly.

Recommendations instead show simple action labels such as:

- `Verify first`
- `Assess next`
- `Review if applicable`

The actual recommendation title and evidence-grounded recommendation text are
still sourced from the backend.

## Evidence integrity

No score, metric, location, risk, or recommendation content is invented by this
UI pass. Dashboard values still come from `/api/v1/dashboard/overview`, and the
assistant still uses the existing grounded backend endpoints.
