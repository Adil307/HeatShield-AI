# Day 10.8.1 — Evidence Label Contract Recovery

## Why this recovery exists

The Day 10.8 interface successfully added two map modes and human-facing labels, but one legacy Day 10.4 UI contract still required the evidence status headings to remain visible with their canonical human-readable capitalization.

The affected headings were already semantically correct, but their letter case changed during the Day 10.8 polish pass:

- `Operational vulnerability` → `Operational Vulnerability`
- `Adaptive capacity` → `Adaptive Capacity`
- `Medical risk probability` → `Medical Risk Probability`

## Scope

This recovery changes presentation text only. It does not change:

- FortyGuard data or provider calls;
- the planning-priority formula;
- evidence classifications;
- recommendation logic;
- Copilot grounding;
- map geometry or heat rendering;
- Satellite / Simple Map behavior.

## Verification

The recovered snapshot passes the complete backend/frontend contract suite and the dashboard evidence smoke test. The safety statement remains visible: HeatShield does not convert planning priority into a medical-risk probability, and mapped objects are not interpreted as people or occupancy.
