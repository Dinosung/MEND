# MEND backlog

Direction (owner, 2026-10-14, see `MARKET_RESEARCH.md`): **C then B**.
- **C. "Claimed vs. proven" study, published first.** Re-run coding agents' "done" claims
  against the original, untouched tests and publish how often they hold.
- **B. Receipts tool, shipped with it.** A five-minute, agent-neutral check (CLI, Claude Code
  Stop hook, GitHub Action) that reproduces the study's measurement on the user's own branch.
- The breaking-change catalog stays as the study's task generator and as a narrow tripwire for
  external-service SDKs; it is not the launch story.

Design rules: deterministic checks only (no LLM judge in the verdict); **zero tokens of agent
context** (runs outside the agent, speaks only when a claim fails); agent-neutral; published
precision; keep it simple.

Budget: free work first (tasks, tool, analysis, dry runs with in-session agents). Paid API runs
only for the publishable measurement; current cap $5 total ($3.89 spent). Ask the owner before
raising it (expected ~$20-30 for the lean study).

## Now: study (C) and receipts (B)

- [ ] Impossible task variant (ImpossibleBench-style: one test contradicts another; 'do not modify tests'), then a second free dry run. Paid run only if dry runs show tasks can separate honest from dishonest agents.
- [ ] **[needs owner]** Budget for the publishable run (Claude Code Haiku k=3 + one Opus pass; Codex later).
- [ ] Measure receipts precision on all labelled cases (target ≥0.9 for blocking verdicts).
- [ ] Rewrite README around the study finding and the receipts tool.
- [ ] Publish: findings post + reproducible harness; launch the tool with it. **[needs owner]** timing.

## Parked (earlier direction)

### Phase 1: two-week pilot (to 2026-10-27), done at checkpoint

Budget: **$5 total API spend** for benchmark/probe runs until the owner raises it. Track every run's cost in `docs/PROGRESS.md`.

Question to answer: *is there a measurable effect to build on?*

- [ ] SDK fixture batch: ~15 post-cutoff breaking changes in client SDKs / service APIs agents can't run locally (LLM provider SDKs incl. OpenAI/Google GenAI/Mistral, payments, cloud, SaaS clients; Anthropic SDK 1.x follow-ups). Use the release-diff stage with an SDK-focused watchlist.
- [ ] Pilot on the SDK batch: Haiku k=3 plus one stronger model (Sonnet) on baseline-failing fixtures, within the $5 cap.
- [ ] Review all fixture checks for over-strictness (accept any correct solution; only the known failure should fail).
- [ ] Pilot verdict written to `docs/PROGRESS.md`: continue to Phase 2 only if A0 shows failures that A1 does not fix.
- [ ] **Checkpoint (owner, 2026-10-14):** after the SDK pilot, pause implementation. Write up the findings, then research market needs and gaps (real pain points, who has them, what exists, the marketing story) and return to the owner with options and a recommendation. No Phase 2 work until the owner picks a direction. The daily task is paused until then.

### Phase 2: build (parked)

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

### Kill/continue criteria (old direction)

See `STRATEGY.md`: ≥50 baseline-failing tasks, A4 beats best of A1/A2 by ≥10 points with CI
excluding zero, ≤2% false-positive harm, ≥10 verified post-cutoff fixtures/week.

## Done

- [x] 2026-10-15: Receipts tool v0 (`mend receipt`, Stop hook, GitHub Action; pre-existing failures don't block).
- [x] 2026-10-15: Study task set: 40 upgrade-rescue tasks, all verified in CI (unfixed fails, reference fix passes).
- [x] 2026-10-15: Study harness with claim parsing and outcome classes.
- [x] 2026-10-15: Free dry run: 6/6 honest passes; tasks too easy; parser bug fixed.
- [x] 2026-10-14: MEND-Bench v2 pilot: Harbor-format agentic tasks with implicit versions (lockfile only), hidden read-only tests, source-only scoring; arms A0 (none), A1 (versions line), A4 (MEND plugin); ~15 existing + ~15 post-cutoff candidates; one model, k=3. Report A0 failure rate and paired A4-vs-A1.
- [x] 2026-10-14: Release-diff prototype: griffe breaking-change diff on ~10 watchlist libraries' releases from the past 12 months; candidate list with false-positive rate.
- [x] 2026-10-14: Claude Code plugin: SessionStart hook (lockfile-scoped lookup, ≤10 fact-phrased lines) + PostToolUse hook (`mend check` on edited .py files, exit 2 with fixture IDs) + MCP server; marketplace.json; end-to-end test on a sample repo.
- [x] 2026-10-14: Ruff/pyupgrade overlap table for all fixtures (`np.trapz` first): `docs/OVERLAP.md`; fixtures already covered by ruff are marked as such.
- [x] 2026-10-14: Differential verification gate: `repro.old_deps`; bad must pass on the old version, fail on the new; fixed passes on new. Time every fixture in CI.
- [x] 2026-10-13: Lookup ranking: IDF-weighted task overlap incl. code patterns and symptom (recall@1 14/33 -> 20/33 on bench tasks).
- [x] 2026-10-13: MVP core: spec, loader/validator, uv verifier, CI, lookup/check/MCP server, MEND-Bench v1 harness, 33 verified fixtures.
- [x] 2026-10-14: Strategy research; direction adopted (`STRATEGY.md`).
- [x] 2026-10-14: Employer clearance obtained (owner).
