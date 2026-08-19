# Running backend tests

Days 2–6 tests build fake inputs in memory. Days 7–9 tests read **real local artifacts** under `data/processed/`. Those files are ignored by `backend/.gitignore` and are not in Git.

On a clean checkout, `pytest -q` will collect, then fail Days 7–9 with `Cannot read Day 6/7/8 artifact` until this recipe has been run once.

All commands below assume:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
```

`backend/.env` must contain a real `FORTYGUARD_API_KEY`.

## Clean checkout — generate the evidence chain

Run in this order. Stop if a step fails.

**1. Heatmap (FortyGuard credits)**

`scripts/first_heatmap_test.py` uses the official control AOI: lower Manhattan, `2024-07-15` at `14:00`.

```powershell
python -m scripts.first_heatmap_test
```

The job must be `Completed` with a **non-zero** GeoJSON feature count. A completed heatmap with `features: []` is not zero heat; Day 2 will refuse it. Do not continue on that file. Near-current dates often return empty tiles; keep the historical control date.

Saved to `data/raw/first_heatmap_result.json`.

**2. Hotspots (local)**

Day 2 defaults to a different filename, so pass the Day 1 output:

```powershell
python -m scripts.day2_hotspot_analysis --input data/raw/first_heatmap_result.json
```

**3. Environmental parameters (FortyGuard credits)**

Date/time must match the heatmap you actually ran:

```powershell
python -m scripts.day3_environmental_enrichment --start-date 2024-07-15 --start-time 14:00 --limit 3
```

**4. Scenario replay (OpenStreetMap, no new heatmap)**

```powershell
python -m scripts.day44_scenario_replay
```

**5–8. Local chain (no FortyGuard, no OSM)**

```powershell
python -m scripts.day5_priority_analysis
python -m scripts.day6_evidence_layer
python -m scripts.day7_explainability_guard
python -m scripts.day8_recommendation_engine
```

Day 4 and Day 4.3 are not required for the current pytest suite.

**9. Tests**

```powershell
pytest -q
```

Expected: all tests passed. A Starlette/`httpx` deprecation warning from FastAPI’s test client can be ignored.

## After setup — run tests again

If `data/processed/` already has:

- `day44_scenario_replay.json`
- `day5_planning_priority.json`
- `day6_site_evidence_layer.json`
- `day7_explainability_guard.json`
- `day8_controlled_recommendations.json`

then only:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest -q
```

No provider calls. Re-run the recipe only if those files are missing, deleted, or you need a fresh evidence chain.

## Files the Day 7–9 tests open

| File | Produced by |
|---|---|
| `data/processed/day44_scenario_replay.json` | `day44_scenario_replay` |
| `data/processed/day5_planning_priority.json` | `day5_priority_analysis` |
| `data/processed/day6_site_evidence_layer.json` | `day6_evidence_layer` |
| `data/processed/day7_explainability_guard.json` | `day7_explainability_guard` |
| `data/processed/day8_controlled_recommendations.json` | `day8_recommendation_engine` |
| `config/day8_action_catalog.json` | committed in the repo |

## Common failures

| Symptom | Cause |
|---|---|
| `No module named 'app'` | Not in `backend/`, or `.venv` not active. `pytest.ini` sets `pythonpath = .`. |
| `GeoJSON feature count: 0` then Day 2 fails | Empty completed heatmap. Use the official historical AOI/date, not a near-current request. |
| `Cannot read Day 6/7/8 artifact` | Clean checkout; `data/processed/` is gitignored. Run the recipe above. |
| Day 3 date mismatch | `--start-date` / `--start-time` must match the heatmap request. |
