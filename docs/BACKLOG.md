# MEND backlog

Direction: see `STRATEGY.md` (adopted 2026-10-14). MEND is a **verified post-cutoff
tripwire** for Python: witness programs for breaking changes from roughly the last 18
months, delivered by hooks and CI, with a probe step recording which current models
actually make each mistake.

The daily progress run takes the top unchecked item it can complete, ships it, and
checks it off with the date. Items marked **[needs owner]** require the maintainer;
skip them and note it in the progress log.

Out of scope until the mid-January 2027 verdict: JS/TS, security weaknesses,
hallucinated packages, project-specific lessons, hand-authoring well-known pre-cutoff
migrations. Public launch waits for benchmark results.

## Phase 1: two-week pilot (to 2026-10-27)

Budget: **$5 total API spend** for benchmark/probe runs until the owner raises it. Track every run's cost in `docs/PROGRESS.md`.

Question to answer: *is there a measurable effect to build on?*

- [ ] Differential verification gate: `repro.old_deps`; bad must pass on the old version, fail on the new; fixed passes on new. Time every fixture in CI.
- [ ] Ruff/pyupgrade overlap table for all fixtures (`np.trapz` first): `docs/OVERLAP.md`; fixtures already covered by ruff are marked as such.
- [ ] Claude Code plugin: SessionStart hook (lockfile-scoped lookup, ≤10 fact-phrased lines) + PostToolUse hook (`mend check` on edited .py files, exit 2 with fixture IDs) + MCP server; marketplace.json; end-to-end test on a sample repo.
- [ ] Release-diff prototype: griffe breaking-change diff on ~10 watchlist libraries' releases from the past 12 months; candidate list with false-positive rate.
- [ ] MEND-Bench v2 pilot: Harbor-format agentic tasks with implicit versions (lockfile only), hidden read-only tests, source-only scoring; arms A0 (none), A1 (versions line), A4 (MEND plugin); ~15 existing + ~15 post-cutoff candidates; one model, k=3. Report A0 failure rate and paired A4-vs-A1.
- [ ] Pilot verdict written to `docs/PROGRESS.md`: continue to Phase 2 only if A0 shows failures that A1 does not fix.

## Phase 2: build (to ~mid-January 2027)

- [ ] Pipeline automation: PyPI feed polling for a download-ranked watchlist, griffe + release-note extraction, LLM drafting, four verification gates, probe step, scheduled Actions. Target ~100 candidates, 50+ verified probed fixtures, <15 min review each.
- [ ] Probe status per fixture: per-model failure rate, `retired` date when models stop failing.
- [ ] Pre-commit hook and GitHub Action (`action.yml`) for `mend check`.
- [ ] `mend context`: write a short fact-phrased block into AGENTS.md / Cursor rules / Copilot instructions.
- [ ] Semgrep rule-pack export (MEND's own rules only; never redistribute Semgrep registry rules).
- [ ] Trust controls: `SECURITY.md` + threat model; CI lint for hidden/bidi Unicode, HTML comments, field length caps; PyPI existence-and-age check for packages named in fixes; signed catalog releases; SHA-pinned actions, read-only tokens.
- [ ] MEND-Bench v2 full run: ≥100 tasks, all arms (A0–A5, oracle, do-nothing) incl. Context7, two models, Claude Code + Codex subset, private held-out split, paired stats with CIs.
- [ ] Publish results (including negative ones): blog post, HF dataset, arXiv draft. **[needs owner]** for launch timing.
- [ ] **[needs owner]** Choose data licence (CC-BY-4.0 vs CDLA-Permissive-2.0); code stays MIT.
- [ ] **[needs owner]** PyPI trusted publishing for `mend-agent`.

## Kill/continue criteria (mid-January 2027)

See `STRATEGY.md`: ≥50 baseline-failing tasks, A4 beats best of A1/A2 by ≥10 points with CI
excluding zero, ≤2% false-positive harm, ≥10 verified post-cutoff fixtures/week.

## Done

- [x] 2026-10-13: Lookup ranking: IDF-weighted task overlap incl. code patterns and symptom (recall@1 14/33 -> 20/33 on bench tasks).
- [x] 2026-10-13: MVP core: spec, loader/validator, uv verifier, CI, lookup/check/MCP server, MEND-Bench v1 harness, 33 verified fixtures.
- [x] 2026-10-14: Strategy research; direction adopted (`STRATEGY.md`).
- [x] 2026-10-14: Employer clearance obtained (owner).
