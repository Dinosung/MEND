# MEND-Bench

Does giving a coding agent verified failure records reduce how often it repeats known
mistakes? MEND-Bench measures that.

**Headline metric: repeat-failure rate.** This is the share of scored trials in which the
agent's `target.py` reproduces the fixture's known failure. Each solution is scored by the
fixture's own `check/test_check.py`, in a clean environment that has exactly the pinned
deps. It is reported for a **baseline** arm (no MEND) and a **mend** arm, with 95% Wilson
intervals.

## How a trial works

1. **Task.** Every fixture gets a natural-language request (`bench/tasks.py`). It describes
   the goal and names the library, but never the pitfall or the fix. The harness then adds
   a contract footer, built from `check/test_check.py` and the signatures in
   `fixed/target.py`. The footer lists which names `target.py` must expose and the pinned
   deps. Task text comes from the first of these that exists:
   - `bench/tasks/<fixture-id>.md`: a hand-written override, reviewed for leaks.
   - `--llm-tasks`: the Anthropic API writes the task. The writer sees the package, deps,
     interface and check, and never sees bad/fixed code or the failure fields. Output that
     quotes `bad_pattern` or `fix_pattern` is rejected. Cache the result with
     `python -m bench.tasks --llm --write`, then review it.
   - A generic template. It is weak, and `run.py` warns when it is used.
2. **Workdir.** A fresh temp dir holding only `requirements.txt` with the pinned deps.
3. **Solve.** `Agent.solve(task, workdir, mend_context)` must leave `target.py` behind.
   `mend_context` is `None` for baseline. For the mend arm it is what `mend lookup` returns
   for this project's deps and the task.
4. **Score** (`bench/score.py`). The check directory is copied out of the fixture, and pytest
   runs with `PYTHONPATH=<workdir>`.

## Outcome classes

| outcome | rule |
|---|---|
| `pass` | check exits 0 |
| `known-failure` | check fails **and** either (a) a failure signature `(test id, exception class)` also appears when the same check runs against the fixture's own `bad/target.py` under the same scorer, or (b) the message part of `failure.symptom` appears in the output |
| `other-failure` | check fails any other way (typo, wrong logic, unrelated exception) |
| `infra-error` | no `target.py`, agent crashed or timed out, uv could not build the env, or (local scorer) a pinned dep is missing. Excluded from rates. |

Rule (a) is coarse on purpose, and it matters most for `behavior-changed` fixtures. For
those the bad code usually fails with an `AssertionError` in a particular test, so a
different bug that trips the same assertion is counted as a repeat. Read known-failure as
an upper bound. Spot-check `raw/<fixture>/<arm>/t<n>/target.py` before you publish.

## Agents (`bench/agents/`)

| agent | baseline | mend arm |
|---|---|---|
| `replay` | copies `bad/` or `fixed/` `target.py` (or `--replay-source <file or dir>`) | same. This is for testing the harness. |
| `anthropic_api` | one Messages API call, no tools | MEND block appended to the system prompt as labelled data |
| `claude_code` | headless `claude -p` with `--strict-mcp-config` and no servers | `--mend-mode mcp` (default): `--mcp-config` → `mend serve` (cwd = workdir); `--mend-mode context`: block appended via `--append-system-prompt` |

`claude_code` saves the stream-json transcript and records whether any `mend_*` tool was
called. The report shows the tool-call rate, because an MCP arm whose agent never calls the
tool tells you nothing about the content.

`--mend-exclude-self` (context modes only) leaves the fixture under test out of the
context. Use it to measure spill-over rather than recall.

## Running

```bash
# Real run: clean env per check via uv (needs network for the first resolve)
export ANTHROPIC_API_KEY=...
python -m bench.run --agent anthropic_api --model claude-sonnet-4-5 \
    --arms baseline,mend --trials 5 --out bench/results/2026-10-sonnet/

python -m bench.run --agent claude_code --arms baseline,mend --trials 3 --fixtures 'pydantic-*'

# Harness self-test, offline: the current interpreter, no uv
python -m bench.run --agent replay --replay-source bad   --scorer local   # expect 100% known-failure
python -m bench.run --agent replay --replay-source fixed --scorer local   # expect 100% pass

python -m bench.report bench/results/<run-id>/    # re-render report.md
python -m bench.tasks                              # print every task as an agent sees it
```

Outputs in `--out`: `run.json` (config), `results.jsonl` (one record per trial),
`report.md`, and `raw/` (per-trial `target.py`, transcripts and check output; git-ignored).

`--scorer local` uses whatever packages the running interpreter has. Pins are **not**
enforced (version mismatches are listed in the report), and fixtures whose deps are missing
come out as `infra-error`. It is for testing the harness only. Never publish numbers from it.

## Before trusting a result

- Run both replay smoke tests under `--scorer uv`. Bad must score 100% known-failure and
  fixed must score 100% pass.
- Read a sample of tasks (`python -m bench.tasks`) and confirm none of them leaks the fix.
- Report the model, the date, `--trials`, the arm config, the MCP tool-call rate and the
  infra-error count next to any number.
