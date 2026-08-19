# Day 5 - Transparent Planning Priority Engine

## Goal

Convert the verified Day 4.4 scenario replay into a deterministic, evidence-linked planning priority while refusing to invent individual vulnerability or adaptive capacity.

This milestone is intentionally **not** a medical/clinical risk model. It ranks planning attention for a scenario that replays a verified historical FortyGuard thermal event against current mapped urban context.

## Inputs

- Verified Day 4.4 scenario-replay artifact.
- Observed FortyGuard heat index and other environmental evidence inherited from Day 3.
- Complete current OpenStreetMap mapped-context coverage inherited from Day 4.4.
- No new external API calls.

## Hazard method

HeatShield v1 uses the observed heat index and the public National Weather Service heat-index classification as an interpretable category anchor:

- below 80 F: below NWS caution band
- 80 to <90 F: caution
- 90 to <103 F: extreme caution
- 103 to <125 F: danger
- 125 F or higher: extreme danger

HeatShield maps these categories to ordinal planning values 20/40/60/80/100. Those values are **HeatShield planning ordinals**, not NWS probabilities and not medical-risk percentages.

Reference: https://www.weather.gov/ama/heatindex

## Why Heat Index Is Not Enough

NIOSH states that heat stress depends on environmental heat plus factors such as metabolic heat, clothing/PPE, acclimatization, hydration, physical condition and other conditions. Therefore Day 5 does not transform heat index alone into a human health probability.

Reference: https://www.cdc.gov/niosh/heat-stress/about/

## Mapped exposure proxy

Raw OSM object count is not treated as population or occupancy. Each of five categories is represented equally:

1. healthcare
2. education
3. transit waiting
4. outdoor public
5. civic/public

Each category count is logarithmically saturated at 20 objects before averaging. This prevents a feature such as a park represented by many polygons from dominating merely because of map segmentation.

## Context-sensitivity proxy

Healthcare and education presence create a conservative place-type sensitivity proxy. It is not individual vulnerability and is not allowed to become a medical claim.

## Priority formula

Baseline prototype:

`P_pre = 0.60 * H + 0.30 * E + 0.10 * S`

Where:

- `H` = NWS-anchored HeatShield hazard ordinal
- `E` = capped mapped-exposure proxy
- `S` = conservative context-sensitivity proxy

The weights are versioned prototype planning weights, not validated epidemiological coefficients. Day 5 therefore performs alternative hazard-heavy and context-heavy weight tests and records whether ranking is stable.

## Vulnerability and adaptive capacity

Day 5 refuses to guess these dimensions.

- Individual vulnerability: `UNKNOWN_NOT_OBSERVED`
- Adaptive capacity: `UNKNOWN_NOT_OBSERVED`
- Final adjusted risk score: `WITHHELD`

A future verified layer can provide evidence for shade, cooling access, hydration, work/rest controls, occupancy/activity, sensitive populations, or other adaptation/vulnerability factors. Until then HeatShield exposes only `pre_adaptation_priority_score`.

## Complexity

For `h` hotspots and fixed `c=5` mapped-context categories:

- artifact validation: O(h*c) = O(h)
- scoring: O(h*c) = O(h)
- three-set sensitivity analysis: O(3*h*c) = O(h)
- ranking: O(h log h)
- network calls: 0

## Scientific guardrails

- Missing evidence is not converted to zero.
- No population is inferred from OSM object count.
- No medical vulnerability is inferred from healthcare/education presence.
- Heat index bands are not presented as probabilities.
- No final risk score is issued without verified vulnerability/adaptive-capacity evidence.
- Historical hazard + current context remains explicitly labeled a cross-time scenario replay.

## Run

From `backend/` with `.venv` active:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m scripts.day5_priority_analysis
```

Output: `backend/data/processed/day5_planning_priority.json` (gitignored).
