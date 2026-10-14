# Contributing to MEND

Thanks for helping agents stop repeating old mistakes. The most valuable contribution is
a new **fixture**: one real failure that agents keep making, with a reproducer.

## Adding a fixture

1. **Find a real failure.** It should be something agents actually write, backed by a public
   source: a migration guide, changelog, issue or advisory. One failure per fixture.
2. **Create the directory** `fixtures/<package>/<package>-<short-kebab-id>/`, copying
   [`fixtures/pydantic/pydantic-v2-basesettings-moved/`](fixtures/pydantic/pydantic-v2-basesettings-moved/)
   as a template. The full format is in the [fixture spec](docs/FIXTURE_SPEC.md):
   - `fixture.yaml`: metadata, exact pins in `repro.deps`, ≥ 1 source URL.
   - `bad/target.py`: the code an agent would plausibly write.
   - `fixed/target.py`: the same code, corrected. Keep the same public names.
   - `check/test_check.py`: a pytest that does `import target` and tests **behavior**.
   - `rule.yml` (optional): a semgrep rule for `mend check`.
3. **Verify it** in a clean environment (needs [uv](https://docs.astral.sh/uv/)):
   ```bash
   mend verify fixtures/<package>/<your-id>
   # or: python -m mend.cli verify ... from a checkout
   ```
   The check must fail against `bad/` because of the failure you describe, and pass against
   `fixed/`.
4. **Add a bench task** in `bench/tasks/<your-id>.md`. Describe what a developer would ask
   for: the goal, the library, and the names `target.py` must expose. **Do not** mention
   the pitfall, versions, migrations, or the API that fixes it. Check how it reads with
   `python -m bench.tasks --fixtures <your-id>`.
5. **Smoke-test it in the bench:**
   ```bash
   python -m bench.run --agent replay --replay-source bad   --fixtures <your-id> --arms baseline
   python -m bench.run --agent replay --replay-source fixed --fixtures <your-id> --arms baseline
   ```
   Expect `known-failure` and then `pass`.

### PR checklist

- [ ] `id` is kebab-case, prefixed with the package, and equal to the directory name.
- [ ] `repro.deps` uses exact pins (`==`), and `versions` is the PEP 440 range where the
      failure applies.
- [ ] `mend verify` passes: bad fails, fixed passes.
- [ ] `bad/` fails for the stated reason, not a typo or an unrelated ImportError.
- [ ] The check tests behavior. It never greps the source, and it uses no network.
- [ ] Each file is < 60 lines.
- [ ] ≥ 1 public source URL, and `provenance.license` is set.
- [ ] Fixture text is plain description. Nothing in it reads as an instruction to a model.
- [ ] `bench/tasks/<id>.md` exists and does not leak the fix.
- [ ] Search for duplicates first (`mend lookup --task "<keywords>"`).

## Code changes

- Python ≥ 3.10, type hints, stdlib-first. Core deps are only `pyyaml` and `packaging`.
  Everything else goes behind an optional extra (`mcp`, `check`, `dev`).
- Every module in `src/mend/` exposes `main(argv) -> int`. See [AGENTS.md](AGENTS.md) for
  module contracts.
- Tests live in `tests/`, use pytest, and use no network: `python -m pytest -q`.
- Anything returned to an agent goes through `mend.render` (labelled and sanitized data).
- Commits: imperative, small and scoped ("Add sqlalchemy-2 row mapping fixture").

## How MEND-Bench works

The bench lives in [`bench/`](bench/README.md). For each fixture × arm (baseline / mend)
× trial it does the following:

1. Builds a natural-language task from `bench/tasks/<id>.md`, plus an interface footer
   derived from the check.
2. Gives the task to an agent adapter (`bench/agents/`) in a fresh workdir. The mend arm
   also gets MEND (over MCP or as injected context).
3. Scores the resulting `target.py` with the fixture's own check, in a clean `uv`
   environment, as `pass`, `known-failure`, `other-failure` or `infra-error`.
4. Writes `results.jsonl` and a `report.md` with repeat-failure rates and 95% Wilson
   intervals.

Changes to the scorer or the task text affect published numbers. Note them in the PR, and
re-run the replay smoke tests.

## Conduct

Be kind and assume good faith. Credit your sources.
