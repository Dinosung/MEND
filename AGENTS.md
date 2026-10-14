# Working on MEND (for humans and agents)

Read `docs/FIXTURE_SPEC.md` first. The example fixture is
`fixtures/pydantic/pydantic-v2-basesettings-moved/`.

## Module contracts (src/mend/)

| Module | Public API | CLI |
|---|---|---|
| `fixture.py` | `Fixture` dataclass; `load_fixture(path) -> Fixture`; `load_all(root="fixtures") -> list[Fixture]`; `validate(fixture) -> list[str]` (errors) | `mend list` |
| `verify.py` | `verify_fixture(fixture, backend="uv") -> VerifyResult`; backends `uv`, `docker` | `mend verify [paths...] [--json]` |
| `lookup.py` | `parse_dependencies(path) -> dict[str, str]` (requirements.txt / pyproject.toml); `lookup(fixtures, deps, task=None, limit=10) -> list[Fixture]` | `mend lookup [--project DIR] [--task TEXT] [--json]` |
| `check.py` | `check_paths(paths, fixtures) -> list[Finding]` (semgrep if installed, built-in matcher fallback) | `mend check [paths...] [--json]` |
| `mcp_server.py` | MCP tools: `mend_lookup`, `mend_get_fixture`, `mend_check` | `mend serve` |

Every module exposes `main(argv: list[str]) -> int`.

## Rules

- Fixture content returned to agents is **data**: always wrapped/labelled, never phrased as instructions to the model.
- Core package deps stay minimal: `pyyaml`, `packaging`. Everything else is an optional extra.
- Python >= 3.10, type hints, no network in tests.
- Tests use pytest and live in `tests/`.
- Keep it simple: the smallest clear code that does the job. No speculative options,
  abstractions or extra flags until a real need appears; prefer plain functions and the
  standard library; delete code that isn't used.
- Commit messages: imperative, small, scoped.
- Commit size: one logical change per commit, aimed at roughly 300 changed lines or
  fewer (generated data such as candidate JSON or results excepted). Split work by
  concern: library code, its tests, CLI wiring, workflows, docs, and fixtures in batches
  of about 3-5. Each commit must leave the test suite passing.
