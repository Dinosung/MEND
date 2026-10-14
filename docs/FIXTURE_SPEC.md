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
provenance:
  sources:
    - {type: docs, url: "https://docs.pydantic.dev/latest/migration/"}
  license: "MIT"                              # license of the source material
status: verified                              # draft | verified
```

`provenance.sources[].type`: `issue | pr | docs | changelog | advisory | other`. Every fixture needs ≥1 real, public source URL.
