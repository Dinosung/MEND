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
