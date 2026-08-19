# Day 4.4 — Evidence-Safe Scenario Replay Baseline

## Why this mode exists

The near-current FortyGuard heatmap jobs were accepted and completed but returned zero GeoJSON features for both a near-current candidate and a bounded 24-hour fallback. HeatShield treats those completed-empty responses as unavailable thermal evidence, not zero heat, and does not keep probing blindly.

Day 4.4 therefore creates an explicit **planning scenario replay** without making new FortyGuard heatmap requests:

- historical hazard/environmental evidence: verified Day 1–3 FortyGuard artifact;
- current urban context: current OpenStreetMap/Overpass mapped places;
- derived overlay: which current mapped contexts would lie near the same thermal hotspots if that verified heat pattern recurred.

This is **not** a live heat map and **not** a historical exposure reconstruction.

## Correctness rules

1. The Day 3 heatmap SHA-256 must still match the raw verified FortyGuard artifact.
2. Historical environmental timestamps must be aligned across selected hotspots.
3. Current OSM is queried without `[date:...]`, avoiding historical attic lookup cost.
4. Five small category queries are used: healthcare, education, transit waiting, outdoor public, civic/public.
5. HTTP 200 responses containing Overpass `remark` runtime errors are rejected.
6. Provider failure means `unknown`, never zero.
7. The historical-to-current temporal gap is stored explicitly in the artifact.
8. No new FortyGuard heatmap request is made by this mode.

## Complexity

For `k` selected hotspots and `p` returned context places:

- source/provenance validation: O(k + file_size)
- query-plan construction: O(k)
- current context parsing/deduplication: O(p)
- spatial assignment: approximately O(p + a) using the existing hotspot spatial buckets, followed by exact Haversine checks for candidate assignments `a`

The number of OSM category queries is fixed at five; endpoint failover is sequential and bounded.

## Run

From `backend/` with `.venv` active:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m scripts.day44_scenario_replay
```

## Output

`backend/data/processed/day44_scenario_replay.json` (ignored by `backend/.gitignore`)

The artifact labels evidence as historical observed, current observed, derived, inferred, or recommended so later risk logic cannot silently treat the replay as current reality.
