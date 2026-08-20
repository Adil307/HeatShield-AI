# HeatShield AI

**Explainable urban heat decision intelligence built on verified FortyGuard temperature evidence.**

HeatShield AI converts provider-backed hyperlocal thermal evidence into a traceable decision workflow: fresh thermal analysis, hottest-tile enrichment, authorized operational context, transparent planning priority, controlled recommendations, a grounded local-Qwen copilot, and explicit what-if scenario comparison.

This repository is the Global AI Hackathon'26 build for **FortyGuard Auto Team 349**.

## What HeatShield does

HeatShield is not another weather map. FortyGuard supplies the temperature-intelligence layer; HeatShield adds the decision-intelligence layer.

```text
FortyGuard thermal evidence
        -> deterministic hotspot / thermal-stress evidence
        -> authorized operational context
        -> transparent planning priority + factor contributions
        -> controlled action catalog
        -> grounded assistant
        -> explicit scenario estimate
```

The product keeps four evidence classes separate:

- **OBSERVED / VERIFIED** - FortyGuard values and explicitly authorized operational context.
- **DERIVED** - deterministic HeatShield calculations with versioned formulas.
- **ASSUMED** - hypothetical Scenario Studio factor changes.
- **RECOMMENDED** - catalog-controlled actions or evidence checks.

HeatShield does **not** produce a medical-risk probability, infer people/occupancy from the map, or claim a guaranteed physical cooling outcome.

## Judge-ready workflow

1. **Historical replay** - repeatable evidence-backed judge path with temporal analytics and provenance.
2. **Live Analysis** - submit the current viewport as a controlled fresh FortyGuard TCM request.
3. **Thermal-stress enrichment** - enrich the verified hottest tile with available environmental parameters.
4. **Context verification** - explicitly enter authorized exposure, operational-vulnerability, and protection/control evidence.
5. **Planning priority** - calculate a transparent evidence-adjusted operational planning index and show factor contributions.
6. **Grounded Copilot** - local Qwen may route intent, while verified tools and deterministic rendering remain the source of factual claims.
7. **Scenario Studio** - compare the verified live baseline with explicit operational assumptions while holding verified thermal hazard constant.

## Architecture

```text
Browser dashboard
  |
  v
FastAPI dashboard contract
  |
  +-- FortyGuard adapter -> submit / poll / parse / cache
  +-- live thermal service
  +-- thermal-stress decision readiness
  +-- controlled context priority service
  +-- controlled recommendation catalog
  +-- live grounded copilot + Evidence Guard
  +-- Scenario Studio
  |
  v
Evidence/provenance packet + deterministic renderer
```

The browser never receives the FortyGuard API key and does not call FortyGuard directly.

## Repository layout

```text
heatshield-ai/
├── README.md
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── ai/
│   │   ├── providers/
│   │   ├── schemas/
│   │   └── services/
│   ├── config/
│   ├── scripts/
│   └── tests/
├── frontend/
│   └── dashboard/
├── docs/
└── demo/
```

Runtime evidence and caches live under `backend/data/` and are ignored by Git.

## Windows setup

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r .\backend\requirements.txt
Copy-Item .\backend\.env.example .\backend\.env
```

Edit `backend/.env` locally and set the real provider key:

```text
FORTYGUARD_API_KEY=YOUR_REAL_KEY
```

Never commit the key, paste it into chat, put it in screenshots, or expose it in frontend code.

## Start the final dashboard

```powershell
powershell -ExecutionPolicy Bypass -File .\RUN_FINAL_DASHBOARD.ps1
```

Open:

```text
http://127.0.0.1:8000/dashboard/
```

Useful workspaces:

```text
/dashboard/#thermal   Historical thermal replay
/dashboard/#live      Fresh controlled live analysis
/dashboard/#copilot   Grounded assistant
/dashboard/#scenario  Scenario Studio
```

## Live demo sequence

In one browser tab:

```text
Live Analysis
-> Run FortyGuard Analysis
-> Enrich Hottest Tile
-> Verify Context & Calculate Priority
-> Open Assistant
-> Open Scenario Studio
```

Use a small AOI and `100 m` granularity for the safest live demo. If the provider is slow or unavailable, switch to **Historical replay** rather than fabricating a live result.

## Final verification

Run the complete 29 August readiness gate:

```powershell
powershell -ExecutionPolicy Bypass -File .\RUN_29AUG_FINAL_READINESS.ps1
```

It runs:

- the complete pytest regression suite;
- historical dashboard smoke verification;
- live thermal, environmental-enrichment, context-priority, grounded-copilot, and Scenario Studio smoke checks;
- Build 15.1 refresh/persistence verification;
- final AI grounding metrics;
- final release/documentation checks;
- JavaScript syntax validation when Node.js is installed;
- whitespace checks.

The automated readiness gate uses fixtures/caches and **does not spend real FortyGuard credits**.

### AI evaluation metrics

`python -m scripts.build16_final_ai_evaluation` evaluates the grounded assistant against the blueprint metrics:

- grounding pass rate;
- unsupported-claim rate;
- evidence citation coverage;
- consistency;
- missing-data behavior;
- tool/intent-selection accuracy;
- deterministic grounded-answer latency.

A machine-readable report is written to:

```text
backend/data/processed/build16_final_ai_evaluation.json
```

and a human-readable report to:

```text
backend/data/processed/build16_final_ai_evaluation.md
```

These generated runtime files are ignored by Git.

## Test commands

From `backend/`:

```powershell
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m scripts.build16_final_ai_evaluation
..\.venv\Scripts\python.exe -m scripts.build16_release_smoke_test
```

No real provider call is required for the test suite.

## Safety and evidence boundaries

HeatShield deliberately refuses to blur measurements, assumptions, and decisions.

- Temperature and environmental values must come from verified provider evidence.
- Occupancy/population is never invented from mapped objects.
- Operational vulnerability and adaptive capacity require an explicit authorized source.
- The planning-priority index is a transparent prototype prioritization score, not a clinically validated medical-risk score.
- Local Qwen can route an intent; it never writes the final factual numeric answer.
- Controlled recommendations come from the versioned action catalog, not free-form LLM invention.
- Scenario Studio labels changed factors as assumptions and does not invent a degree-Celsius reduction.
- A time-shift scenario requires fresh provider evidence for the new time window.

## Demo reliability strategy

The final demo has two paths:

**Primary path:** fresh provider-backed live analysis.

**Fallback path:** verified historical replay with cached evidence, transparent provenance, priority explanation, controlled actions, and grounded assistant.

The fallback is a reliability feature, not a claim that historical evidence is current.

## Rehearsal material

Use the files under `demo/`:

- `DEMO_SCRIPT.md` - timed judge-facing sequence;
- `JUDGE_QA.md` - concise answers to likely technical questions;
- `REHEARSAL_CHECKLIST.md` - preflight and repeatability gate;
- `DEMO_RUN_LOG_TEMPLATE.md` - record repeated rehearsal runs.

## Known limitations

- The live path enriches the selected hottest tile first; equivalent full-priority comparison across all live tiles requires equivalent environmental and authorized context evidence per tile.
- The current planning score is a transparent prototype engineering index, not a medical model.
- Scenario Studio v1 changes operational assumptions while holding the verified thermal hazard constant.
- Premium FortyGuard segmentation/report features are not required for the core MVP.
- Dashboard session recovery is browser-tab scoped; it does not create new source evidence.

## Official 18-30 August execution mapping

The repository keeps historical internal milestone filenames for traceability, but judge-facing naming follows the official calendar:

- **28 Aug:** UI polish, caching/failure-state reliability, repeatable demo.
- **29 Aug:** full tests, AI metrics, README, and demo rehearsal.
- **30 Aug:** submission freeze, backup, pitch and Q&A; no new product features.

## Team

**FortyGuard Auto Team 349**

- Aiman - Team Lead
- Muhammad Adil - AI Engineering / intelligence layer
- Abdullah - Developer / frontend and integration

## Stage line

> Weather apps tell you how hot a city is. HeatShield AI tells you where heat becomes a priority, why, and what to do next.
