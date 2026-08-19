# Day 13 — Controlled Live Context Priority

Day 13 completes the live decision chain without weakening HeatShield's evidence boundary.

## Runtime flow

1. Day 11 supplies a verified, cached FortyGuard TCM live analysis.
2. Day 12 supplies a verified, cached FortyGuard Environmental Parameters enrichment for the server-selected hottest tile.
3. Day 13 accepts explicit source-backed operational context from an authorized operator.
4. HeatShield applies the existing transparent planning formulas and produces an evidence-adjusted operational planning priority.
5. Only actions already present in the Day 8 controlled action catalog may be surfaced.

Day 13 itself creates **zero FortyGuard jobs and zero LLM calls**.

## Required explicit context

The UI requires every field to be chosen; no substantive value is preselected:

- meaningful exposure level,
- sensitive-use context,
- physical exertion,
- acclimatization gap,
- heat-trapping PPE/clothing,
- potable water access,
- shaded/cooled recovery,
- work-rest controls,
- heat training/monitoring,
- auditable source reference and timestamp.

The operational context is not personal medical information and must not be used to enter individual diagnoses or health attributes.

## Transparent score chain

Day 13 reuses HeatShield's existing versioned functions:

- `hazard_ordinal_score` from observed FortyGuard heat index,
- `weighted_pre_adaptation_score(..., weight_set="baseline_v1")`,
- Day 6 operational vulnerability/adaptive-capacity level maps,
- `evidence_adjusted_score(..., modifier_strength=0.15)`,
- `priority_band`.

The live v1 composition is visible as contributions:

- 60% hazard planning ordinal,
- 30% explicitly verified exposure ordinal,
- 10% explicitly verified sensitive-use proxy,
- +15% of verified operational-vulnerability score,
- −15% of verified adaptive-capacity score.

This remains a prototype **operational planning priority**, not a medical-risk probability.

## Recommendation boundary

Day 13 does not ask an LLM to invent actions. The only live worksite action reusable without inventing mapped public-use context is `review_worker_heat_practices_if_applicable`, and it is surfaced only when its existing Day 8 catalog trigger (`hazard_planning_ordinal >= 60`) is met.

## Automated verification

The Day 13 smoke test uses local fixtures. It verifies a complete live evidence chain, context provenance, deterministic priority, controlled catalog action selection, zero provider calls in the context step, and the medical-risk boundary.
