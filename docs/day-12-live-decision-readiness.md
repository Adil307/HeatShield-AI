# Day 12 — Live Thermal-Stress Decision Readiness

Day 12 connects the Day 11 fresh FortyGuard thermal workflow to HeatShield's evidence architecture without inventing a full planning-priority score from temperature alone.

## User flow

1. Run **Live Analysis** to obtain a verified FortyGuard TCM completion.
2. HeatShield identifies the relative hottest verified tile deterministically.
3. Press **Enrich Hottest Tile**.
4. The backend reuses the already completed Day 11 heatmap cache and derives the hottest tile representative point server-side.
5. HeatShield may submit exactly one FortyGuard **Environmental Parameters** job for that tile and time.
6. Observed heat index, apparent temperature, wet-bulb temperature and relative humidity are shown when the provider returns them.
7. If an observed heat index exists, HeatShield derives the existing transparent hazard planning ordinal and names the heat-index band.
8. Full planning priority remains **WITHHELD** until required exposure, operational-vulnerability and adaptive-capacity evidence is verified.

## New endpoint

`POST /api/v1/dashboard/live-analysis/top-hotspot-enrichment`

Input: the same `HeatmapRequest` used for Day 11.

Important: the endpoint does not trust client-supplied hotspot coordinates or temperature. It reloads the verified Day 11 completion from cache, selects the hottest tile on the server, derives its representative point, and uses the verified tile temperature in the environmental request.

Response schema:

`heatshield.day12.live_decision_readiness.v1`

The response contains:

- selected verified hottest tile and thermal evidence ID;
- observed FortyGuard environmental thermal-stress values;
- derived heat-index band/hazard planning ordinal when supported;
- explicit decision-readiness states;
- controlled evidence-collection next checks;
- thermal + environmental activity IDs and evidence IDs;
- provider/cache accounting and safety flags.

## Evidence classification

**OBSERVED** — FortyGuard air temperature and environmental thermal-stress parameters.

**DERIVED** — relative hotspot rank, evidence linkage, metric deltas/completeness and the transparent hazard planning ordinal when an observed heat index is available.

**INFERRED** — none for occupancy, operational vulnerability, adaptive capacity or individual medical risk.

**RECOMMENDED** — evidence-collection checks only. Day 12 does not recommend a site intervention from thermal evidence alone.

## Why priority is withheld

The existing HeatShield planning-priority model requires more than hazard. Day 12 therefore does not silently set missing exposure, vulnerability or protection context to zero. The UI explicitly lists these as missing and keeps planning priority withheld.

HeatShield also does not substitute air temperature or apparent temperature into an absent heat-index value. If observed heat index is unavailable, the hazard ordinal is withheld too.

## Credit safety

The enrichment button is explicit because it can create a provider job.

- Day 12 never creates a second heatmap job during enrichment.
- Completed environmental requests are fingerprinted and cached under `backend/data/cache/day12/`.
- Repeating the identical enrichment reuses the validated completion.
- Automated tests and smoke verification use local fixtures and spend **zero real FortyGuard credits**.

## Verification

The installer verifies:

- the complete pytest regression suite;
- the historical Day 10 judge-dashboard smoke;
- the Day 11 live thermal/cache smoke;
- the Day 12 live decision-readiness/cache smoke;
- local Qwen when Ollama is available.
