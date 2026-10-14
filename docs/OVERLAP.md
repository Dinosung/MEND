# Overlap with existing linters

Which of MEND's 33 fixtures describe mistakes that a free, widely used linter
already flags? MEND should only claim value where it is differentiated (STRATEGY.md,
pilot item 3).

**Headline: `np.trapz` is already covered.** ruff's NPY201 (`numpy2-deprecation`,
a stable rule) flags `np.trapz` and `np.in1d`, and its fix rewrites `np.trapz` to
`np.trapezoid`. The rule source also lists `np.product`, `np.cumproduct` and
`np.row_stack`. NPY201's rule page does not mention `trapz`, but the rule source
(`numpy_2_0_deprecation.rs`) does. The message wrongly says "will be removed in NumPy
2.0" (the functions were deprecated in 2.0 and removed in 2.4), but the fix is
correct. MEND's one measured win so far sits on a pattern ruff already catches,
provided the project enables `NPY` rules. They are not in ruff's default rule set.

## Result

As of 2026-10-14: **10 covered, 2 partially covered, 21 MEND-only.**

| fixture | ruff | pyupgrade | bump-pydantic | other | verdict |
|---|---|---|---|---|---|
| fastapi-app-add-event-handler-removed | - | - | n/a | - | MEND-only |
| fastapi-strict-content-type-json-body | - | - | n/a | - | MEND-only |
| fastapi-templateresponse-request-first | - | - | n/a | - | MEND-only |
| fastapi-testclient-allow-redirects | - | - | n/a | - | MEND-only |
| numpy-2-removed-aliases-nan-float | **NPY201** (all 3 lines, autofix) | - | n/a | - | covered |
| numpy-array-copy-false-raises | - | - | n/a | - | MEND-only |
| numpy-nep50-uint8-scalar-overflow | - | - | n/a | - | MEND-only |
| numpy-trapz-removed | **NPY201** (trapz + in1d, autofix) | - | n/a | - | covered |
| pandas-cow-chained-assignment-noop | - | - | n/a | - | MEND-only |
| pandas-cow-inplace-on-column-noop | **PD002** (both calls, unsafe autofix) | - | n/a | - | covered |
| pandas-dataframe-append-removed | - | - | n/a | - | MEND-only |
| pandas-offset-alias-m-removed | - | - | n/a | - | MEND-only |
| pandas-series-int-key-not-positional | - | - | n/a | - | MEND-only |
| pandas-str-dtype-not-object | - | - | n/a | - | MEND-only |
| pydantic-v2-allow-mutation-ignored | - | - | BP002 drops the key and adds a TODO; no `frozen=True`* | - | partially covered |
| pydantic-v2-allow-population-by-field-name-ignored | - | - | **BP002** → `populate_by_name`* | - | covered |
| pydantic-v2-anystr-strip-whitespace-ignored | - | - | **BP002** → `str_strip_whitespace`/`str_to_lower`* | - | covered |
| pydantic-v2-basesettings-moved | - | - | **BP004** → `pydantic_settings`* | - | covered |
| pydantic-v2-conlist-min-items-removed | - | - | **BP008** → `Annotated[List, Field(min_length=…)]`* | - | covered |
| pydantic-v2-custom-root-type-removed | - | - | BP006 matches only `__root__ = T`, not `__root__: T`* | - | MEND-only |
| pydantic-v2-field-regex-removed | - | - | **BP003** `regex` → `pattern`* | PYD001 fires on bad and fixed (not counted) | covered |
| pydantic-v2-json-dumps-kwargs-removed | - | - | does not touch `.json()` calls* | - | MEND-only |
| pydantic-v2-optional-field-required | UP045 fires on bad and fixed (not counted) | rewrites bad and fixed alike | **BP001** adds `= None`* | - | covered |
| pydantic-v2-orm-mode-ignored | - | - | **BP002** → `from_attributes`* | - | covered |
| pydantic-v2-root-validator-skip-on-failure | - | - | BP007 adds only a TODO for bare `@root_validator`* | - | partially covered |
| sqlalchemy-2-connection-autocommit-removed | - | - | n/a | - | MEND-only |
| sqlalchemy-2-engine-execute-removed | - | - | n/a | - | MEND-only |
| sqlalchemy-2-execute-kwargs-params | - | - | n/a | - | MEND-only |
| sqlalchemy-2-raw-string-sql-needs-text | - | - | n/a | - | MEND-only |
| sqlalchemy-2-row-string-key-access | - | - | n/a | - | MEND-only |
| sqlalchemy-2-select-list-argument | - | - | n/a | - | MEND-only |
| starlette-1-app-route-decorator-removed | - | - | n/a | - | MEND-only |
| starlette-1-on-startup-removed | - | - | n/a | - | MEND-only |

\* bump-pydantic result comes from reading its source, not from running it (see Method).
Per-fixture notes are in `scripts/overlap/manual_review.json`.

**Verdicts.**

- *Covered*: a tool flags the pattern lines in `bad/`, does not flag `fixed/`, and its
  message or fix leads to working code.
- *Partially covered*: the pattern is flagged, but the tool's fix is wrong or
  incomplete.
- *MEND-only*: nothing fires on the pattern.

A rule that fires on `bad/` and `fixed/` alike (UP045, PYD001, and pyupgrade's
`Optional`/`List` rewrites) is about the Python version or style, not the migration, so
it does not count. Generic rules that happen to land on a changed line are not counted
either: D106 on the removed `class Config`, N805/ANN001 on the old validator signature,
and E501.

## What remains differentiated

- **Fully covered (10). Do not claim value here:** both NumPy 2 removal fixtures
  (NPY201), pandas inplace-on-column (PD002), and 7 of the 11 Pydantic v2 fixtures
  (bump-pydantic). Keep them as regression and coverage tests, as STRATEGY.md already
  says for old migrations.
- **Partially covered (2):** `allow_mutation`, where bump-pydantic deletes the setting
  and so silently makes the model mutable, and bare `@root_validator`, where it leaves
  only a TODO and never mentions `skip_on_failure` or the `mode="after"` signature.
  MEND adds the correct fix and the proof of the failure.
- **MEND-only (21):** all of FastAPI (4), SQLAlchemy 2.0 (6) and Starlette 1.0 (2);
  pandas 2.x/3.0 (5 of 6: chained assignment under CoW, `DataFrame.append`, `"M"`/`"H"`
  aliases, `Series[int]` key, `str` dtype); NumPy `copy=False` and NEP 50 promotion;
  Pydantic `__root__: T` annotations and `.json(**dumps_kwargs)`. No ruff rule family
  covers SQLAlchemy, Starlette or Pydantic, and the FAST rules (FAST001–003) are about
  style, not migrations.

The MEND-only set is mostly changes that are semantic (behaviour changes or argument
order) or that need type information. A name-based deprecation table like NPY201 cannot
express those. That is where MEND's executed bad/fixed pair is worth having.

## Method

The table above was produced on 2026-10-14 by running each tool on every fixture's
`bad/` and `fixed/` code. A tool **covers** a fixture if it flags `bad/` but not
`fixed/`, and **partially covers** it if it flags both or mis-fixes it.

- **ruff 0.16.8, run** with `--select ALL --preview` and without `--preview`. NPY201
  and PD002 are stable but not in ruff's default rule set, so a project with no
  `select` config gets neither hit. The NPY/PD/FAST/AIR codes on ruff `main`
  (0.17.0-dev, commit a8632f8) match 0.16.8.
- **pyupgrade (3.22.0) and flake8-pydantic (0.4.0), run.** Neither covers any fixture:
  their only hits fired on `bad/` and `fixed/` alike. pyupgrade (`--py313-plus`) is
  re-run weekly; flake8-pydantic is not.
- **bump-pydantic 0.8.0, source reading.** It needs LibCST's native parser, which
  could not be installed here. Verdicts come from its codemods and unit tests (e.g.
  `REMOVED_KEYS` contains `allow_mutation`; the root matcher only matches
  `__root__ = …`). The weekly workflow runs it for real.
- **Not found:** no maintained static linter for SQLAlchemy 2.0, Starlette 1.0, or
  pandas 2.x/3.0 beyond ruff's PD rules. This search was not exhaustive.

Reviewed verdicts live in `scripts/overlap/manual_review.json` and override the
automatic one. The weekly workflow (`.github/workflows/overlap.yml`) re-runs ruff
(NPY, PD, FAST, AIR), pyupgrade and bump-pydantic with their latest releases, and
uploads `overlap.json` (per fixture: ruff codes on bad/fixed, whether each rewriting
tool touched bad/fixed, auto and reviewed verdicts); a **(differs)** row
means a tool changed or the review needs a look.

Reproduce:

```sh
pip install ruff pyupgrade bump-pydantic
python scripts/overlap/run_overlap.py fixtures > overlap.md  # also writes overlap.json
```
