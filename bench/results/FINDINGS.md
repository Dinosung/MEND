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

## 2026-10-14: fresh pilot (breaking changes released 2026-06 to 2026-10)

Same harness, 11 new fixtures (Anthropic SDK 1.0, polars 2.0, SQLAlchemy 2.1, matplotlib
3.11, scikit-learn 1.9, NumPy 2.5), k=3: 99 trials, $0.52. Repeat failures: A0 3/33, A1 3/33,
A4 0/33. All baseline failures were one fixture: `anthropic-messages-sampling-params-removed`
(`messages.create(temperature=...)` removed in anthropic 1.0, 2026-08-20).

Diagnosis on that fixture, k=5 (15 trials, $0.13, after loosening an over-strict check that
had failed correct MEND-arm solutions which wrapped the review in a prompt):

| Arm | Repeat failures | Pass |
|---|---|---|
| A0 no help | 5/5 | 0/5 |
| A1 versions line | 5/5 | 0/5 |
| A4 MEND hooks | 0/5 | 5/5 |

### What this says

1. **The first measured effect.** On a post-cutoff SDK change, the agent repeated the mistake
   every time without MEND, stating the version did not help, and MEND fixed it every time.
   The PostToolUse hook never had to block: the SessionStart facts were enough.
2. **Why this fixture and not the others:** the agent cannot run code that calls an external
   API, so there is no execution feedback to self-correct from. The 10 other fresh fixtures
   (local libraries the agent can run) produced no baseline failures.
3. **Limits:** one fixture, one model (Haiku 5.5), 5 trials per arm. This is a lead, not a
   result; the kill/continue bar is ≥50 baseline-failing tasks.

### Direction

Target the niche where execution feedback is absent: client SDKs and service APIs (LLM
providers, payments, cloud, SaaS clients) with breaking changes after model cutoffs. Next:
a fixture batch of such changes, then a pilot on Haiku and one stronger model.

## 2026-10-14: SDK batch and Opus 5.5 (checkpoint)

14 new fixtures for 2026 breaking changes in client SDKs (Anthropic SDK 1.0 ×3 more, Together
2.0, Hugging Face Hub 2.0, Mistral 2.0, Stripe 15/16, Azure SDKs), all verified three ways in CI.
Catalog: 58 fixtures.

**Opus screen** (no help, k=1, $1.20; the cap stopped it after 6 of 17 fixtures, all
Anthropic): Opus 5.5 failed only `anthropic-messages-sampling-params-removed`; it handled the
other five Anthropic SDK changes.

**Opus paired** on that fixture (A0 vs A4, k=3, $0.81):

| Arm | Repeat failure | Pass | No target.py (hit turn/budget cap) |
|---|---|---|---|
| A0 no help | 2 | 0 | 1 |
| A4 MEND hooks | 0 | 1 | 2 |

Inconclusive: half the Opus trials ran out of turns (12) or per-trial budget ($0.40) before
writing the file. Of completed trials, same direction as Haiku (A0 2/2 repeat, A4 1/1 pass).
A fair Opus run needs higher limits (~$0.50+/trial).

### Checkpoint summary (all runs, 2026-10-14)

- Agents in a runnable repo self-correct removed APIs: 0 baseline repeats on 43 of 44
  library fixtures (Haiku, 396 trials).
- The exception is code calling an external service, which agents can't run: the Anthropic
  SDK 1.0 `temperature` removal. Haiku: A0 5/5, A1 5/5 repeat; A4 0/5 (5/5 pass). Opus: A0
  2/2 repeat on completed trials; A4 1/1 pass.
- Opus 5.5 already knows most of the 2026 Anthropic SDK changes we tested (5 of 6).
- Evidence for MEND's effect rests on a single fixture. The kill/continue bar (≥50
  baseline-failing tasks) is far away. Spend: $3.89 of $5.
