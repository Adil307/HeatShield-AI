# HeatShield AI — Build 15.1
## 28 Aug Milestone Target: UI Polish & Demo Reliability

This build keeps the working live-analysis, priority, grounded-copilot, and Scenario Studio logic unchanged. It focuses on judge-demo reliability and removes the confusion between internal build counters and the official 18–30 August execution calendar.

## Changes

- Fix the stale `Verified live baseline required` banner once a baseline exists.
- Persist the verified live context baseline in `sessionStorage` so a page refresh in the same browser tab does not force the user to repeat the entire live workflow.
- Persist the most recent Scenario Studio result in the same tab and restore it after refresh.
- Clear the saved baseline whenever a new thermal analysis or enrichment invalidates the old context chain, or when the user resets live analysis.
- Show an explicit notice when the baseline was restored from browser-session state.
- Present the context source as an `Operator evidence reference` with `Authorized operator input` as the source type.
- Remove internal `Day 12 / Day 13 / Day 14 / Day 15` counters from judge-facing UI copy. Internal history, test names, schemas, and Git commits remain unchanged for traceability.
- Bump the dashboard asset to `app.js?v=15.1.0`.

## Safety / evidence boundary

Browser-session recovery does not create new evidence and does not change scores. It restores the exact verified context request and derived result that were already present in the current tab. Scenario comparison continues to make zero new FortyGuard calls and zero LLM calls, and it does not predict a physical temperature reduction or a medical-risk probability.

## Acceptance

- Full pytest suite passes.
- Day 10–15 smoke chain remains PASS.
- JavaScript syntax passes when Node.js is available.
- Scenario lock banner hides correctly after verification.
- Refresh in the same tab restores the verified baseline and most recent scenario result.
- A new live analysis/enrichment/reset clears the saved baseline.
