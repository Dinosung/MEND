# MEND-Bench v2 pilot harness

Agentic, in-repo, implicit-version tasks with hidden tests and source-only scoring.
Design, budget and open issues: [docs/BENCH_V2.md](../../docs/BENCH_V2.md).

## Run

```bash
# The configured pilot (Claude Code, needs ANTHROPIC_API_KEY, `claude` and `uv` on PATH)
python -m bench.v2.run --config bench/v2/run-config.yaml
python -m bench.v2.run --config bench/v2/run-config.yaml --dry-run      # plan + guards only

# Override anything from the config
python -m bench.v2.run --config bench/v2/run-config.yaml --fixtures 'numpy-*' --trials 1

# Offline harness self-test (no network, no claude): replay agent + local scorer
python -m bench.v2.run --agent replay --replay-source bad    --scorer local --fixtures 'numpy-*,pandas-cow-*'
python -m bench.v2.run --agent replay --replay-source fixed  --scorer local --fixtures 'numpy-*,pandas-cow-*'
python -m bench.v2.run --agent replay --replay-source tamper-bad --scorer local --fixtures 'numpy-*'

python -m bench.v2.report <out-dir>                    # re-render report.md / summary.json
```

`--scorer local` runs the hidden check with `--local-python` (default: the current
interpreter) and does not enforce pins. Use it only to test the harness.

## Files

| file | role |
|---|---|
| `taskgen.py` | fixture → project files (pyproject with exact pins, CLAUDE.md, helpers.py, main.py, tests/), prompt, leak check |
| `arms.py` | A0 (nothing), A1 (CLAUDE.md fact line), A4 (`.claude/settings.json` hooks → `hook_wrapper.py` → `mend hook ...`) |
| `hook_wrapper.py` | runs `python -m mend.cli hook <event>` and logs each call for hook-fire counts |
| `agents.py` | `ClaudeCode` (headless `claude -p`, stream-json), `Replay` (bad/fixed/tamper-*) |
| `score.py` | source-only sanitize + hidden check (uv or local) + v1 outcome classes |
| `stats.py`, `report.py` | Wilson, paired bootstrap, exact McNemar, hook rates → `summary.json`, `report.md` |
| `run.py` | runner, trial/budget guards |
| `run-config.yaml` | the default pilot (also used by `.github/workflows/bench-v2.yml` on `bench-run/**` pushes) |

Outputs in `--out` (default `bench/results/<timestamp>-v2-<agent>/`): `run.json`,
`results.jsonl` (one record per trial, with `cost_usd`), `summary.json` (with `spend_usd`),
`report.md`, and `raw/<fixture>/<arm>/t<k>/` (prompt, transcript, hook log, target.py,
scorer output; git-ignored).
