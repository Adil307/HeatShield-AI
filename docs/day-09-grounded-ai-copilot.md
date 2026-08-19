# Day 9 - Grounded AI Copilot Core

## Goal

Turn the Day 7 evidence ledger and Day 8 controlled action catalog into a conversational decision-support interface without allowing an LLM to become the source of truth.

## Architecture

1. Load and SHA-256 verify the Day 7 and Day 8 artifacts.
2. Build a compact whitelist containing hotspot ranks, evidence keys, and guard-approved recommendation IDs.
3. Route the user's question to a bounded intent.
4. Optional LLM mode may select only whitelist IDs using structured output.
5. Validate every selected evidence key, rank, and recommendation ID.
6. Render the final factual answer deterministically from verified artifacts.
7. Re-ground every observed/derived/status claim through the Day 7 Claim Guard.

The LLM never writes the final factual answer.

## Supported intents

- summary
- why priority
- controlled recommendations
- missing evidence
- compare hotspots
- metric lookup
- scenario-scope correction

## Safety invariants

- Historical thermal evidence is never called current/live heat.
- Mapped OSM objects are never converted into people or occupancy.
- Medical/clinical probability is never produced.
- Unknown evidence is never defaulted to zero.
- Actions must come from the Day 8 controlled catalog.
- An invalid LLM plan is rejected and `auto` mode falls back to the deterministic planner.
- Prompt injection cannot directly create factual output because the planner can only select validated IDs.

## Provider policy

`COPILOT_PROVIDER=deterministic` is the default in `backend/.env` and makes zero paid LLM calls. An OpenAI Responses API planner adapter is included as an opt-in provider (`COPILOT_PROVIDER=openai` plus `OPENAI_API_KEY`). Even in OpenAI mode, the model only chooses a structured plan; the deterministic evidence renderer creates the final answer.

The live provider smoke test is intentionally opt-in so installing or testing the project does not spend API credits unexpectedly.

## Complexity

For `h` hotspots, `e` evidence entries per hotspot, and `a` recommendations:

- artifact validation: O(h * (e + a))
- deterministic routing: O(query length)
- plan validation: O(e + a) for the selected hotspot
- final rendering and claim grounding: O(e + a)
- network calls in deterministic mode: 0
- optional LLM calls per user turn: at most 1

## API

- `GET /api/v1/copilot/status`
- `GET /api/v1/copilot/capabilities`
- `POST /api/v1/copilot/ask`

Start the API from `backend/` with `.venv` active:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
python -m scripts.day9_copilot_demo
```

Example request:

```json
{
  "query": "Why is hotspot 2 high priority?",
  "mode": "deterministic",
  "hotspot_rank": 2
}
```
