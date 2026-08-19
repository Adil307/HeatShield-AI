# Day 02 - Thermal Hotspot Intelligence

## Objective
Convert a completed FortyGuard heatmap artifact into a validated, deterministic, provenance-linked list of **AOI-relative thermal hotspot candidates**.

## Scientific boundary
Day 02 does **not** compute human heat risk. It uses observed FortyGuard tile temperature and geometry, then derives AOI-relative ranking. Exposure, vulnerability, adaptive capacity, activity context, and interventions are intentionally excluded until later stages.

## Pipeline
1. Read the immutable completed FortyGuard JSON artifact.
2. Validate provider status, GeoJSON structure, unique tile IDs, finite temperatures, and polygon coordinates.
3. Recompute minimum, maximum, AOI-population standard deviation, and sample standard deviation locally.
4. Compare local statistics with provider `temperature_stats` and identify the provider standard-deviation convention. FortyGuard's verified artifact uses sample standard deviation (`n-1`). HeatShield retains population standard deviation for AOI-internal z-scores because the returned tiles are treated as the analyzed AOI population.
5. Select hottest top-k tiles using a bounded heap.
6. Compute AOI-relative z-score and min-max intensity.
7. Create deterministic evidence IDs linked to the raw artifact SHA-256.
8. Save a machine-readable derived artifact under `backend/data/processed/`.

## Complexity
Let `n` be the number of FortyGuard tiles, `v` the total geometry vertices, and `k` the number of retained hotspot candidates.

- JSON parsing and feature validation: O(n + v) time.
- Local temperature statistics: O(n) time.
- Raw artifact SHA-256: O(file_size) time with O(1) streaming hash memory.
- Hotspot selection: O(n log k) time with O(k) heap state.
- Final selected ranking: O(k log k).

The parser stores normalized tile records and geometry in memory, so normalized analysis memory is O(n + v), in addition to the standard JSON object loaded by Python. This is acceptable for the hackathon heatmap scale; streaming parsing can be introduced later if provider artifacts become very large.

## Provenance classes
- **Observed:** FortyGuard temperature and geometry.
- **Derived:** local validation, statistics, rank, z-score, relative intensity, evidence ID.
- **Inferred:** none on Day 02.
- **Recommended:** none on Day 02.

## Run

From `backend/` with `.venv` active:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m scripts.day2_hotspot_analysis
```

Schema audit:

```powershell
python -m scripts.day2_schema_audit
```

Tests:

```powershell
pytest -q
```

## Artifacts
- Raw evidence: `backend/data/raw/official_heatmap_completed.json`
- Derived result: `backend/data/processed/day2_hotspot_analysis.json`

Raw and derived provider data are ignored by `backend/.gitignore` unless the team later confirms that repository publication is appropriate.

## Failure behavior
The pipeline fails explicitly for invalid UTF-8/JSON, provider errors, non-completed status, zero features, duplicate tile IDs, invalid/non-finite temperatures, invalid polygon coordinates, inconsistent tile min/average/max, or provider/local statistics mismatch in the main Day 2 command. It never fabricates missing values.
