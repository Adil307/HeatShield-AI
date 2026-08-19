# Day 11 — Controlled Live Thermal Analysis

Day 11 adds a **fresh FortyGuard request path** to the judge dashboard without weakening the evidence boundaries established on Days 5–10.

## What changed

- New dashboard workspace: **Live Analysis**.
- The user pans/zooms the existing Leaflet map and uses the current viewport as the AOI.
- HeatShield submits a server-side `TCM` heatmap job through the existing FortyGuard adapter.
- Provider `activity_id` polling remains behind the backend; the API key is never exposed to the browser.
- Identical AOI/time/granularity requests are SHA-256 fingerprinted and reused from `backend/data/cache/day11/`.
- Demo-safe AOI validation stops requests above approximately **10 mi²** before a provider job is created.
- The fresh result is validated with the existing HeatShield GeoJSON parser and ranked deterministically into the three relative hottest tiles.
- The map can switch between the verified historical replay and the fresh provider result.

## New HeatShield dashboard contract

`GET /api/v1/dashboard/live-analysis/status`

Returns configuration readiness, cache count, supported analytic type, and the demo AOI limit without exposing the API key.

`POST /api/v1/dashboard/live-analysis`

Accepts the existing `HeatmapRequest` schema. Day 11 intentionally permits only `analytic_type="tcm"`.

The response schema is:

`heatshield.day11.live_thermal_analysis.v1`

It contains verified thermal GeoJSON, computed thermal statistics, the three relative hottest tiles, provider provenance, request/cache fingerprints, and explicit safety flags.

## Critical evidence boundary

A **fresh thermal job is not automatically a full HeatShield planning-priority analysis**.

Day 11 does **not** infer or fabricate:

- planning priority;
- occupancy or population;
- operational vulnerability;
- adaptive capacity;
- recommendations;
- medical/clinical risk probability.

Those outputs require the additional verified/contextual evidence layers already defined elsewhere in HeatShield. The fresh workspace therefore labels its output as **verified thermal evidence + relative hottest tiles only**.

## Credit and failure safety

1. Validate TCM-only request.
2. Approximate AOI area and reject >10 mi² in demo-safe mode.
3. Normalize the exact provider payload.
4. Compute SHA-256 request fingerprint.
5. Reuse a completed cached response when available.
6. On cache miss, submit exactly one new provider job and persist its completed response.
7. Validate the completion before rendering it.
8. Never convert provider failure or missing data into a synthetic thermal value.

## Verification

The Day 11 installer runs:

- the complete pytest regression suite;
- the existing Day 10 dashboard evidence smoke test;
- the Day 11 live-analysis cache/validation smoke test;
- the local Qwen smoke test when Ollama is available.

The automated Day 11 smoke does **not** spend FortyGuard credits. A real provider request is created only when the user presses **Run FortyGuard Analysis** in the dashboard.
