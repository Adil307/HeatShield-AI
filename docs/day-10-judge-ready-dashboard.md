# Day 10 — Judge-Ready HeatShield Dashboard

## Objective

Turn the verified HeatShield backend into a competition-facing decision interface without weakening the evidence contract.

## Architecture

```text
FortyGuard historical thermal evidence
        ↓
Day 7 explainability packets + Day 8 controlled actions
        ↓
Dashboard snapshot adapter (zero network)
        ↓
Offline-native SVG thermal field
        ↓
Priority / evidence / action panels
        ↓
Local Qwen3 1.7B intent router
        ↓
Deterministic materializer + Evidence Guard + renderer
```

## Judge demo flow

1. Open the dashboard and establish that FortyGuard is the authoritative thermal source.
2. Show the thermal field and the three priority candidates.
3. Point out that the hottest tile is not automatically the highest planning priority.
4. Select hotspot rank 2 and show the transparent score decomposition.
5. Show UNKNOWN operational vulnerability/adaptive capacity and WITHHELD medical-risk probability.
6. Show catalog-controlled actions.
7. Ask the local Copilot why hotspot 2 is prioritized.
8. Explain that the LLM routes intent only; deterministic HeatShield evidence writes the factual answer.

## Scope

The current dashboard is intentionally a scenario replay, not a live-current heat claim: historical FortyGuard thermal evidence is evaluated against current mapped urban context. Planning priority is not a medical-risk probability and mapped objects are not people.

A future new-area workflow can trigger fresh FortyGuard analysis. Rendering this verified scenario makes zero new FortyGuard or Overpass calls.

## Runtime

From repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\RUN_DAY10_DASHBOARD.ps1
```

Direct URL:

```text
http://127.0.0.1:8000/dashboard/
```

## Verification

```powershell
cd backend
pytest -q
python -m scripts.day10_dashboard_smoke_test
python -m scripts.day9_local_qwen_smoke_test
```
