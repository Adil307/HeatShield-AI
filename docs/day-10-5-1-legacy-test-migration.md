# Day 10.5.1 — Single-Workspace Legacy Test Migration

Day 10.5 was applied correctly. The failed suite was caused by three older
regression assertions that still described Day 10.4:

- `app.js?v=10.4.0`;
- a second Day 10.4 asset-version assertion;
- an exact old Copilot sentence.

Day 10.5 intentionally changes the UI architecture to a single-workspace SPA
and uses `app.js?v=10.5.0`. The local Qwen safety contract is still preserved:
Qwen routes intent locally and the deterministic evidence renderer remains the
factual authority.

This recovery patch updates only the stale regression contracts. It does not
change FortyGuard evidence, planning scores, map data, recommendation logic,
or Qwen behavior.
