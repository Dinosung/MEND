# MEND-Bench findings

## 2026-10-13: first runs (Week-1 checkpoint)

Setup: `anthropic_api` agent (single-shot, from-scratch task), local scorer, the 20
pydantic / pandas / numpy fixtures scorable offline (`pydantic-v2-basesettings-moved`
was an infra error: dependency not installable in that environment), 3 trials per arm.
SQLAlchemy / FastAPI / Starlette fixtures were not run (need the CI benchmark).

| Run | Model | Baseline repeat-failure | With MEND |
|---|---|---|---|
| versions stated in task | claude-sonnet-5-5 | 0/60 | 0/60 |
| versions stated in task | claude-haiku-5-5 | 0/60 | 0/60 |
| `--hide-versions` | claude-sonnet-5-5 | 3/60 (all `numpy-trapz-removed`) | 0/60 |
| `--hide-versions` | claude-haiku-5-5 | 0/60 (+1 other-failure) | 0/60 |

### What this says

1. **Well-known migrations are solved.** Current models do not repeat Pydantic v1→v2,
   pandas 2/3 or NumPy 2.0 mistakes on clean, single-shot tasks, even without version
   hints. Fixtures for these have little benchmark value against frontier models.
2. **Recent removals are where agents fail, and MEND fixes them.** The only repeated
   failure was `np.trapz`, removed in NumPy 2.4. Sonnet used it 3/3 times without MEND and
   0/3 with MEND.
3. **The sample is tiny.** 3 failing trials out of 240 is a signal, not a result.

### Direction

- **Freshness first:** prioritise fixtures for breaking changes released after model
  training cutoffs (last ~6–12 months): Starlette 1.0, FastAPI 0.132+ strict content type,
  NumPy 2.4 removals, and new major releases as they ship. This is MEND's real value: it
  updates faster than model weights.
- **Realistic tasks:** add an edit-in-existing-repo task mode (legacy code around the
  change, lockfile not mentioned), which is how agents actually meet these APIs.
- Run the CI benchmark on `sqlalchemy/*,fastapi/*,starlette/*` next.

## 2026-10-14: MEND-Bench v2 pilot (agentic, implicit versions)

Setup: Claude Code headless (`claude-haiku-5-5`, max 12 turns) working inside a small repo
per fixture; versions only in `pyproject.toml`; hidden check scored on source only. All 33
verified fixtures, arms A0 (no help) / A1 (versions line in CLAUDE.md) / A4 (MEND hooks),
k=3: 297 trials, $0.94 (CI run 38582038736; summary in
`2026-10-14-v2-pilot-haiku/annotation.txt`).

| Arm | Repeat failures | Other failures | Infra |
|---|---|---|---|
| A0 | 0/99 | 0 | 0 |
| A1 | 0/99 | 0 | 0 |
| A4 | 0/99 | 0 | 0 |

A4 hooks: SessionStart injected in 100% of trials, PostToolUse ran in 100%, blocked 0 times
(the agent never wrote a known-bad pattern).

### What this says

1. **In an agentic loop, the current catalog produces no baseline failures.** The agent can
   run its code against the pinned versions, so removed APIs surface as errors it fixes
   itself; on these tasks it also avoided the silent pandas 3.0 behaviour changes.
2. **This is the opposite of the single-shot result** (Sonnet repeated `np.trapz` 3/3 when it
   could not run code). Execution feedback, not knowledge, is doing the work.
3. **By the pilot's own criterion** (continue only if A0 shows failures), the existing
   fixtures give no effect to build on. The remaining pilot test is fresh post-cutoff
   changes found by the release-diff stage (`docs/PIPELINE.md`), which models are least
   likely to know.
