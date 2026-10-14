# MEND-Bench report: 20261014T025952Z-anthropic_api

agent `anthropic_api` model `claude-sonnet-5-5`, scorer `local`, 21 fixtures x 3 trials, 126 records.

> Scored with `--scorer local` (current interpreter, pins NOT enforced). Smoke-test only; not a benchmark result.

## Headline: repeat-failure rate

Share of scored trials (infra errors excluded) whose solution reproduces the fixture's known failure. 95% Wilson intervals.

| arm | repeat-failure rate | pass rate | other-failure | infra-error |
|---|---|---|---|---|
| baseline | 0.0% [0.0%, 6.0%] (0/60) | 100.0% [94.0%, 100.0%] (60/60) | 0 | 3 |
| mend | 0.0% [0.0%, 6.0%] (0/60) | 100.0% [94.0%, 100.0%] (60/60) | 0 | 3 |

**Baseline -> MEND:** 0.0% -> 0.0% (absolute +0.0 pp, relative reduction n/a).
Intervals are per-arm; overlapping intervals mean the difference is not established.

## Outcomes by arm

| arm | pass | known-failure | other-failure | infra-error | total |
|---|---|---|---|---|---|
| baseline | 60 | 0 | 0 | 3 | 63 |
| mend | 60 | 0 | 0 | 3 | 63 |

## Per package (repeat-failure rate)

| package | baseline | mend |
|---|---|---|
| numpy | 0.0% [0.0%, 24.2%] (0/12) | 0.0% [0.0%, 24.2%] (0/12) |
| pandas | 0.0% [0.0%, 17.6%] (0/18) | 0.0% [0.0%, 17.6%] (0/18) |
| pydantic | 0.0% [0.0%, 11.4%] (0/30) | 0.0% [0.0%, 11.4%] (0/30) |

## Per fixture

| fixture | baseline | mend |
|---|---|---|
| `numpy-2-removed-aliases-nan-float` | P3 | P3 |
| `numpy-array-copy-false-raises` | P3 | P3 |
| `numpy-nep50-uint8-scalar-overflow` | P3 | P3 |
| `numpy-trapz-removed` | P3 | P3 |
| `pandas-cow-chained-assignment-noop` | P3 | P3 |
| `pandas-cow-inplace-on-column-noop` | P3 | P3 |
| `pandas-dataframe-append-removed` | P3 | P3 |
| `pandas-offset-alias-m-removed` | P3 | P3 |
| `pandas-series-int-key-not-positional` | P3 | P3 |
| `pandas-str-dtype-not-object` | P3 | P3 |
| `pydantic-v2-allow-mutation-ignored` | P3 | P3 |
| `pydantic-v2-allow-population-by-field-name-ignored` | P3 | P3 |
| `pydantic-v2-anystr-strip-whitespace-ignored` | P3 | P3 |
| `pydantic-v2-basesettings-moved` | I3 | I3 |
| `pydantic-v2-conlist-min-items-removed` | P3 | P3 |
| `pydantic-v2-custom-root-type-removed` | P3 | P3 |
| `pydantic-v2-field-regex-removed` | P3 | P3 |
| `pydantic-v2-json-dumps-kwargs-removed` | P3 | P3 |
| `pydantic-v2-optional-field-required` | P3 | P3 |
| `pydantic-v2-orm-mode-ignored` | P3 | P3 |
| `pydantic-v2-root-validator-skip-on-failure` | P3 | P3 |

P = pass, K = known-failure, O = other-failure, I = infra-error.

## Infra errors

- `pydantic-v2-basesettings-moved` baseline t0: local scorer: pinned dependency missing in this interpreter
- `pydantic-v2-basesettings-moved` baseline t1: local scorer: pinned dependency missing in this interpreter
- `pydantic-v2-basesettings-moved` baseline t2: local scorer: pinned dependency missing in this interpreter
- `pydantic-v2-basesettings-moved` mend t0: local scorer: pinned dependency missing in this interpreter
- `pydantic-v2-basesettings-moved` mend t1: local scorer: pinned dependency missing in this interpreter
- `pydantic-v2-basesettings-moved` mend t2: local scorer: pinned dependency missing in this interpreter

## Environment notes

- local scorer: python 3.13.16 (pinned 3.12)
- local scorer: python 3.13.16 (pinned 3.13)
- missing dep pydantic-settings (pinned ==2.5.2)
- pydantic 2.13.5 != pinned ==2.9.2
