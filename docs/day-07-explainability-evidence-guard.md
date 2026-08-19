# Day 7 - Explainability and Evidence Guard

## Objective

Day 7 converts HeatShield's verified Day 4.4 -> Day 5 -> Day 6 evidence chain into deterministic, machine-readable explanation packets and a claim-grounding guard for future UI/LLM layers.

The layer is deliberately **not an LLM**. It does not generate medical conclusions and it does not authorize free-form text merely because it sounds plausible.

## Evidence classes

Every ledger item is explicitly classified as one of:

- `observed` - provider, mapped, or verified operator evidence carried through provenance;
- `derived` - deterministic HeatShield calculations that can be recomputed;
- `unknown` - required evidence is not verified and no value may be invented;
- `withheld` - HeatShield intentionally does not produce the value under the current evidence/policy scope.

## Provenance chain

Day 7 verifies the byte-level SHA-256 chain before building explanations:

```text
Day 6 evidence artifact
  -> declared Day 5 SHA-256
Day 5 priority artifact
  -> declared Day 4.4 SHA-256
Day 4.4 scenario replay artifact
```

A mismatch fails closed.

## Exact score decomposition

For each hotspot the Day 5 baseline planning priority is decomposed into additive weighted points:

```text
priority = hazard_score * hazard_weight
         + mapped_exposure_score * mapped_exposure_weight
         + context_sensitivity_proxy * context_sensitivity_weight
```

Day 7 verifies the contribution sum exactly reconstructs the stored Day 5 priority within a small numeric tolerance. An explanation is not produced if the decomposition does not match.

## Claim Guard

The structured Claim Guard supports only:

- `metric_assertion`
- `status_assertion`
- exact `scenario_statement`

An observed/derived metric assertion is approved only when the claimed value exactly matches the evidence ledger. Unknown/withheld metrics cannot be asserted as values.

Examples:

```text
historical_heat_index_celsius = verified ledger value
-> APPROVE

pre_adaptation_planning_priority = exact derived value
-> APPROVE

verified_operational_vulnerability = 0
when ledger classification is unknown
-> REJECT

medical_risk_probability = 70%
-> REJECT
```

## Natural-language safety boundary

The free-text scanner is only defense-in-depth. It blocks high-risk semantic patterns such as:

- historical hazard described as current/live heat;
- OSM mapped objects described as exposed people/population;
- medical/clinical probability claims;
- unsupported individual safety/illness certainty.

Free text that does not trigger a red flag is still **not approved**. Factual clauses must first be converted into structured claims and grounded against the ledger.

This becomes the contract for a later grounded AI Copilot:

```text
LLM draft
  -> structured factual claims
  -> Evidence Guard
  -> only approved claims may be rendered
```

## Scenario semantics

The Day 4.4 data intentionally combines:

- a verified historical FortyGuard hazard event; and
- current mapped OSM context.

Therefore Day 7 preserves the temporal gap in every explanation packet. The system must not call the historical thermal evidence current/live heat and must not call current mapped context a reconstruction of historical exposure.

## API endpoints

Day 7 exposes local read/guard endpoints for future frontend and Copilot integration:

```text
GET  /api/v1/decision/explainability
GET  /api/v1/decision/explainability/{hotspot_rank}
POST /api/v1/decision/claim-guard/evaluate
POST /api/v1/decision/claim-guard/screen-text
```

These endpoints do not call FortyGuard, Overpass, or an LLM.

## Complexity

For `h` hotspots and `e` ledger entries per hotspot:

```text
artifact validation / indexing     O(h)
explanation construction           O(h * e)
claim lookup                       O(e) per packet in v1
API artifact read                  O(file size)
network provider calls             0
```

The hotspot count is currently small. A future long-lived API process can cache the packet index in memory if needed.

## Non-claims

Day 7 does not produce:

- medical/clinical risk probability;
- mortality/illness probability;
- actual exposed-person counts;
- current heat from the historical replay;
- recommendations;
- autonomous LLM reasoning.

Recommendations belong to the controlled recommendation layer after Day 7.

## Run

From `backend/` with `.venv` active:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m scripts.day7_explainability_guard
```

Start the API from the same folder with `uvicorn app.main:app --reload`. Output: `backend/data/processed/day7_explainability_guard.json` (ignored by `backend/.gitignore`).
