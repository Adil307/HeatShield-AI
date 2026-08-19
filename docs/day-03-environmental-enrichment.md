# Day 3 - Environmental Thermal Context

## Goal

Day 3 enriches the highest-ranked **AOI-relative thermal hotspot candidates** from Day 2 with FortyGuard environmental parameters. It does not create a clinical or population heat-risk score.

## Provider contract

HeatShield uses FortyGuard `POST /v1/env_params` with the documented fields: latitude, longitude, temperature, and date_time. The same asynchronous `GET /v1/status/{activity_id}` flow is used to retrieve completed results.

The current provider documentation exposes heat index, apparent temperature, wet-bulb temperature, relative humidity, precipitation, air quality, gases, and solar irradiance in the completed response. Basic access may be limited to a subset of customizable parameters, so the parser treats missing/sentinel values as missing rather than inventing values.

## Pipeline

1. Read `backend/data/processed/day2_hotspot_analysis.json`.
2. Verify its source heatmap SHA-256 still matches the local Day-1 raw artifact.
3. Select the highest-ranked hotspot candidates only.
4. Derive a representative point from each small GeoJSON tile in O(v).
5. Build a documented FortyGuard environmental request using the exact Day-1 heatmap date/time and the observed tile temperature.
6. Fingerprint the request with SHA-256.
7. Reuse a completed local cache when the same request fingerprint already exists, avoiding unnecessary provider submissions and credit use.
8. Poll FortyGuard to completion for uncached requests.
9. Strictly parse the returned location and core environmental metrics.
10. Link environmental evidence back to the Day-2 thermal evidence ID.
11. Save a derived Day-3 artifact to `backend/data/processed/day3_environmental_enrichment.json`.

## Evidence classes

- **Observed:** FortyGuard tile temperature and completed environmental parameter values.
- **Derived:** representative point, request fingerprint, evidence IDs, simple metric deltas, and completeness.
- **Inferred:** none on Day 3.
- **Recommended:** none on Day 3.

## Complexity

For k selected hotspots and v total geometry vertices, local processing is O(k + v). Network/API latency dominates wall-clock time. The cache lookup is O(1) per request using deterministic file names based on a request SHA-256 fingerprint.

The implementation deliberately avoids enriching all heatmap tiles. Day 2 narrows 150 tiles to a small candidate set first, and Day 3 enriches only the highest-value candidates. This reduces latency, provider load, and credit usage.

## Current demo invocation

The verified Day-1 control heatmap used New York City on `2024-07-15` at `14:00`. Day 3 must use the same date/time so environmental context aligns with the temperature evidence.

From `backend/` with `.venv` active:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m scripts.day3_environmental_enrichment --start-date 2024-07-15 --start-time 14:00 --limit 3
```

## Limitations

- Environmental context is not equivalent to vulnerability, exposure, adaptive capacity, or health outcome.
- No demographic data or occupancy is assumed.
- No missing environmental metric is imputed.
- The representative-point calculation is a planar centroid approximation designed for small provider tiles.
- A composite risk model is intentionally deferred until the evidence layers needed to justify it are available.
