# MEND progress log

## API spend ledger

Cap: **$5.00 total** for benchmark/probe runs from 2026-10-14 until the owner raises it.
Every paid run gets a row. Check the running total before starting any run.

| Date | Run | Model(s) | Trials | Cost (USD) | Running total |
|---|---|---|---|---|---|
| 2026-10-13 | MEND-Bench v1, single-shot, 4 runs (pre-cap, unmetered; owner's personal key) | claude-sonnet-5-5, claude-haiku-5-5 | 504 | not metered, not counted against the cap | $0.00 |
| 2026-10-14 | Plugin end-to-end check: 2 headless `claude --plugin-dir` sessions | default | 2 | ~0.15 | $0.15 |

## Log

### 2026-10-14
- Strategy research completed; direction adopted (`STRATEGY.md`): verified post-cutoff tripwire for Python, hooks-first delivery, agentic benchmark.
- Owner: employer clearance obtained; API budget capped at $5 for now.
- Pilot work started: differential verification gate, ruff overlap table, Claude Code plugin, release-diff prototype, MEND-Bench v2 pilot harness.
- Shipped: Claude Code plugin (SessionStart facts + PostToolUse check, verified end to end; simplified hooks.py 452 → 125 lines).
- Shipped: linter overlap (`docs/OVERLAP.md`): 21 of 33 fixtures MEND-only, 10 covered (ruff NPY201 covers `np.trapz`), 2 partial.
- Shipped: differential gate. 28 of 33 fixtures carry `repro.old_deps`; CI verified all 33, including all 28 three-way checks (bad passes on old, fails on new; fixed passes on new). Five Pydantic fixtures can't use the gate because their code calls v2-only APIs.
- Catalog: 33 total / 28 differential / 0 probed. Tests: 190.
