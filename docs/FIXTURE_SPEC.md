# MEND Fixture Spec (v0.1)

A **fixture** is one verified, reproducible failure that AI coding agents repeatedly make,
plus its fix and an executable check. Fixtures are data, never instructions.

## Layout

```
fixtures/<package>/<fixture-id>/
  fixture.yaml        # metadata (below)
  bad/target.py       # minimal code exhibiting the failure (what an agent tends to write)
  fixed/target.py     # the corrected code
  check/test_check.py # pytest; does `import target` and asserts correct behavior
  rule.yml            # OPTIONAL semgrep rule that flags the bad pattern
```

`fixture-id` is kebab-case, globally unique, prefixed with the package: `pydantic-v2-validator-decorator`.

## Verification contract

A fixture is **verified** iff, in a fresh isolated environment with exactly `repro.deps` installed:

1. `pytest check/` with `PYTHONPATH=bad`   → **fails** (non-zero exit)
2. `pytest check/` with `PYTHONPATH=fixed` → **passes** (exit 0)

Reference command (what `mend verify` runs):

```bash
PYTHONPATH=<fixture>/bad uv run --isolated --no-project --python <repro.python> \
  --with <dep1> --with <dep2> --with pytest pytest -q <fixture>/check
```

### Differential gate (`repro.old_deps`)

Steps 1-2 show that bad code fails on the new version. They do not show *why*: a broken
check or a typo would fail too. When `repro.old_deps` is present, `mend verify` adds:

3. `pytest check/` with `PYTHONPATH=bad` against exactly `repro.old_deps` on `repro.old_python`
   → **passes** (exit 0)

Together the three runs prove that **the version change causes the failure**: bad passes on
the old version, fails on the new one, and fixed passes on the new one (the "UPass" logic of
CodeUpdateArena, arXiv 2407.06249). A fixture with `old_deps` is verified only if all three
hold. A run whose environment cannot be built (no wheels for that Python, resolver error,
timeout) is reported as an infrastructure error, never as a verdict.

`old_deps` is optional for now; `mend verify --require-differential` fails fixtures that lack
it. Leave it out only when bad code cannot pass on *any* pre-change version, e.g. when bad
or check also call APIs that only exist after the change (`model_validate` in a Pydantic v2
fixture).

Rules for `old_deps`:
- Exact pins, like `deps`. It must pin the fixture `package` at a version that does **not**
  satisfy `versions`: normally the last release before the breaking one.
- Co-dependencies may differ from `deps` where the old ecosystem needs it: `httpx` instead of
  `httpx2` for Starlette < 1.0, `numpy==1.26.4` for pandas 1.x, no `pydantic-settings` for
  Pydantic v1. Pin them exactly so the old environment stays reproducible.
- Set `old_python` when the old pins have no wheels for `repro.python` (e.g. numpy 1.26 has
  none for 3.13). It defaults to `repro.python`.

Rules:
- Checks must test **behavior**, not text. Never grep the source file.
- `bad/` must fail for the reason described in `failure`, not a typo or ImportError of an unrelated module.
- Pin exact versions in `repro.deps` (`pydantic==2.9.2`).
- Keep files tiny (< 60 lines each). No network access in checks.

## fixture.yaml

```yaml
id: pydantic-v2-validator-decorator          # required, == directory name
title: "Using @validator instead of @field_validator in Pydantic v2"   # required
summary: >                                    # required, 1-3 sentences, plain data
  Pydantic v2 deprecates @validator; with `mode`-style semantics changed ...
ecosystem: python                             # required
package: pydantic                             # required, PyPI name
versions: ">=2.0"                             # required, PEP 440 specifier where failure applies
tags: [validation, models, migration]         # required, >=1
failure:
  kind: api-removed                           # api-removed | api-renamed | signature-changed | behavior-changed | deprecated-broken
  symptom: "PydanticUserError: ..."           # observed error / wrong behavior
  bad_pattern: "@validator('x', pre=True)"    # short snippet agents tend to write
  fix_pattern: "@field_validator('x', mode='before')"
repro:
  python: "3.12"
  deps: ["pydantic==2.9.2"]
  old_deps: ["pydantic==1.10.26"]             # optional: last release(s) before the change (differential gate)
  old_python: "3.12"                          # optional: interpreter for old_deps; defaults to python
provenance:
  sources:
    - {type: docs, url: "https://docs.pydantic.dev/latest/migration/"}
  license: "MIT"                              # license of the source material
  released: "2023-06-30"                      # optional for now: quoted ISO date of the breaking release
status: verified                              # draft | verified
```

`provenance.released` is the release date of the first `package` version that satisfies
`versions`. It is used to rank fixtures by freshness. Quote it, because an unquoted YAML date
is not a string.

`provenance.sources[].type`: `issue | pr | docs | changelog | advisory | other`. Every fixture needs ≥1 real, public source URL.
