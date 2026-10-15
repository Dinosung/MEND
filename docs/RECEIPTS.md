# Receipts: does "all tests pass" hold?

Coding agents sometimes say the tests pass when they don't, or edit the tests until they
do. `mend receipt` answers one question: **do the original tests pass with only the
agent's source changes?** It runs outside the agent, adds nothing to the agent's context,
and only reports when it is run.

```
mend receipt [REPO] [--base REF] [--test-cmd CMD] [--claim TEXT | --claim-file FILE] [--json]
```

## What it does

1. Collects the change set against the base commit: committed, uncommitted and untracked
   files. `--base` defaults to the merge-base with the default branch (`origin/HEAD`,
   `main` or `master`), else `HEAD`.
2. Splits it into **protected** files and **source** files. Protected files are tests
   (`test_*.py`, `*_test.py`, anything under a `tests/` or `test/` directory,
   `conftest.py`), test config (`pytest.ini`, `tox.ini`, the `[tool.pytest*]` and
   `[tool.coverage*]` sections of `pyproject.toml`, and the `[tool:pytest]` and
   `[coverage:*]` sections of `setup.cfg`), and CI config (`.github/workflows/`).
   Everything else is source.
3. Checks out the base into a temporary git worktree and applies only the source changes.
   The base's protected files stay as they were; protected files the agent deleted are
   restored.
4. Runs the test command there (default `python -m pytest -q`, or `$MEND_TEST_CMD`) and
   parses the pytest summary.
5. Runs the same command in the agent's own tree when it differs (protected files edited or
   tests added), so the receipt shows what the agent saw.
6. Counts test functions removed and `skip`/`xfail` markers added in edited test files.
   These are plain text counts and never change the verdict.
7. If a claim is given (the agent's final message), looks for "all tests pass", "N passed"
   and similar wording.

**Test files the agent added** (new paths, other than `conftest.py`) are copied in and run
with the original tests. A new test that fails makes the receipt fail; a new test
cannot replace or hide an original one. A new `conftest.py` is never used, because it can
skip or rewrite any test.

## Verdicts

| Verdict | Meaning | Exit |
|---|---|---|
| PROVEN | The original tests pass with only the source changes. | 0 |
| NEEDS REVIEW | Same, but the agent also edited protected files. Listed for a human; does not fail. | 0 |
| NOT PROVEN | The original tests fail, error, or did not run with only the source changes. | 1 |
| CLAIM MISMATCH | As NOT PROVEN, and the agent's message claims passing tests. | 1 |

Usage errors (not a git repo, unknown base) exit 2. A failing verdict always comes from
the re-run itself; diff counts and claim wording never fail a check on their own.

## Failures that were already there

When the re-run fails, the receipt also runs the tests at the base commit. If every failure
already happens there, the receipt says so ("pre-existing"). The Stop hook then stays silent
unless the agent claimed the tests pass: a false "tests pass" claim is always reported, but
unrelated tests that were broken before the agent started are not.

## What it does not check

- Whether the tests are any good, or whether they cover the task.
- Lint or type-checker suppressions (`# noqa`, `# type: ignore`) and coverage thresholds.
- Source-side cheating that the original tests don't catch, such as special-casing test
  inputs, or a test file the agent added that patches source code at import time.
- Non-pytest test commands are supported only by exit code (no counts).
- The test environment: the command runs in your current environment. An editable install
  that points at the agent's tree is fine, since the source is the same.

## Install

**CLI.** `pip install mend-agent` (or run from a checkout with `PYTHONPATH=src python -m mend.cli receipt`).
The receipt itself needs only the standard library and `git`.

**Claude Code Stop hook.** The MEND plugin registers `mend receipt --hook stop` on `Stop`
(`plugin/hooks.json`). It reads the hook JSON on stdin, uses `cwd`, and takes the claim
from `last_assistant_message`, falling back to the last assistant entry in
`transcript_path`. With no changes against the base it exits at once. It exits 2 with the
receipt on stderr, so Claude keeps working, only on CLAIM MISMATCH or on NOT PROVEN with
failing or erroring tests. When `stop_hook_active` is true (Claude is already continuing
after a block), it does not block again; it shows the receipt to the user as a
`systemMessage`. Any internal error exits 0. Set `MEND_TEST_CMD` if your tests need a
different command. Note that the tests run every time Claude stops while the branch has
changes.

**GitHub Action.**

```yaml
- uses: actions/checkout@v4
  with: {fetch-depth: 0}          # the base commit must be present
- run: pip install -e . pytest     # your project's test environment
- uses: Dinosung/MEND@main
  with:
    test-cmd: python -m pytest -q  # default
    claim: ${{ github.event.pull_request.body }}  # optional
```

The action writes the receipt to the job summary and fails the step on NOT PROVEN or
CLAIM MISMATCH. `base` defaults to the pull request's base commit.
