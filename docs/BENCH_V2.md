# MEND-Bench v2 pilot

This is item 6 of the two-week pilot in [STRATEGY.md](STRATEGY.md). It asks whether
MEND's hooks (A4) reduce repeat failures compared with no help (A0) and with a one-line
statement of the pinned versions (A1). The agent is Claude Code working in a real-ish repo,
and it is never told the versions in the prompt. The code is in [bench/v2/](../bench/v2/README.md).

## Task design

Each verified fixture becomes one task.

- **Repo.** `pyproject.toml` pins the fixture's deps exactly (`numpy==2.5.3`), so `uv run`
  in the workdir gets exactly those versions. The repo also holds `README.md`, a neutral
  `CLAUDE.md`, `helpers.py`, `main.py` and `tests/test_helpers.py`. None of these files
  touch the fixture's API.
- **Prompt.** The hand-written `bench/tasks/<id>.md` description (it already avoids hinting
  at the fix), the interface `target.py` must expose, and "use the project's existing
  dependencies". `find_leaks()` rejects a prompt that contains a pinned version, a
  version-like mention (`numpy 2`, `pydantic v2`), `==`, hint words such as
  "deprecated" or "upgrade", or the fixture's bad/fix pattern. The runner refuses to start
  if any prompt leaks. All 33 current prompts are clean.
- **Hidden test.** The fixture's `check/` is never in the workdir. Before the agent starts,
  the runner hashes the workdir against the check files and aborts on a match. The check
  is copied in only at scoring time.
- **Source-only scoring.** Before scoring, the harness discards `tests/`, `test_*.py`,
  `conftest.py`, `pytest.ini`/`tox.ini`/`setup.cfg`, `sitecustomize.py`/`usercustomize.py`,
  `*.pth`, and top-level modules that shadow pytest or a pinned dependency. Any of these
  that the agent added, changed or deleted is recorded as `tampered_tests`. The hidden
  check then runs on the remaining source with
  `uv run --isolated --no-project --python <repro.python> --with <deps> --with pytest pytest`.
  Outcomes follow the v1 classes: `pass`, `known-failure` (repeat of the fixture's failure),
  `other-failure` and `infra-error`.

## Arms

| Arm | What changes in the workdir |
|---|---|
| A0 | Nothing. Every arm has the same neutral `CLAUDE.md`. |
| A1 | `CLAUDE.md` gains one fact line: `This project uses numpy 2.5.3.` |
| A4 | `.claude/settings.json` with `SessionStart` (matcher `startup`) and `PostToolUse` (matcher `Write\|Edit\|MultiEdit`) command hooks. Each runs `bench/v2/hook_wrapper.py`, which runs `python -m mend.cli hook session-start\|post-tool-use` with `PYTHONPATH=<repo>/src`, `MEND_FIXTURES_DIR=<copy of the catalog without check/ dirs>`, and logs each call. |

Note that A4's SessionStart facts include the project's version (`numpy>=2.4 (project: 2.5.3)`).
A4 is therefore "A1 plus MEND content", and A4−A1 measures the content beyond the
version fact.

Claude Code is run as
`claude -p <prompt> --model M --output-format stream-json --verbose --include-hook-events --max-turns N --max-budget-usd X --permission-mode bypassPermissions --no-session-persistence --strict-mcp-config --setting-sources project`.
These flags were checked against Claude Code 2.1.299 `--help` and the CLI reference.
`--setting-sources project` keeps the runner's user settings out of the run and still
loads the project `CLAUDE.md` and `.claude/settings.json`. `--bare` is not used, because
it skips both. A local `claude --init-only --setting-sources project` in an A4 workdir
fired the SessionStart hook through the wrapper, and `mend hook` returned the facts.

Hook activity is counted from the wrapper log:

- SessionStart injected context
- PostToolUse ran
- PostToolUse exited 2 (a block that Claude sees)
- hook errors

`hook_*` events in the stream-json output are kept as a cross-check. A `peeked` flag marks
trials whose tool calls referenced `test_check.py` or a `/fixtures/` path.

## Statistics

A trial fails when its outcome is `known-failure`. `infra-error` trials are excluded.

- **Per-arm failure rate.** Reported over trials with a Wilson 95% interval. This is
  descriptive only, because trials of the same task are not independent.
- **Paired difference (B−A).** The mean over tasks of the per-task failure-rate difference,
  with a 95% percentile bootstrap that resamples tasks (10k resamples, fixed seed).
  Reported for A0→A1, A0→A4 and A1→A4.
- **McNemar test.** An exact two-sided test on the per-task majority outcome. A task counts
  as failed when its rate is ≥ 0.5, so with k=2 a 1/1 split counts as a failure.
- **A4 hook rates.** The share of A4 trials in which each hook fired, with the total number
  of blocks.

The pilot cannot reach significance. STRATEGY.md estimates that a strong effect needs
about 51 baseline-failing tasks. The pilot exists to measure the A0 failure rate and get
a first paired A4-vs-A1 signal.

## Budget ($5 total cap)

The owner's cap is **$5 for all benchmark runs combined**. Three mechanisms enforce it.

- **Per trial.** `--max-budget-usd per_trial_usd` (default $0.10) and `--max-turns`
  (default 12) are passed to every `claude` run.
- **Per run.** The runner stops launching trials once
  `spent + per_trial_usd > min(run_usd, max_usd − prior_spend_usd)`. Spend comes from
  `total_cost_usd` in Claude Code's result event. A trial that reports no cost (a crash or
  timeout) is charged the full `per_trial_usd`. Trials run in trial-major order
  (all fixtures × arms for t0, then t1), so a run that stops early keeps complete pairs.
- **Before the run starts.** The runner refuses to start when fixtures × arms × trials
  exceeds `max_trials` (default 300), or when the cap cannot fit a single trial.

Spend is recorded per trial (`cost_usd`, `spent_so_far_usd` in `results.jsonl`) and per
run (`spend_usd` in `summary.json` and `run.json`). Before each new run, sum the earlier
runs' `spend_usd` and pass it as `prior_spend_usd`, either in `run-config.yaml` or as the
workflow input. Claude Code's cost is a client-side estimate, so it can differ from the
bill.

### Default pilot and cost estimate

`run-config.yaml` uses `claude-haiku-5-5` on 7 fixtures, the 2025–26 changes most likely
to fail:

- `numpy-trapz-removed`
- both Starlette 1.0 fixtures
- `fastapi-strict-content-type-json-body`
- `fastapi-app-add-event-handler-removed`
- `pandas-cow-chained-assignment-noop`
- `pandas-str-dtype-not-object`

With arms A0/A1/A4, k=2 and max_turns 12, that is **42 trials**, with `run_usd: 1.50`.

The estimate below uses Haiku 5.5 list prices: $0.10/M input, $0.50/M output, $0.125/M
5-minute cache write and $0.01/M cache read, for prompts up to 100k tokens. It assumes a
small task takes about 8 turns, with a context of about 25–35k tokens that is mostly
cached.

| Component | Tokens | Cost |
|---|---|---|
| Cache reads | ~250k | ~$0.003 |
| Cache writes | ~40k | ~$0.005 |
| Output | ~5k | ~$0.003 |
| **Per trial** | | **≈ $0.01–0.03** (allowing for retries and side calls) |
| **Pilot (42 trials)** | | **≈ $0.40–1.30** |

The same pilot on `claude-sonnet-5-5` ($2/$10 per M, $0.10/M cache read) would cost about
$0.15–0.25 per trial, or $6–10. That does not fit the cap: the run cap would stop it after
roughly 6–10 trials. Use Sonnet only on a few fixtures, with k=1.

## Running in GitHub Actions

The workflow is `.github/workflows/bench-v2.yml`. It needs the repository secret
`ANTHROPIC_API_KEY`. It installs:

- Python 3.12
- uv
- Node 22
- `npm install -g @anthropic-ai/claude-code`
- `pip install -e .`

The job timeout is 120 minutes and the run step's is 100 minutes. Runs are serialized
through the `bench-v2` concurrency group, so two runs never spend at the same time. The
report goes to the job summary, and the results directory is uploaded as artifact
`bench-v2-<run_id>`.

There are two ways to start a run:

1. **Push a branch.** Edit `bench/v2/run-config.yaml` (fixtures, trials, `prior_spend_usd`, ...),
   then `git push origin HEAD:bench-run/<name>`. Every push to a `bench-run/**` branch
   starts a run, so only push when you mean to spend.
2. **Manual dispatch.** Use Actions → *MEND-Bench v2 pilot* → *Run workflow*, or
   `gh workflow run bench-v2.yml -f trials=1 -f fixtures=numpy-trapz-removed -f prior_spend_usd=0.84`.
   Blank inputs fall back to `run-config.yaml`. `max_usd` defaults to 5.

## Harbor

Not in the pilot. The full run (Phase 2) should export these tasks in Harbor's format so they run unchanged on Claude Code, Codex and mini-swe-agent, with Docker isolation of the hidden tests.

## Open issues

- **No live run yet.** There is no API key in the dev environment. The harness was
  checked with the replay agent and local scorer, with unit tests, and with
  `claude --init-only` for the hooks. The first CI run should be a cheap smoke run
  (`trials=1`, one fixture) to check stream-json parsing, cost capture and PostToolUse
  blocks.
- **The uv scorer was not run here** because PyPI is blocked. It uses the same command as
  v1's `--scorer uv`.
- **Isolation is incomplete.** On the Actions runner the agent can read the whole checkout,
  including `fixtures/*/check`. Three things mitigate this: the workdir is in a temp dir,
  A4 uses a catalog copy without checks, and the `peeked` flag is reported. Full isolation
  needs Docker/Harbor.
- **Agents may run their code.** The pins are in `pyproject.toml` and `uv` is on PATH, so
  the agent can `uv run` its code against the real versions and fix errors itself. That is
  realistic, but it raises the A0 pass rate on `api-removed` fixtures. Silent
  `behavior-changed` fixtures (pandas CoW) are unaffected.
- **Known-failure classification** reuses v1's coarse signature match, so read it as an
  upper bound. A trial whose agent ran but left no `target.py` (for example after running out of
  turns or budget; see `result_subtype`) is scored `other-failure`, not `infra-error`.
- **Spend accounting across runs is manual** (`prior_spend_usd`), because CI cannot write
  back a ledger.
- **Actions are pinned by tag, not SHA.** STRATEGY.md asks for SHA pinning. Pin them
  before making the repo public.
