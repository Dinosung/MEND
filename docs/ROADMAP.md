# MEND Roadmap

MEND's goal is to make "the agent wrote code that was correct two major versions ago" a
solved problem, and to prove it with numbers. A phase is done when its exit criteria are
met, not on a date.

## Phase 0: MVP (current)

Show the loop end to end: catalog → verify → serve to agents → measure.

- Fixture spec v0.1 and JSON schema. Seed catalog for Python: pydantic, SQLAlchemy,
  pandas, NumPy, FastAPI, Starlette.
- `mend verify`: bad must fail and fixed must pass, in an isolated `uv` (or docker)
  environment with exact pins.
- `mend lookup` and the `mend serve` MCP server (`mend_lookup`, `mend_get_fixture`,
  `mend_check`). Output is labelled and sanitized as data.
- `mend check`: semgrep rules with a built-in AST fallback.
- MEND-Bench: tasks, adapters (replay, Anthropic API, Claude Code), scorer, report.

**Exit criteria**
- [ ] ≥ 30 verified fixtures across ≥ 5 packages. All pass `mend verify` in CI on every PR.
- [ ] Replay smoke tests under `--scorer uv`: `bad` → 100% known-failure and `fixed` → 100%
      pass, on the whole catalog.
- [ ] Every fixture has a reviewed, leak-free bench task in `bench/tasks/`.
- [ ] One complete internal bench run (≥ 1 agent, both arms, ≥ 3 trials), with raw outputs
      archived.

## Phase 1: Alpha

Make MEND worth installing, and publish the first honest numbers.

- **100+ verified fixtures** across **3 ecosystems**: Python, JS/TS (npm; e.g. Next.js
  app router, React 19, Node ESM/CJS, ESLint flat config, Prisma/TypeORM), and one more
  (Go, Rust or Java, chosen by demand). Ecosystem-specific verify backends (`npx`/`pnpm
  dlx` with exact pins).
- **GitHub Action** `mend-check`: annotates PRs that introduce a known bad pattern, scoped
  to the repo's lockfile.
- **PyPI release** `mend-agent`, with the catalog bundled (and updatable via
  `mend update`). Also published as an npm wrapper for JS users.
- **First published MEND-Bench results**: ≥ 2 agents, ≥ 5 trials per task, baseline vs
  MCP vs injected context, plus a held-out (`--mend-exclude-self`) variant. The raw
  results are published with the report.

**Exit criteria**
- [ ] ≥ 100 verified fixtures; ≥ 20 of them JS/TS; ≥ 10 external contributors' fixtures merged.
- [ ] `pipx install mend-agent && claude mcp add mend -- mend serve` works on a clean
      machine with no repo clone.
- [ ] GitHub Action is used in ≥ 5 public repos other than ours.
- [ ] Published bench report with confidence intervals, run config and raw data. The
      result is published whether MEND helps or not.

## Phase 2: Beta

Scale the catalog without scaling maintainer effort, and harden it against abuse.

- **Automated miner**: mines candidate fixtures from GitHub issues ("AttributeError after
  upgrading to …"), changelogs and migration guides, and Stack Overflow. An LLM drafts
  `bad/`, `fixed/` and `check/`, and the verifier gates them. Humans review every draft.
- **Feedback loop**: an opt-in CI/agent hook that captures real agent failures (a failing
  test plus the diff that fixed it) and proposes them as draft fixtures, de-duplicated
  against the catalog.
- **Signed fixtures and anti-poisoning**: Sigstore-signed catalog releases, verification
  reproduced by CI rather than trusted from the contributor, contributor reputation,
  diff-review rules for fixture text, and red-team tests that the rendered output cannot
  carry instructions.
- **Packs**: curated subsets that can be installed (e.g. `django-5`, `pydantic-v2`,
  `security`). The security pack covers insecure-default APIs agents keep using (e.g.
  `yaml.load` without a Loader, `verify=False`, deprecated crypto primitives), checked by
  behavior and not by grep.

**Exit criteria**
- [ ] ≥ 50% of newly merged fixtures originate from the miner or the feedback loop.
- [ ] Miner precision ≥ 70% (drafts that verify and pass human review).
- [ ] Every catalog release is signed and reproducibly re-verified. A documented
      poisoning threat model has been externally reviewed.
- [ ] ≥ 500 verified fixtures; security pack ≥ 30 fixtures.
- [ ] A second bench report shows whether the effect holds at catalog scale. Retrieval
      precision (are irrelevant records crowding out relevant ones?) is reported.

## Phase 3: 1.0

MEND becomes infrastructure.

- **Hosted registry**: versioned catalog API, search, per-package pages, and a
  self-hostable mirror for orgs with private fixtures.
- **Public leaderboard**: MEND-Bench repeat-failure rates for major agents/models, re-run
  on every catalog release, with a held-out split to deter overfitting.
- **Build-time integration**: like a compiler, MEND checks happen where code is built and
  not only where it is written. Integration points are language-server diagnostics, the
  pre-commit/CI gate, and a resolver hook that warns when a lockfile bump makes existing
  code hit a known failure.
- Stable spec v1.0 with a compatibility promise.

**Exit criteria**
- [ ] Registry serves ≥ 3 independent clients (agents/IDEs) in production.
- [ ] Leaderboard covers ≥ 5 agents and is re-run automatically on each release.
- [ ] Fixture spec v1.0 frozen; v0.x fixtures migrated automatically.
- [ ] A governance doc and ≥ 3 maintainers outside the original author.
