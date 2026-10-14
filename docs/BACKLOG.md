# MEND backlog

The daily progress run takes the top unchecked item it can complete, ships it, and
checks it off with the date. Phases and exit criteria live in `ROADMAP.md`.
Items marked **[needs owner]** require something only the maintainer can provide;
skip them and note it in the progress log.

## Now: MVP → Alpha

- [ ] Built-in `mend check` matcher: support decorator patterns (`@validator(...)`), call-with-keyword patterns (`Field(regex=...)`, `select([...])`), and `class Config:` attribute patterns, so most existing rule.yml files work without semgrep. Add tests per fixture rule.
- [ ] Run semgrep in CI against every fixture's rule.yml: must flag `bad/`, must not flag `fixed/`.
- [ ] Fixture batch: Pydantic `parse_raw_as`, `EmailStr` without email-validator, `const=True`, strict int/str coercion.
- [ ] Fixture batch: SQLAlchemy `engine.has_table`, `table_names`, `MetaData(bind=)`; FastAPI `app.routes` include_router change.
- [ ] Fixture batch: pandas `iteritems`, `applymap`, `fillna(method=)`, `read_csv(delim_whitespace=)`, groupby string-column mean.
- [ ] `mend new <package> <id>` scaffolding command that creates a spec-compliant fixture skeleton.
- [ ] GitHub Action (`action.yml`) wrapping `mend check` for PRs.
- [ ] Release workflow: build wheel + sdist on tag, bundle fixtures in the package (so `mend serve` works after `pipx install`). **[needs owner]**: PyPI trusted publishing setup.
- [ ] First real MEND-Bench run (baseline vs mend) and publish the chart in README. **[needs owner]**: `ANTHROPIC_API_KEY` as a repo secret + a bench workflow.
- [ ] Miner v0: script that turns a library's migration guide/changelog into draft fixtures for human review.
- [ ] JS/TS ecosystem: spec extension + verifier backend (node + vitest), first 10 fixtures (Next.js app router, React 19, ESLint flat config, Express 5).

## Later (Beta)

- [ ] Feedback loop: `mend capture` turns a failing CI log + diff into a draft fixture.
- [ ] Signed fixtures and provenance checks; poisoning-resistance review.
- [ ] Domain packs (security pack: pentest findings, bounty patterns).
- [ ] Hosted registry + public leaderboard.

## Done

- [x] 2026-10-13: Lookup ranking: IDF-weighted task overlap incl. code patterns and symptom (recall@1 14/33 -> 20/33 on bench tasks).

- [x] 2026-10-13: MVP core: spec, loader/validator, uv verifier, CI, lookup/check/MCP server, MEND-Bench harness, 33 verified fixtures.
