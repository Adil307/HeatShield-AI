# Day 10.2.1 — Frontend Contract Migration

## Why this patch exists

Day 10.2 intentionally replaced parts of the Day 10.1 information architecture.
The UI upgrade was valid, but three older regression tests were still asserting
Day 10.1 implementation details:

- exact asset version `10.1.1`;
- old DOM IDs such as `rankingList`, `detailTitle`, `metricGrid`, and `actionList`;
- exact CSS text `position: fixed` including whitespace.

Those tests were testing the previous implementation rather than stable product behavior.

## What changed

The tests now validate durable UX contracts:

- CSS and JS assets must both be cache-versioned and use the same version;
- the dashboard must expose a sidebar, KPIs, thermal map, selected hotspot,
  priority composition, comparison, recommendations, and Copilot;
- the Copilot must remain a fixed drawer;
- FortyGuard provenance and safety language must remain visible.

No production decision logic, evidence values, provider calls, Qwen behavior,
or dashboard data contract is changed by this patch.
