# Day 14 — Live Grounded Copilot

Day 14 connects the existing local HeatShield assistant to the completed Day 11 → Day 12 → Day 13 live evidence chain.

## Objective

After a fresh FortyGuard thermal job, hottest-tile environmental enrichment, and explicit operator context verification are complete, the assistant can answer questions about that exact live analysis without switching back to the historical replay.

## Trust boundary

The local Qwen model is an **intent router only**. It receives no numeric evidence and does not write the final factual answer. HeatShield reconstructs the verified live packet from cache plus the submitted Day 13 context, selects evidence deterministically, and uses a deterministic renderer for factual output.

Day 14 therefore keeps the same project separation:

- **OBSERVED** — fresh FortyGuard temperature and environmental parameters, plus explicit authorized operational context.
- **DERIVED** — hazard ordinal, transparent score components, pre-adaptation priority, operational adjustment, evidence-adjusted planning priority and band.
- **RECOMMENDED** — only actions already present in the Day 8 controlled action catalog whose documented trigger is satisfied.
- **UNSUPPORTED** — medical/clinical risk probability, diagnosis, people or occupancy counts, individual vulnerability inference, and full decision-priority comparisons for live tiles that have not received equivalent enrichment/context.

## Runtime flow

1. Browser keeps the exact successful Day 13 `analysis_request + context_profile` in local page state.
2. User asks the assistant a question.
3. Browser sends the question to `POST /api/v1/dashboard/live-analysis/copilot`.
4. Backend reuses verified Day 11 and Day 12 caches and deterministically recomputes Day 13 priority from the submitted context.
5. A deterministic router handles explicit/safety-sensitive intent. When configured, local Qwen may route ambiguous intent only.
6. The deterministic live evidence renderer produces the factual answer from a bounded ledger.
7. Response returns evidence references, approved claims, controlled recommendation IDs, planner/runtime metadata, and safety flags.

## Supported live questions

- Why does the current live priority have this value?
- What is the current air temperature / heat index / apparent temperature / wet-bulb / humidity?
- Which factors raise or lower the priority?
- What evidence and activity IDs support the result?
- What controlled action is currently triggered?
- What is verified and what remains unsupported?
- What can safely be compared across the relative hottest tiles?

## Comparison boundary

The Day 11 thermal layer can compare the hottest tiles by fresh temperature. Day 14 does **not** compare full planning priorities across tiles unless each tile has equivalent Day 12 environmental enrichment and Day 13 authorized context.

## Provider and credit behavior

The Day 14 copilot step makes:

- **0 new FortyGuard heatmap calls**
- **0 new FortyGuard environmental calls**
- **0 new Overpass calls**
- **0 LLM-authored factual answers**

A local Qwen request may occur only for intent routing when Ollama is configured and selected.

## UI

Once Day 13 priority succeeds, the live result panel shows **Day 14 · Live Grounded Copilot** and an **Ask Assistant** button. The assistant context card switches from historical replay context to the fresh live packet automatically. Grounding metadata is shown under live assistant answers.

Day 14 also removes horizontal overflow from the live side panel so the Day 13/14 result remains judge-friendly on desktop.
