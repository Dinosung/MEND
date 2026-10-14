"""MEND-Bench v2 pilot: agentic, in-repo, implicit-version tasks with hidden tests.

Modules:
  taskgen   fixture -> small project dir + prompt + hidden test (and leak checks)
  arms      A0 / A1 / A4 workdir variants (CLAUDE.md fact line, project-local hooks)
  agents    claude_code (headless `claude -p`), anthropic_api (single-shot), replay
  score     source-only scoring of the agent's workdir against the hidden check
  stats     Wilson, paired bootstrap, exact McNemar
  report    report.md + summary.json
  run       the runner (`python -m bench.v2.run`)

See bench/v2/README.md and docs/BENCH_V2.md.
"""
