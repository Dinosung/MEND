# Release-diff pipeline (stage "Detect")

This is the first automated stage of the fixture pipeline described in
[STRATEGY.md](STRATEGY.md#build-a-pipeline-that-mints-witness-programs-from-release-diffs)
(pilot item 5). Given a library and two release tags, it lists **candidate breaking
changes in the public API**. Later stages (draft, verify, probe) turn candidates into
fixtures. Its output is machine-generated *data* for review. It never contains instructions.

```
pipeline/
  watchlist.yaml        # libraries, repos, tag patterns, release pairs (+ dates), changelog paths
  release_diff.py       # CLI: library + old tag + new tag -> JSON candidates
  candidates/*.json     # one file per diffed release pair (<= 200 candidates each)
tests/test_release_diff.py
```

## How to run

```bash
# one release pair (library must be in pipeline/watchlist.yaml)
python3.13 -I pipeline/release_diff.py pandas v2.3.3 v3.0.0
# every pair in the watchlist, or every pair for one library
python3.13 -I pipeline/release_diff.py --all
python3.13 -I pipeline/release_diff.py numpy --all
# options
#   --cache DIR        checkout cache (default ~/.cache/mend-pipeline or $MEND_PIPELINE_CACHE)
#   --griffe-path DIR  griffe sources (dir containing the `griffe` package); else $MEND_GRIFFE_PATH,
#                      else griffe 2.3.2 is git-cloned into the cache
#   --limit N          max candidates per diff (default 200)
#   --out FILE|-       output path, '-' = stdout (default pipeline/candidates/<lib>-<old>-<new>.json)
```

Requirements: Python ≥ 3.11 (griffe's floor; the project uses 3.13 here), `git`, and network access to
github.com. Nothing is installed from PyPI. The script uses the standard library and griffe
(`griffelib` has no runtime dependencies). It also uses pyyaml, a MEND core dependency, to read the watchlist.
A full `--all` run over the 26 release pairs below took about 3.5 minutes with a cold cache.

Tests (pure logic, no network; the griffe integration test runs only when `MEND_GRIFFE_PATH` is set):

```bash
PYTHONPATH=src:. python -m pytest -q tests/test_release_diff.py
```

## What it does

1. **Checkout.** `git clone --depth 1 --branch <tag> --filter=blob:none --no-checkout`, then a cone
   sparse-checkout of just the package directory and the changelog files. The script never imports,
   builds or executes anything from a checkout. Hooks are disabled (`core.hooksPath=/dev/null`)
   and LFS smudge is off.
2. **Diff.** `griffe.load(pkg, search_paths=[src], allow_inspection=False)` for both trees, then
   `griffe.find_breaking_changes`. This is purely static: C extensions are not needed, and `.pyi` stubs are merged.
   One patch: griffe aborts the whole traversal on a `CyclicAliasError` (numpy 2.5 has one), so the
   alias step is wrapped to skip and record unresolvable aliases instead (`errors` in the JSON).
   With that patch, griffe succeeded on all 26 diffs. If griffe fails on a package, the error is
   recorded and that package is skipped.
3. **Re-export check.** griffe only diffs members it considers public, and it skips
   `from .core import Option` re-exports in packages without `__all__` (click, starlette). Removed
   package-level re-exports are therefore added separately (`removed_reexports`).
4. **Public-API filter.** It builds an index of canonical object path to public spellings by
   following re-export chains, for example `pandas.core.frame.DataFrame` maps to `pandas.DataFrame`.
   Each breakage is mapped to its shortest public path. It is dropped if no public spelling exists:
   `_private` segments, `tests`/`testing`, non-callable dunders, and per-library `internal_segments`
   such as `pandas.core` and `fastapi.dependencies`.
5. **Classify.** The categories are `removed_symbol`, `removed_parameter`, `renamed_parameter`
   (a removed parameter plus a similar new one at the same position or with a similar name),
   `new_required_parameter`, `parameter_now_required`, `changed_parameter_kind`, `moved_parameter`
   and `changed_default`. `failure_mode` is `hard` (ImportError/AttributeError/TypeError on the old
   call), `soft` (silent behaviour change) or `shim` (see flags).
6. **Drop known noise:**
   - attribute value/type changes, return-type changes, object-kind changes and removed base classes (typing churn)
   - private/variadic parameters (`*args`, `**kw`, the first parameter of `__new__`)
   - `...` stub defaults
   - sentinel renames (`notset` → `NOTSET`)
   - deprecation sentinels (a default changed to `'deprecated'`/`'warn'` is still a warning, not a break)
7. **Flag likely noise.** Flagged candidates are kept but ranked lower:
   - `reexported_elsewhere`: the same canonical object is still public under another path (moved).
   - `module_getattr_shim`: the new module defines `__getattr__` and mentions the name. This is either a
     deprecation shim that still works or a curated error, and a check must tell which (`failure_mode: shim`).
   - `may_be_inherited`: the class now has a base from another library somewhere in its hierarchy,
     so the "removed" method may simply be inherited (starlette `TestClient` → `httpx2.Client`).
   - `stub_only`: the object lives in a `.pyi`.
8. **Corroborate.** `changelog_mentions` lists the candidate's identifiers when they occur
   *together in one paragraph* of the new release notes. Cumulative changelogs are first cut at the
   old release's heading. For a parameter, the parameter and its function name must co-occur; for a class
   member, the class and the member name must co-occur.
9. **Rank.** `score` = category weight + public-path shortness + 3 if a segment is in the
   library's `hot_symbols` + 2 if the changelog corroborates, − penalties for the flags above.

Each candidate records `path` (griffe/canonical location), `public_path`, `param`, `old_value`/`new_value`,
`renamed_to`, `file`/`lineno` (in the source tree), `flags`, `changelog_mentions` and `score`.

## Watchlist and results (run 2026-10-14)

All 26 diffs used griffe. Dates are tag commit dates. "Kept" is after filtering (capped at 200);
"CL" means the candidate is corroborated by the release notes.

| library | old | new | raw | kept | hard | CL |
|---|---|---|---|---|---|---|
| numpy | v2.3.5 (2025-11-16) | v2.4.0 (2025-12-20) | 544 | 108 | 93 | 20 |
| numpy | v2.4.6 (2026-05-18) | v2.5.0 (2026-06-21) | 103 | 7 | 7 | 6 |
| pandas | v2.3.3 (2025-09-30) | v3.0.0 (2026-01-21) | 5052 | 200 | 173 | 140 |
| pydantic | v2.12.5 (2025-11-26) | v2.13.0 (2026-04-13) | 5 | 1 | 1 | 0 |
| pydantic | v2.13.5 (2026-08-28) | v2.14.0 (2026-10-08) | 30 | 0 | 0 | 0 |
| fastapi | 0.119.1 (2025-10-20) | 0.143.0 (2026-10-08) | 143 | 52 | 51 | 2 |
| starlette | 0.52.1 (2026-01-18) | 1.0.0 (2026-03-22) | 32 | 26 | 23 | 24 |
| starlette | 1.0.0 (2026-03-22) | 1.8.0 (2026-10-13) | 12 | 9 | 9 | 0 |
| sqlalchemy | rel_2_0_54 (2026-09-15) | rel_2_1_0 (2026-09-24) | 434 | 200 | 183 | 43 |
| django | 5.2.7 (2025-10-01) | 6.0 (2025-12-03) | 262 | 137 | 134 | 29 |
| django | 6.0.8 (2026-08-04) | 6.1 (2026-08-05) | 168 | 51 | 37 | 11 |
| langchain-core | 0.3.79 (2025-10-09) | 1.0.0 (2025-10-17) | 175 | 151 | 150 | 1 |
| langchain-core | 1.0.0 (2025-10-17) | 1.6.0 (2026-08-19) | 33 | 11 | 2 | 0 |
| langchain | 0.3.27 (2025-07-24) | 1.0.0 (2025-10-17) | 3042 | 200 | 200 | 5 |
| openai | v1.109.0 (2025-09-23) | v2.0.0 (2025-09-30) | 1 | 0 | 0 | 0 |
| openai | v2.54.0 (2026-08-11) | v3.0.0 (2026-08-12) | 7 | 0 | 0 | 0 |
| anthropic | v0.125.0 (2026-08-19) | v1.0.0 (2026-08-20) | 403 | 103 | 103 | 61 |
| pytest | 8.4.2 (2025-09-03) | 9.0.0 (2025-11-08) | 37 | 6 | 5 | 0 |
| pytest | 9.0.3 (2026-04-07) | 9.1.0 (2026-06-13) | 76 | 1 | 1 | 0 |
| click | 8.2.2 (2025-07-29) | 8.3.0 (2025-09-12) | 4 | 2 | 0 | 0 |
| click | 8.3.3 (2026-04-17) | 8.4.0 (2026-05-16) | 1 | 0 | 0 | 0 |
| click | 8.4.2 (2026-06-23) | 8.5.0 (2026-08-21) | 13 | 7 | 0 | 7 |
| scikit-learn | 1.7.2 (2025-09-08) | 1.8.0 (2025-12-09) | 364 | 52 | 37 | 7 |
| scikit-learn | 1.8.0 (2025-12-09) | 1.9.0 (2026-06-02) | 486 | 37 | 27 | 13 |
| polars | py-1.44.2 (2026-09-08) | py-2.0.0 (2026-10-06) | 273 | 200 | 184 | 142 |
| matplotlib | v3.10.9 (2026-04-23) | v3.11.0 (2026-06-11) | 256 | 74 | 65 | 14 |

These libraries were considered and skipped. httpx has had no stable release since 0.28.1 (2024-12), and
its 1.0 exists only as a 2021 beta tag; the ecosystem moved to the `httpx2` fork, which openai 3.0 and anthropic 1.0
now use. requests 2.33 and 2.34 had no API removals. typer and celery are left for a later batch, and boto3 is too large.

Empty or near-empty results are mostly genuine:
- **openai 2.0/3.0** broke only types and dependencies (a `.output` union type; httpx → httpx2), which are invisible to signature diffing.
- **pydantic 2.13/2.14** made no signature-level removals (the 30 raw items in 2.14 are attribute-value changes).
- **click 8.4** had nothing to report.

These releases need the behavioural and LLM-release-notes legs of the pipeline instead.

## Measured false-positive rate

Method: the top 10 candidates of every non-empty diff (176 candidates; click 8.5's 7 `shim` items
are reported separately) were labelled against the release notes and, where the notes were silent,
the old and new source. A random sample of 5 lower-ranked candidates (rank > 10, seed 0) was also labelled
for 8 large diffs (40 candidates). The labels are:
- **R**: a real change that old code calling the public spelling would hit.
- **N**: noise, meaning nothing a caller does breaks.

"Agent-relevant" is a separate, stricter judgement: an agent would plausibly write the old call.

| diff | top-10 R / sampled | FP | tail R / 5 | notes on the FPs |
|---|---|---|---|---|
| numpy 2.4 | 9/10 | 10% | 3/5 | positional-only markers added to C-function dispatcher stubs (`np.where(condition=...)` never worked) |
| numpy 2.5 | 2/7 | 71% | – | `.pyi` restructuring (`ndarray.diagonal/nonzero`, `chararray.*`, `Generator.permuted` are still there at runtime) |
| pandas 3.0 | 10/10 | 0% | 3/5 | tail: `lib.no_default` deprecation sentinels (`set_index(verify_integrity)`, `rename(copy)`) |
| pydantic 2.13 | 0/1 | 100% | – | `field_serializer(field, /, *fields)` overload: only a zero-argument call breaks |
| fastapi 0.143 | 2/10 | 80% | – | pydantic-v1-only branches (`if PYDANTIC_V2: ... else: class Config`) and `params.*.deprecated` inherited from pydantic `FieldInfo` (now flagged `may_be_inherited`) |
| starlette 1.0 | 10/10 | 0% | – | |
| starlette 1.8 | 2/9 | 78% | – | `TestClient.get/post/...` are now inherited from `httpx2.Client` (flagged `may_be_inherited`, ranked low) |
| sqlalchemy 2.1 | 8/10 | 20% | 5/5 | `Table(name, metadata, /)`: positional-only, but callers always pass these positionally; the tail is real but entirely internal (`orm.unitofwork`, `orm.strategies`) |
| django 6.0 | 10/10 | 0% | 5/5 | |
| django 6.1 | 7/10 | 30% | – | `match_re` became conditional; an incidental `RemovedInDjango61Warning` import; `Aggregate(order_by=())`→`None` default |
| langchain-core 1.0 | 10/10 | 0% | – | |
| langchain-core 1.6 | 10/10 | 0% | – | |
| langchain 1.0 | 10/10 | 0% | – | whole legacy modules moved to `langchain-classic` |
| anthropic 1.0 | 10/10 | 0% | 5/5 | |
| pytest 9.0 | 6/6 | 0% | – | all real but `OptionGroup` internals (constructor is `_ispytest`) |
| pytest 9.1 | 1/1 | 0% | – | |
| click 8.3 | 2/2 | 0% | – | `UNSET` sentinel default (soft) |
| click 8.5 | 7 shims | – | – | all 7 are deprecation shims via module `__getattr__`, correctly labelled `failure_mode: shim` |
| scikit-learn 1.8 | 6/10 | 40% | – | class annotation `steps: list` on a mixin; deprecations in progress (`y_pred`→`y_score`, `estimator_name`) |
| scikit-learn 1.9 | 6/10 | 40% | 5/5 | `deprecate_positional_args`-style keyword-only changes (still accept positional with a warning) |
| polars 2.0 | 10/10 | 0% | 5/5 | |
| matplotlib 3.11 | 9/10 | 10% | 4/5 | `pyplot.savefig(*args)` → `savefig(fname, **kw)` (no real call breaks) |
| **total** | **140/176** | **20%** | **35/40 (12.5%)** | |

**Overall precision is about 80% on the top 10 and about 88% deeper in the list.** It varies widely by library:
- **0–10% FP** on pure-Python libraries with conventional deprecate-then-remove cycles: pandas, django 6.0,
  starlette 1.0, langchain, anthropic, polars and matplotlib.
- **40–80% FP** where the public API is shaped by stubs, version-gated branches or inheritance from
  another library: numpy 2.5, fastapi, starlette 1.8 and scikit-learn.

Precision is not relevance. A sizeable share of the "real" items are internals no agent would call
(sqlalchemy's tail, pytest `OptionGroup`, django `get_joining_columns`). This share was not measured. The
`hot_symbols` boost and the review stage handle that.

The main remaining FP sources, roughly in order of size, and possible fixes:
1. **Stub corrections and typing.** Adding `/` to C-function dispatcher stubs or moving methods
   between stub classes. A cheap fix would be to ignore positional-only changes when the old signature had no
   Python implementation, or to cross-check with `inspect` in a sandbox.
2. **Conditional definitions.** Code under `if PYDANTIC_V2:/else:` or `TYPE_CHECKING` is diffed as if both branches
   exist.
3. **Inheritance from another library.** This is now flagged `may_be_inherited`.
4. **Deprecations in progress.** Signature changes behind `@deprecate_positional_args` or sentinel defaults.

The changelog-co-occurrence signal is a good precision filter where the release notes are structured.
Almost every corroborated top-10 candidate was labelled R; the clear exceptions in the table are numpy 2.5's stub items,
which matched a broad typing paragraph. Recall depends on the notes:
- The langchain and fastapi notes are too thin or too noisy to corroborate anything.
- The anthropic `MIGRATION.md` and polars `upgrade/2.md` tables corroborate almost everything.

## Top 30 candidates for fixtures

The ranking puts first APIs agents use a lot, changes that are hard failures (a TypeError or AttributeError
rather than a warning), and releases from after mid-2025 that are likely past model cutoffs.
"Covered" refers to the existing `fixtures/`.

| # | library (release, date) | old pattern an agent writes → what happens | kind | covered? |
|---|---|---|---|---|
| 1 | anthropic 1.0 (2026-08-20) | `client.messages.create(..., temperature=0.2)` (also `top_p`, `top_k`, and in `.stream()`/`.parse()`) → TypeError; use `extra_body` or drop it | removed_parameter | no |
| 2 | anthropic 1.0 | `client.completions.create(prompt=f"{HUMAN_PROMPT}...")`, `anthropic.HUMAN_PROMPT`/`AI_PROMPT` → AttributeError/ImportError | removed_symbol | no |
| 3 | anthropic 1.0 | `client.beta.messages.create(..., output_format={...})` → TypeError; use `output_config={"format": ...}` | removed_parameter | no |
| 4 | langchain 1.0 (2025-10-17) | `from langchain.chains import LLMChain` / `langchain.memory` / `langchain.text_splitter` / `langchain.document_loaders` / `langchain.hub` → ModuleNotFoundError; moved to `langchain_classic` / `langchain_text_splitters` | removed_symbol | no |
| 5 | langchain-core 1.0 (2025-10-17) | `llm.predict(...)`, `llm(messages)`, `llm.predict_messages(...)`, `apredict` → AttributeError/TypeError; use `.invoke()` | removed_symbol | no |
| 6 | langchain-core 1.0 | `retriever.get_relevant_documents(q)` → AttributeError; use `.invoke(q)` | removed_symbol | no |
| 7 | pandas 3.0 (2026-01-21) | `pd.read_csv(f, delim_whitespace=True)` → TypeError; use `sep=r"\s+"` | removed_parameter | no |
| 8 | pandas 3.0 | `pd.read_csv(..., date_parser=..., infer_datetime_format=True, keep_date_col=True)`; `pd.to_datetime(..., infer_datetime_format=True)` → TypeError | removed_parameter | no |
| 9 | pandas 3.0 | `df.applymap(f)` → AttributeError; use `df.map(f)` | removed_symbol | no |
| 10 | pandas 3.0 | `df.groupby(key, axis=1)` → TypeError | removed_parameter | no |
| 11 | pandas 3.0 | `df.first("3D")` / `df.last(...)`, `df.pad()`/`backfill()`, `df.swapaxes()`, `df.bool()`, `Series.view()` → AttributeError | removed_symbol | no |
| 12 | pandas 3.0 | `pd.value_counts(s)` → AttributeError | removed_symbol | no |
| 13 | pandas 3.0 | `pd.read_parquet(p, use_nullable_dtypes=True)` → TypeError; use `dtype_backend=` | removed_parameter | no |
| 14 | django 6.0 (2025-12-03) | `CheckConstraint(check=Q(...), name=...)` → TypeError; use `condition=` | removed_parameter | no |
| 15 | django 6.0 | `send_mail(subj, msg, from_, to, False)` → TypeError: optional args are keyword-only | changed_parameter_kind | no |
| 16 | polars 2.0 (2026-10-06) | `df.melt(...)` / `lf.melt(...)` → AttributeError; use `unpivot` | removed_symbol | no |
| 17 | polars 2.0 | `pl.read_csv(..., rechunk=...)`, `pl.read_parquet/scan_parquet(..., allow_missing_columns=..., retries=...)`, `scan_csv(cache=...)` → TypeError | removed_parameter | no |
| 18 | numpy 2.4 (2025-12-20) | `np.trapz(y, x)`, `np.in1d(a, b)` → AttributeError | removed_symbol | **yes** (`numpy-trapz-removed`) |
| 19 | numpy 2.4 | `np.percentile(a, q, interpolation="nearest")` (and `quantile`) → TypeError; use `method=` | removed_parameter | no |
| 20 | numpy 2.4 | `np.corrcoef(x, bias=..., ddof=...)`, `np.save(f, a, fix_imports=...)` → TypeError | removed_parameter | no |
| 21 | numpy 2.4 | `from numpy.linalg.linalg import ...`, `numpy.fft.helper` → ModuleNotFoundError | removed_symbol | no |
| 22 | numpy 2.5 (2026-06-21) | `np.row_stack(...)` → AttributeError; use `np.vstack` | removed_symbol | no |
| 23 | starlette 1.0 (2026-03-22) | `Starlette(on_startup=[...])`, `@app.route(...)`, `@app.on_event("startup")`, `@app.exception_handler(...)`, `@app.middleware("http")`, `app.add_event_handler(...)` → TypeError/AttributeError | removed_* | **partly**: `starlette-1-on-startup-removed`, `starlette-1-app-route-decorator-removed`; `on_event`/`exception_handler`/`middleware` decorators not yet |
| 24 | starlette 1.0 | `FileResponse(path, method="HEAD")` → TypeError | removed_parameter | no |
| 25 | matplotlib 3.11 (2026-06-11) | `matplotlib.cm.get_cmap("viridis")` → AttributeError; use `matplotlib.colormaps[...]` | removed_symbol | no |
| 26 | matplotlib 3.11 | `ax.plot_date(dates, y)` / `plt.plot_date` → AttributeError; use `plot` | removed_symbol | no |
| 27 | sqlalchemy 2.1 (2026-09-24) | `Session.close_all()` / `sessionmaker.close_all()` → AttributeError; use `close_all_sessions()` | removed_symbol | no |
| 28 | sqlalchemy 2.1 | `stmt.select()` on a `Select`/`CompoundSelect` (deprecated since 1.4) → AttributeError; use `.subquery().select()` | removed_symbol | no |
| 29 | scikit-learn 1.8 (2025-12-10) | `LogisticRegression(multi_class="multinomial")` → TypeError; `learning_curve/validation_curve(..., fit_params=...)` → TypeError (use `params=`) | removed_parameter | no |
| 30 | scikit-learn 1.9 (2026-06-02) | `LassoCV(n_alphas=...)` / `ElasticNetCV(n_alphas=...)`, `ColumnTransformer(force_int_remainder_cols=...)` → TypeError | removed_parameter | no |

The pipeline also found these soft (behavioural) changes, which need a behavioural check rather than a call that fails:
- langchain-core 1.6: `load()`/`loads(secrets_from_env=True→False)`, a security default.
- click 8.3: `Option(flag_value/default None→UNSET)`.
- scikit-learn 1.8: `LogisticRegression(l1_ratio None→0.0)`.
- sqlalchemy 2.1: `MetaData.create_all(checkfirst=True→CheckFirst.ALL)`.

Coverage: 2 of the top 30 rows are covered by existing fixtures (#18, and #23 in part). The existing
`fastapi-app-add-event-handler-removed` fixture also corresponds to #23. The pipeline did *not* surface it from the fastapi
diff because `FastAPI` inherits that method from `Starlette`, a dependency. See the limitations below.

## Limitations and next steps

- **Inherited-from-dependency breakage is invisible.** A FastAPI user hits Starlette 1.0's
  removals through `FastAPI(...)`. The next step is to diff the dependency's classes that the
  library re-exports or subclasses (FastAPI→Starlette, langchain→langchain-core) and attribute them to the subclass.
- **Behaviour, type and dependency changes** (pandas CoW/str dtype, openai/anthropic httpx2, return types) are out
  of scope for signature diffing. They need the LLM release-notes extractor from STRATEGY.md.
- **Static analysis only.** There is no `inspect` diff of C extensions yet. numpy and scikit-learn would benefit most, from
  running `inspect.signature` on both versions in an isolated uv venv. That is the planned "verify" sandbox, not this stage.
- **Ranking ignores real usage frequency.** `hot_symbols` is a hand-written proxy. GitHub code-search
  counts or PyPI-dependent usage would be better.
- **The release event poller is not built.** `tag_pattern` in the watchlist is there for it.

## Problems hit while building this

- PyPI and the GitHub REST API are not reachable from this environment; only `git` over github.com works. Release
  dates therefore come from tag commit dates via treeless clones, and griffe runs from a source checkout
  (`packages/griffelib/src` at tag 2.3.2). griffe has no runtime dependencies.
- griffe aborts `find_breaking_changes` on a `CyclicAliasError` (numpy 2.5: `frompyfunc`). The
  traversal step is wrapped to skip and record such aliases.
- griffe treats re-exports in packages without `__all__` as non-public, so their removal is invisible to it.
  The script adds an explicit re-export diff to cover this.
- Several layout quirks needed per-library config:
  - langchain 0.3 lives in `libs/langchain` while langchain 1.0 lives in `libs/langchain_v1` (`src_root_overrides`).
  - pytest's API is the private `_pytest` re-exported by `pytest`.
  - polars is in `py-polars/src`.
- Cumulative changelogs (fastapi, starlette, pytest, click, the SDKs) had to be trimmed at the old release's heading.
  Without trimming, any old entry "corroborated" a candidate.
