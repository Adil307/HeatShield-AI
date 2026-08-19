# HeatShield AI — Day 15 Live Scenario Studio

Day 15 adds a controlled what-if comparison to the completed live evidence chain.

## Purpose

Scenario Studio starts from the verified Day 13 live baseline and asks a narrow planning question:

> If an explicitly selected operational factor were different, how would the same transparent planning index change while the verified thermal hazard is held constant?

This is a **scenario estimate**, not a measured future outcome.

## Runtime flow

1. Reuse the completed Day 11 FortyGuard TCM cache.
2. Reuse the completed Day 12 environmental/thermal-stress cache.
3. Reconstruct the exact Day 13 authorized context and verified baseline planning priority.
4. Apply only the explicit Day 15 scenario overrides.
5. Keep the verified thermal-hazard ordinal fixed.
6. Recompute exposure/sensitivity/vulnerability/adaptive-capacity components with the same transparent Day 13 formulas.
7. Return baseline vs scenario priority, band, delta, assumptions, and provenance.

The Day 15 scenario step creates **zero new FortyGuard jobs** and **zero LLM calls**.

## Supported v1 scenario presets

- Assume all protective controls are adequate.
- Assume shaded/cooled recovery is adequate.
- Assume work-rest controls are adequate.
- Assume exposure is one level lower.
- Assume physical exertion is one level lower.
- Assume stronger controls plus one-level lower exposure.

The backend receives explicit factor targets; the scenario engine never infers hidden changes from the map or an LLM.

## Evidence classification

- **OBSERVED / VERIFIED** — existing FortyGuard thermal/environmental evidence and the authorized Day 13 baseline context.
- **ASSUMED** — only the explicit factor changes selected for the scenario.
- **DERIVED** — scenario priority recomputed with the existing transparent Day 13 formulas.
- **RECOMMENDED** — comparison is for evaluation only; no guaranteed outcome is claimed.

## Safety boundary

Day 15 v1 intentionally does **not**:

- predict a site-specific temperature reduction;
- turn shade/control assumptions into degrees Celsius;
- simulate a different time window without fresh provider evidence;
- infer a medical-risk probability or individual health outcome;
- invent people/occupancy counts;
- relabel scenario assumptions as observations.

A future time-shift scenario must request or reuse FortyGuard evidence for that new time window before the hazard term can change.

## API

`POST /api/v1/dashboard/live-analysis/scenario`

The request contains the exact Day 13 `context_request`, a scenario label, and explicit `scenario_changes`.

The response schema is:

`heatshield.day15.live_scenario_studio.v1`

## Demo story

1. Complete a fresh live analysis.
2. Enrich the hottest tile.
3. Verify source-backed operational context.
4. Open Scenario Studio.
5. Choose one controlled what-if preset.
6. Show the verified baseline, scenario estimate, priority delta, and changed assumptions.
7. Point out that thermal hazard is held constant and no temperature reduction is claimed.
