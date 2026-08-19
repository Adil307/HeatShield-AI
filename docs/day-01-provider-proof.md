# Day 01 — FortyGuard Provider Proof

## Goal

Prove the provider boundary before building HeatShield intelligence.

## Provider contract used

- Header: `api-key`
- Submit heatmap: `POST /v1/heatmap`
- Status/result: `GET /v1/status/{activity_id}`
- Granularity: 60 / 80 / 100 m
- Analytic types:
  - `tcm`
  - `time_of_measure`
  - `exceedance`
  - `persistence`

## Run

From `backend/` with `.venv` active:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m scripts.first_heatmap_test
```

The completed provider payload is saved to `backend/data/raw/first_heatmap_result.json` (ignored by `backend/.gitignore`). The API key stays in `backend/.env`.

## Evidence to save

- activity_id
- request payload without secret
- final status
- map_data feature count
- stats_data shape
- provider error payloads
- test timestamp

## Never save

- raw API key
- API key in screenshots
- API key in Git commits
