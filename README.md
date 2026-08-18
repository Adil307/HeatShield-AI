# HeatShield AI — Day 1 Foundation

This is the first implementation milestone for the Global AI Hackathon'26 project.

## Day 1 objective

Prove the real FortyGuard provider integration before building AI/risk logic.

1. Read the API key securely from `.env`.
2. Submit `POST /v1/heatmap`.
3. Capture the returned `activity_id`.
4. Poll `GET /v1/status/{activity_id}`.
5. Receive `map_data` + `stats_data`.
6. Save the real result locally.

## Setup — Windows PowerShell

```powershell
cd heatshield-ai

py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt

Copy-Item .env.example .env
```

Edit `.env` and place the real key locally:

```text
FORTYGUARD_API_KEY=YOUR_REAL_KEY
```

Never send the key in chat, commit it to GitHub, or expose it in frontend code.

## Start backend

```powershell
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000/docs
```

Useful endpoints:

- `GET /health`
- `GET /api/v1/fortyguard/config-status`
- `POST /api/v1/fortyguard/heatmap/submit`
- `GET /api/v1/fortyguard/status/{activity_id}`
- `POST /api/v1/fortyguard/heatmap/run`

## First real FortyGuard test

In another terminal:

```powershell
python scripts/first_heatmap_test.py
```

Expected flow:

```text
Submitting real FortyGuard heatmap request...
Activity ID: <uuid>
Polling until completion...
Final status: Completed

GeoJSON feature count: ...
stats_data present: True
Saved result: data/raw/first_heatmap_result.json
```

If it fails, share only the HTTP status and provider error message — never the API key.

## Day 1 completion condition

Day 1 is complete only when:

- a real `activity_id` is returned;
- status reaches `Completed`;
- `map_data` is present;
- `stats_data` is present;
- the raw result is saved;
- the API key is not exposed.

Next milestone: **Day 2 — Heatmap parser + GeoJSON validation + hotspot extraction.**


## Day 02 - Thermal Hotspot Intelligence

HeatShield validates completed FortyGuard GeoJSON, independently verifies temperature statistics, and derives deterministic AOI-relative hotspot candidates with SHA-256-linked evidence IDs. The bounded top-k detector runs in O(n log k) selection time and intentionally does not claim human heat risk yet.

See `docs/day-02-hotspot-intelligence.md` for design boundaries, complexity, provenance, and failure behavior.

## Day 3 - Environmental Thermal Context

HeatShield enriches a small set of Day-2 thermal hotspot candidates with FortyGuard environmental parameters. The pipeline verifies Day-1/Day-2 provenance, derives a representative point per tile, uses deterministic request fingerprints and local completed-response caching, and links environmental evidence back to each thermal evidence ID. Day 3 preserves the distinction between observed provider values and transparent derived metadata; it does not yet claim population or clinical heat risk.

## Day 4 - Exposure Context Intelligence

HeatShield links Day-3 thermal/environmental evidence to time-aligned OpenStreetMap context candidates around each hotspot. It uses a single historical bounding-box Overpass query, deterministic context taxonomy, local spatial indexing, exact distance checks, provenance hashes, response caching, and explicit OSM attribution. Day 4 does not infer population counts, occupancy, vulnerability or health risk from mapped-place presence or absence.

## Day 4.2 - Resilient Historical Context Retrieval

Historical OpenStreetMap context retrieval now uses five small category-specific bbox queries, semantic-success validation, sequential failover across three public global/attic Overpass instances, and category-level availability states. Provider failure is represented as unknown/unavailable and is never converted into a zero context count.

### Day 4.4 - Evidence-Safe Scenario Replay
When near-current FortyGuard heatmaps completed with zero GeoJSON features, HeatShield did not treat them as zero heat or keep spending credits. The verified historical thermal/environmental event can instead be replayed against current mapped OSM context as an explicitly cross-time planning scenario. Historical hazard, current context, temporal gap, provider availability, and provenance remain separate evidence fields.

## Day 5 - Transparent Planning Priority Engine

Day 5 converts the evidence-safe Day 4.4 scenario replay into a deterministic planning-priority ranking. It uses an NWS-anchored heat-index hazard ordinal, capped mapped-context exposure, and a conservative place-type sensitivity proxy. Individual vulnerability and adaptive capacity remain unknown unless directly verified, so HeatShield intentionally withholds a final medical/risk score. The engine records factor explanations, evidence IDs, alternative weight sets, and ranking stability without making new network calls.

## Day 6 - Verified Vulnerability and Adaptive Capacity Evidence Layer

Day 6 adds a human-in-the-loop operational evidence layer for vulnerability and adaptive capacity. HeatShield never infers exertion, acclimatization, PPE/clothing, hydration, recovery, work-rest controls, or training from OSM, temperature, or an LLM. Unknown factors remain unknown. An evidence-adjusted planning priority is unlocked only when every required factor is explicitly verified, while medical/clinical risk remains outside the model. Day 6 makes no provider/API calls.

## Day 7 - Explainability and Evidence Guard

HeatShield now produces deterministic explanation packets over the verified Day 4.4 -> Day 5 -> Day 6 provenance chain. Each claimable value is classified as observed or derived, while missing evidence remains unknown and policy-blocked outputs remain withheld. The structured Evidence Guard approves only exact ledger-grounded claims, rejects medical-risk probability and semantic overclaims, and requires free-form AI text to be decomposed into structured grounded claims before rendering. Day 7 makes zero provider/API/LLM calls.


## Day 8 - Controlled Action Recommendation Engine

Day 8 adds a deterministic, versioned recommendation catalog grounded in the Day 7 evidence ledger. Actions are emitted only when catalog triggers are satisfied, carry exact triggering evidence and authoritative source IDs, and pass a recommendation guard. Unknown operational factors trigger verification rather than being treated as absent. No provider, Overpass, or LLM calls are required.


## Day 9 - Grounded AI Copilot Core

Day 9 adds a conversational copilot over the verified Day 7 evidence ledger and Day 8 controlled recommendation catalog. The safe default is deterministic and makes zero LLM calls. An optional OpenAI Responses API planner can be enabled, but the model may only select whitelisted evidence keys and guard-approved recommendation IDs; it never writes the final factual answer. Final wording is rendered deterministically and every structured claim is rechecked against the Day 7 Claim Guard.

Key safety rules: historical thermal evidence is not current heat; mapped OSM objects are not people/occupancy; medical risk probability is never produced; unknown evidence is not defaulted to zero; actions remain catalog-controlled.
