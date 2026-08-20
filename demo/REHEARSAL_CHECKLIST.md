# HeatShield AI - Rehearsal Checklist

Do not add new product features while rehearsing. Fix only blocking defects.

## Before the first rehearsal

- [ ] Pull/checkout the verified main branch.
- [ ] Confirm `backend/.env` exists locally and is not staged.
- [ ] Start Ollama with the expected local Qwen model if the live assistant routing demo will use it.
- [ ] Run `RUN_29AUG_FINAL_READINESS.ps1` and require PASS.
- [ ] Start `RUN_FINAL_DASHBOARD.ps1`.
- [ ] Hard-refresh once before the rehearsal, then avoid unnecessary refreshes during the live flow.
- [ ] Confirm Live Analysis, Historical replay, Assistant and Scenario Studio open.
- [ ] Confirm no API key appears in the browser, terminal recording, screenshots or Git status.
- [ ] Decide the exact small AOI, time and `100 m` granularity for the live demo.
- [ ] Decide the authorized demo context reference text before presenting.

## During each rehearsal

- [ ] Problem statement under 20 seconds.
- [ ] Fresh provider request attempted once only.
- [ ] If provider is slow/unavailable, switch cleanly to Historical replay.
- [ ] Never call historical evidence "current".
- [ ] Show one provenance/evidence chain.
- [ ] Explain one priority decomposition.
- [ ] Ask the grounded assistant one "why" question and one provenance question.
- [ ] Show the medical-risk / occupancy boundary.
- [ ] Run one Scenario Studio comparison.
- [ ] State that scenario output is an estimate and no temperature reduction is predicted.
- [ ] Finish within 5 minutes.
- [ ] Record any defect in `DEMO_RUN_LOG_TEMPLATE.md` or a copied run log.

## Repeatability gate

Before submission, complete **three successful rehearsals** with no blocking defect and with the same primary/fallback script understood by all team members.

- [ ] Rehearsal 1 PASS
- [ ] Rehearsal 2 PASS
- [ ] Rehearsal 3 PASS

## Final freeze

- [ ] No new features after the readiness gate.
- [ ] Working tree clean.
- [ ] Main branch pushed.
- [ ] Backup ZIP created without `.env`, `.venv`, `node_modules`, cache or secrets.
- [ ] README verified from a clean-checkout perspective.
- [ ] Pitch deck/demo links checked.
- [ ] All team members can explain FortyGuard vs HeatShield responsibility in one minute.
