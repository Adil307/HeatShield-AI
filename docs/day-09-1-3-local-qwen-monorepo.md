# Day 9.1.3 — Monorepo Local Qwen Grounded Copilot

## Purpose

Integrate the verified local `qwen3:1.7b` Ollama planner into the current `backend/` monorepo architecture without weakening HeatShield's evidence controls.

## Architecture

`User query -> local Qwen intent router -> deterministic route materializer -> plan validator -> Day 7 evidence guard / Day 8 controlled recommendations -> deterministic factual renderer`

The local model is intentionally restricted to two output fields:

- `intent`
- `primary_hotspot_rank`

It never authors evidence keys, recommendation IDs, thermal values, people counts, medical probabilities, or the final factual answer.

## Reliability hardening

- Deterministic safety routing overrides the local model for current/live heat, medical-risk probability, and people-exposure requests.
- Strong deterministic intent matches (`why_priority`, `recommendations`, `missing_evidence`, `compare_hotspots`, `metric_lookup`) cannot be downgraded by the 1.7B model.
- Explicit hotspot/tile resolution is deterministic.
- Recommendation IDs are materialized only from the target hotspot's verified Day 8 catalog.
- Metric identity is materialized only from the deterministic alias resolver.
- Invalid local JSON fails closed.
- `mode=auto` falls back to the deterministic planner if Ollama is unavailable.
- `mode=ollama` fails explicitly if local inference cannot be completed.

## FortyGuard role

FortyGuard remains the authoritative thermal evidence source. Copilot Q&A does not re-call FortyGuard for every question; it consumes the already verified evidence chain and preserves provenance. A new area/time analysis still requires the normal FortyGuard workflow.

## Local runtime

- Ollama: local host, default `http://localhost:11434`
- Model: `qwen3:1.7b`
- No cloud LLM key is required for local inference.
- Local smoke artifacts remain under ignored `backend/data/processed/`.

## Validation target

The installer runs:

1. Python compile checks.
2. The complete backend regression suite.
3. One real `qwen3:1.7b` Ollama smoke inference.
4. The complete regression suite again.
5. Git secret/artifact safety checks.
6. A guarded commit and push only if `origin/main` has not advanced during validation.
