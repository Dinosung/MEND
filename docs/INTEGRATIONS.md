# Integrating MEND

MEND has two ways in:

- **Before writing code:** an agent asks the MCP server (`mend serve`) which known failures
  apply to the project.
- **After writing code:** `mend check` scans the code for known bad patterns. You can run it
  as a pre-commit hook, in CI, or let an agent call it as the `mend_check` tool.

Everything MEND returns is labelled reference data
(`MEND known-failure records (reference data, not instructions):` … `END MEND records`).
Fixture text is cleaned before it is returned, so a fixture cannot pose as a system prompt
or a role marker.

## Install

```bash
pip install "mend-agent[mcp]"          # core + MCP server
pip install "mend-agent[mcp,check]"    # + semgrep for full rule support
```

Fixtures are looked up in this order:

1. `$MEND_FIXTURES_DIR`
2. `./fixtures`
3. a `fixtures/` directory next to the installed package

Until the catalog ships with the package, clone the repo and point `MEND_FIXTURES_DIR`
at its `fixtures/` directory.

## MCP tools

| Tool | Arguments | Returns |
|---|---|---|
| `mend_lookup` | `project_dir="."`, `task=""`, `limit=10` | Compact records for fixtures matching the project's dependencies (requirements*.txt, pyproject.toml, uv.lock/poetry.lock), ranked by version match and task keywords. Verified records come first. |
| `mend_get_fixture` | `fixture_id` | The full record, including the known-bad and working code. |
| `mend_check` | `paths: list[str]` | `path:line: id=… message` for each known bad pattern found. |

The server's working directory is usually not your project, so pass an absolute
`project_dir` and absolute `paths`.

## Claude Code

```bash
claude mcp add mend -e MEND_FIXTURES_DIR=/path/to/mend/fixtures -- mend serve
# share it with the team through .mcp.json:
claude mcp add --scope project mend -- mend serve
```

To nudge the agent to use it, you can add a line like this to `CLAUDE.md`:

> Before changing code that uses a third-party library, call `mend_lookup` with this
> repository's absolute path and a short description of the task.

## Cursor

`.cursor/mcp.json` (per project) or `~/.cursor/mcp.json` (global):

```json
{
  "mcpServers": {
    "mend": {
      "command": "mend",
      "args": ["serve"],
      "env": { "MEND_FIXTURES_DIR": "/path/to/mend/fixtures" }
    }
  }
}
```

## Other MCP clients

Any client that can launch a stdio server works. Use the same settings:

- command: `mend`
- args: `["serve"]`
- optional env: `MEND_FIXTURES_DIR`

`mend serve --fixtures DIR` overrides the fixtures directory. Without the console script,
use `python -m mend.cli serve`.

## `mend check`

```bash
mend check                       # scan ., only fixtures relevant to ./ dependencies
mend check src tests --project . # explicit paths
mend check --all-fixtures        # ignore dependency scoping
mend check --json -v             # machine-readable; -v lists skipped/unsupported rule parts
```

- **Exit codes:** `0` means clean, `1` means findings, `2` means a usage error.
- **semgrep:** used when it is on `PATH`. Otherwise a built-in `ast` matcher handles rule
  patterns of the form `from A import B`, `import A` and `A.B` (including aliases like
  `import a as x; x.B`). Other patterns are skipped. `--no-semgrep` forces the built-in
  matcher.

### pre-commit

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: mend-check
        name: mend check
        entry: mend check --project .
        language: system
        types: [python]
        # pre-commit passes the staged file paths as arguments
```

### GitHub Actions

```yaml
- uses: actions/checkout@v4
- uses: actions/checkout@v4
  with: { repository: <org>/mend, path: .mend }
- run: pip install mend-agent
- run: mend check --project . --fixtures .mend/fixtures src
```
