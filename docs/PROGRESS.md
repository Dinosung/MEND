# MEND progress log

## API spend ledger

Cap: **$5.00 total** for benchmark/probe runs from 2026-10-14 until the owner raises it.
Every paid run gets a row. Check the running total before starting any run.

| Date | Run | Model(s) | Trials | Cost (USD) | Running total |
|---|---|---|---|---|---|
| 2026-10-13 | MEND-Bench v1, single-shot, 4 runs (pre-cap, unmetered; owner's personal key) | claude-sonnet-5-5, claude-haiku-5-5 | 504 | not metered, not counted against the cap | $0.00 |
| 2026-10-14 | Plugin end-to-end check: 2 headless `claude --plugin-dir` sessions | default | 2 | ~0.15 | $0.15 |
| 2026-10-14 | Bench v2 smoke runs ×2 (numpy-trapz-removed, A0/A1/A4, k=1); first run's results not readable, assumed ≤$0.02 | claude-haiku-5-5 | 6 | ~0.02 | $0.17 |
| 2026-10-14 | Bench v2 pilot: 33 fixtures, A0/A1/A4, k=3 | claude-haiku-5-5 | 297 | 0.94 | $1.11 |
| 2026-10-14 | Bench v2 fresh pilot: 11 post-mid-2026 fixtures, A0/A1/A4, k=3 | claude-haiku-5-5 | 99 | 0.52 | $1.63 |
| 2026-10-14 | Diagnosis: anthropic sampling-params, A0/A1/A4, k=5, ×2 (strict, then loosened check) | claude-haiku-5-5 | 30 | 0.25 | $1.88 |
| 2026-10-14 | Opus screen: 17 SDK fixtures, A0, k=1 (stopped by cap after 6) | claude-opus-5-5 | 6 | 1.20 | $3.08 |
| 2026-10-14 | Opus paired: sampling-params, A0 vs A4, k=3 | claude-opus-5-5 | 6 | 0.81 | $3.89 |

## Log

### 2026-10-14
- Strategy research completed; direction adopted (`STRATEGY.md`): verified post-cutoff tripwire for Python, hooks-first delivery, agentic benchmark.
- Owner: employer clearance obtained; API budget capped at $5 for now.
- Pilot work started: differential verification gate, ruff overlap table, Claude Code plugin, release-diff prototype, MEND-Bench v2 pilot harness.
- Shipped: Claude Code plugin (SessionStart facts + PostToolUse check, verified end to end; simplified hooks.py 452 → 125 lines).
- Shipped: linter overlap (`docs/OVERLAP.md`): 21 of 33 fixtures MEND-only, 10 covered (ruff NPY201 covers `np.trapz`), 2 partial.
- Shipped: differential gate. 28 of 33 fixtures carry `repro.old_deps`; CI verified all 33, including all 28 three-way checks (bad passes on old, fails on new; fixed passes on new). Five Pydantic fixtures can't use the gate because their code calls v2-only APIs.
- Catalog: 33 total / 28 differential / 0 probed. Tests: 190.
- Bench v2 pilot (297 trials, $0.94): 0/99 repeat failures in every arm. Agents fix removed APIs by running their code. Next: fresh post-cutoff fixtures from the release-diff candidates, then the pilot verdict.
- Shipped: release-diff stage (`docs/PIPELINE.md`): 26 releases of 15 libraries, ~80% of top candidates are real breaking changes.
- Fresh pilot: 11 post-mid-2026 fixtures (catalog now 44). Only the Anthropic SDK 1.0 sampling-params fixture fails at baseline; on it, A0 5/5 and A1 5/5 repeat the failure, A4 (MEND) 0/5 and passes 5/5. First measured effect; one fixture, one model.
- Direction: SDK/service-API breaking changes, where agents can't run code to self-correct.
- Checkpoint reached: SDK batch (catalog 58), Opus screen and paired run. Evidence for MEND's effect rests on one fixture (see FINDINGS.md). Implementation paused for market research, per owner.
