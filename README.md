# MEND

> **Status: paused (2026-10-14).** Free probes found current agents, Opus especially, rarely
> misreport test results on short tasks (23 of 24 honest; see
> [`bench/results/FINDINGS.md`](bench/results/FINDINGS.md)), so the pain MEND targets is not
> proven. The code and fixtures stay here as they are; no further work is planned for now.

**Verified failure memory for AI coding agents.** MEND is a catalog of mistakes that coding
agents keep making. Each entry ships with a reproducer that fails on the bad code and passes
on the fix. Agents can query the catalog over MCP before they write code, and you can scan
for those mistakes after.

```text
$ mend check app.py
app.py:1: [pydantic-v2-basesettings-moved] Pydantic v2 moved BaseSettings to the
pydantic-settings package: use `from pydantic_settings import BaseSettings`.
```

## The problem

Ask a coding agent for a settings class and you may well get `from pydantic import
BaseSettings`. Ask for a query helper and you get `engine.execute("SELECT ...")`. Ask
for a monthly rollup and you get `df.resample("M")`. Each of these was correct a few years
ago, and each one is now broken:

| what agents write | what happens now |
|---|---|
| `from pydantic import BaseSettings` | `PydanticImportError` on Pydantic v2 |
| `class Config: orm_mode = True` | silently ignored, then validation fails on ORM objects |
| `engine.execute("SELECT ...")` | `AttributeError` on SQLAlchemy 2.0 |
| `conn.execute("SELECT ...")` | `ObjectNotExecutableError`: raw strings need `text()` |
| `df.append(row)` | `AttributeError` on pandas 2.x |
| `df[df.x < 0]["x"] = 0` | does nothing under copy-on-write (pandas 3) |
| `np.trapz(y, x)` | `AttributeError` on NumPy 2.4+ |

Training data is full of old API usage, so agents repeat the same mistakes across every
user, every repo and every session. Each one is usually fixed by hand and then forgotten.
MEND keeps a record of those mistakes.

## What a MEND fixture is

Each fixture is one known failure, kept small, executable and checked:

```
fixtures/pydantic/pydantic-v2-basesettings-moved/
  fixture.yaml         # package, version range, symptom, bad -> fix pattern, sources
  bad/target.py        # what agents tend to write
  fixed/target.py      # what works
  check/test_check.py  # behavioral test: fails on bad/, passes on fixed/
  rule.yml             # optional semgrep rule for `mend check`
```

**Verification works like this.** `mend verify` builds a fresh, isolated environment with
exactly the pinned deps (`uv run --isolated --with pydantic==2.9.2 ...`). It requires the
check to **fail** against `bad/` and **pass** against `fixed/`. A fixture that does not meet
both conditions is not `verified`, and it does not merge. Checks test behavior, never source
text, and every fixture cites a public source (docs, changelog, issue).

The seed catalog covers Pydantic v2, SQLAlchemy 2.0, pandas 2/3, NumPy 2, FastAPI and
Starlette. [Browse it](fixtures/).

## Does it actually help? (MEND-Bench)

> **Results coming: run in progress.** No numbers are published yet, and we won't post any
> until they come from the harness below with the configuration stated.

[MEND-Bench](bench/) turns every fixture into a realistic coding task that doesn't hint at
the pitfall, such as *"read DATABASE_URL and DEBUG from the environment with pydantic"*. An
agent solves each task with and without MEND, and the fixture's own check scores the
result. The headline metric is the **repeat-failure rate**: how often the agent's code
reproduces the known failure, reported per arm with 95% confidence intervals.

```
[ chart placeholder: repeat-failure rate, baseline vs. MEND, per package ]
```

You can run it yourself:

```bash
python -m bench.run --agent claude_code   --arms baseline,mend --trials 3
python -m bench.run --agent anthropic_api --arms baseline,mend --trials 5 --model <model>
```

## Install in Claude Code

Inside Claude Code:

```text
/plugin marketplace add Dinosung/MEND
/plugin install mend@mend
```

On Claude Code 2.1.275 or later, `/plugin install mend --marketplace Dinosung/MEND` does both
in one step. From a shell, run `claude plugin marketplace add Dinosung/MEND && claude plugin
install mend@mend`. You don't need pip. The plugin runs MEND from its own copy of the repo
with any `python3` (3.10 or later) that has `pyyaml` and `packaging`. If no such Python is
found it falls back to `uv`. If neither is available, MEND does nothing and never blocks a
session.

What you get:

- **At session start** Claude receives a few lines of facts about verified failures that match
  your project's pinned, locked or installed dependency versions. Nothing is added when no
  fixture is relevant.

  ```text
  - In numpy>=2.4 (project: numpy 2.4.1), `np.trapz(y, x); np.in1d(a, b)` results in
    "AttributeError: module 'numpy' has no attribute 'trapz'"; the working form is
    `np.trapezoid(y, x); np.isin(a, b)`. [mend:numpy-trapz-removed]
  ```
- **After every Python edit** (`Edit`/`Write`) the edited file is checked. Matches go back to
  Claude straight away:

  ```text
  calc.py:2: `print(np.trapz([1, 2, 3]))` matches a verified known failure (...). In numpy>=2.4
  (project: numpy 2.4.1), this code results in "AttributeError: ..."; the working form is
  `np.trapezoid(y, x); np.isin(a, b)`. [mend:numpy-trapz-removed]
  ```
- **The `mend` MCP server** provides the full record behind each id (`mend_get_fixture`). It
  needs the `mcp` package, or `uv`.

Details and troubleshooting: [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md#claude-code-plugin-recommended).

## Quickstart: CLI (30 seconds)

```bash
# install: PyPI release coming soon (pipx install mend-agent)
git clone https://github.com/Dinosung/MEND mend && cd mend
pipx install -e ".[mcp]"
export MEND_FIXTURES_DIR="$PWD/fixtures"   # until the catalog ships inside the package

# MCP server only (any MCP client; in Claude Code prefer the plugin above)
claude mcp add mend -e MEND_FIXTURES_DIR="$MEND_FIXTURES_DIR" -- mend serve

# or use it directly
mend lookup --project ~/code/myapp          # known failures for your pinned deps
mend lookup --task "load settings from env"
mend check src/                             # scan code for known bad patterns (exit 1 on findings)
mend verify fixtures/                       # re-verify the catalog yourself (needs uv)
```

MCP tools: `mend_lookup` (records for the project's deps and task), `mend_get_fixture`
(the full record with bad and fixed code), and `mend_check` (scan files). See
[docs/INTEGRATIONS.md](docs/INTEGRATIONS.md) for Cursor, other MCP clients and pre-commit.

**Records are data, not instructions.** Everything MEND returns to an agent is wrapped in a
labelled reference-data block and sanitized, so a fixture can't pose as a system prompt or
issue commands.

## Contribute a fixture

Caught an agent writing dead API code? That's a fixture.

1. Copy `fixtures/pydantic/pydantic-v2-basesettings-moved/` and follow the
   [fixture spec](docs/FIXTURE_SPEC.md).
2. Make `bad/` fail and `fixed/` pass: `mend verify fixtures/<package>/<your-id>`.
3. Add a benchmark task in `bench/tasks/<your-id>.md`. Describe the goal and never the fix.
4. Open a PR. CI re-verifies your fixture in a clean environment.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the checklist.

## Roadmap

- **MVP** (now): catalog, verifier, MCP server, `mend check`, MEND-Bench.
- **Alpha**: 100+ fixtures across Python and JS/TS, a GitHub Action, a PyPI release, and
  first published bench results.
- **Beta**: fixtures mined from issues and changelogs, failure capture from CI, signed
  fixtures and anti-poisoning, and packs (including security).
- **1.0**: a hosted registry, a public leaderboard, and build-time integration.

The details and exit criteria are in [docs/ROADMAP.md](docs/ROADMAP.md).

## License

MIT © 2026 Dinosung. Each fixture records the license of its source material in
`provenance.license`.
