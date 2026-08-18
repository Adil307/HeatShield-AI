# Day 8 - Controlled Action Recommendation Engine

## Purpose

Day 8 converts the verified Day 7 evidence ledger into a small set of deterministic, auditable planning actions. It does **not** use an LLM to invent interventions and it does not produce medical advice.

## Safety model

Every recommendation must:

- exist in the versioned action catalog;
- have deterministic trigger conditions;
- carry the exact Day 7 evidence that activated it;
- cite a registered authoritative source basis;
- preserve the historical-hazard/current-context scenario semantics;
- state required verification and limitations; and
- pass the recommendation guard before it is emitted.

Unknown vulnerability or adaptive-capacity evidence triggers **verification**, never an assertion that a factor or control is absent.

## Controlled action families

1. Evidence verification for operational vulnerability factors.
2. Evidence verification for water, recovery, work-rest, and training/monitoring controls.
3. Public-space shade/recovery feasibility assessment when relevant mapped public-use context exists.
4. Tree/vegetation shade feasibility assessment as a long-term heat-island mitigation option.
5. Conditional worker heat-practice review only if actual outdoor/hot-environment work is confirmed.

## Authoritative basis

The action catalog uses current official guidance from CDC/NIOSH for workplace heat controls and US EPA for urban heat-island mitigation. HeatShield paraphrases these sources and does not claim that a generic control is automatically appropriate for a specific site.

## Non-claims

Day 8 never claims:

- a medical or clinical probability;
- that mapped objects equal people or occupancy;
- that the historical thermal event is current heat;
- that an unknown control is absent; or
- a site-specific temperature reduction from an intervention without a validated intervention model.

## Complexity

For `h` hotspots, `a` catalog actions, and small evidence ledger size `e`, trigger evaluation is `O(h*a*e)` in the simple implementation. The catalog is intentionally small, so runtime is effectively linear in hotspot count. No provider, Overpass, or LLM calls are made.
