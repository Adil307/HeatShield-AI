# Day 10.6.1 — Responsive UI Test Contract Recovery

Day 10.6 itself applied successfully. The regression suite had two stale test
assertions:

1. An older UI contract still required the text `Controlled Recommendations`,
   while Day 10.6 intentionally humanized this visible label to
   `Recommended Next Checks`.

2. The Day 10.6 real-data test required the exact JavaScript expression
   `summary.highest_priority_score`, while the renderer validly aliases the
   summary object to another local variable before reading the same backend
   field.

This recovery updates only tests so they validate stable product behavior:

- the humanized Day 10.6 information architecture;
- responsive breakpoints;
- no hard-coded demo metrics;
- live dashboard values loaded from `/api/v1/dashboard/overview`;
- assistant status and answers loaded from the backend;
- selected-hotspot quick prompts generated from runtime state.

No production evidence, FortyGuard integration, planning score, recommendation,
map, or local-Qwen behavior is changed.
