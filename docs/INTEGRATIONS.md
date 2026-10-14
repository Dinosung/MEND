# Integrating MEND

MEND reaches an agent through three channels, listed in order of preference:

1. **Claude Code plugin (recommended).** Hooks run on every session and every edit, so the
   agent never has to decide to call a tool:
   - A `SessionStart` hook adds a few lines of facts about verified failures that match the
     project's dependency versions.
   - A `PostToolUse` hook checks each edited Python file and sends any matches back to the
     model.
   - The bundled MCP server provides the full record behind each id.
2. **Deterministic checks for every agent and every human.** `mend check` runs as a
   pre-commit hook or in CI.
3. **MCP server only (`mend serve`)** for Cursor and other MCP clients. The agent has to choose
   to call it, and agents often don't. See
   [docs/STRATEGY.md](STRATEGY.md#deliver-through-hooks-and-ci-not-an-optional-tool-call).

Everything MEND returns is labelled reference data
(`MEND known-failure records (reference data, not instructions):` … `END MEND records`).
Fixture text is cleaned before it is returned, so a fixture cannot pose as a system prompt
or a role marker. Hook output follows the same rules and is phrased as facts ("In numpy>=2.4,
X results in Y; the working form is Z"), never as instructions.

## Claude Code plugin (recommended)

```text
/plugin marketplace add Dinosung/MEND
/plugin install mend@mend
```

On Claude Code 2.1.275 or later, `/plugin install mend --marketplace Dinosung/MEND` does both in
one step. In a shell, the equivalent is `claude plugin marketplace add Dinosung/MEND` followed by
`claude plugin install mend@mend`. To share the plugin with a team, commit
`"enabledPlugins": {"mend@mend": true}` and an `extraKnownMarketplaces` entry for
`Dinosung/MEND` to `.claude/settings.json`.

To develop or try it from a checkout without installing, run
`claude --plugin-dir /path/to/MEND`.

### What it does

| Hook | When | Output |
|---|---|---|
| `SessionStart` (no matcher: startup, resume, clear, compact) | Each session start, and again after `/clear` or compaction | JSON `hookSpecificOutput.additionalContext`: a header, up to 8 fact lines, and one pointer line. Prints nothing if no fixture is relevant. |
| `PostToolUse`, matcher `Edit\|Write\|MultiEdit` | After Claude edits a file | For a `.py` file with known bad patterns, findings go to stderr with **exit 2**, and Claude Code shows that stderr to the model next to the tool result. Otherwise it exits 0 with no output. |

Both hooks are `mend hook session-start` and `mend hook post-tool-use`. They read the hook JSON
from stdin. `cwd` locates the project, and `tool_input.file_path` names the edited file.

**Which fixtures apply.** Only `status: verified` fixtures are used. A fixture applies when
its `package` is a project dependency. The project version is taken from the first source
that has one:

1. an exact pin in `requirements*.txt` or `pyproject.toml`, or a `uv.lock`/`poetry.lock`
   entry
2. the version installed in the project's `.venv/`, `venv/` or `env/`

After that:

- If the version is outside the fixture's range, the fixture is dropped. This avoids false
  positives on old-version projects.
- If no version is known but the declared range implies the fixture's range (`pydantic>=2.5`
  implies `>=2.0`), the line reads `In pydantic>=2.0 (project requires pydantic>=2.5)`.
- If no version is known and the declared range only overlaps the fixture's range, the line
  reads `If numpy>=2.4 (project pins no numpy version)`.
- If the declared range excludes the fixture's range (`numpy<2`), the fixture is dropped.

Newer breakages are listed first, because a model is least likely to know about them.

**It never breaks a session.** Malformed input, a missing catalog, a missing Python, or any
exception all exit 0 silently. Set `MEND_DEBUG=1` to see tracebacks on stderr. In the
measured case, `session-start` takes about 0.2 s and `post-tool-use` about 0.3 s. Each hook
has a 30 s timeout.

### How the plugin runs MEND without PyPI

The marketplace entry's `source` is `"./"`: the repository root *is* the plugin. Claude Code
copies the whole repo into its plugin cache, so the plugin carries `src/mend/` and the
`fixtures/` catalog with it:

```
.claude-plugin/marketplace.json   # marketplace "mend", one plugin "mend", source "./"
.claude-plugin/plugin.json        # manifest; hooks -> ./plugin/hooks.json, inline MCP server
plugin/hooks.json                 # SessionStart + PostToolUse command hooks
plugin/run-mend.sh                # launcher used by hooks and the MCP server
src/mend/ fixtures/               # code and catalog, used in place
```

We keep `plugin/` separate from the default `hooks/` and `.mcp.json` locations so that people
working on this repo don't get a project-level MCP server or hooks by accident.

`plugin/run-mend.sh` sets `PYTHONPATH=${CLAUDE_PLUGIN_ROOT}/src` and
`MEND_FIXTURES_DIR=${CLAUDE_PLUGIN_ROOT}/fixtures`, then runs `python -m mend.cli <args>` with
the first option that works:

1. `python3` or `python`, version 3.10 or later, that can already import `yaml` and
   `packaging` (and `mcp` for `serve`). This is fast and works offline, and most machines with
   Python already have it.
2. `uv run --no-project --with pyyaml --with packaging [--with mcp] python -m mend.cli ...`. The
   first run downloads a few small wheels into uv's cache.
3. Nothing. In hook mode the launcher exits 0 silently; for `serve` it prints what is
   missing.

We chose this over `uvx --from "${CLAUDE_PLUGIN_ROOT}" mend` for three reasons. `uvx --from`
requires uv on every machine. It builds a wheel of the whole plugin directory with hatchling
on first use (network, then a rebuild whenever the cached copy changes). And it would add
uv's resolution time to every hook call. In hook mode the launcher passes through only exit
codes 0 and 2, so a crash can never surface as a hook error.

The plugin's `version` is intentionally unset. Claude Code then uses the git commit as the
version, so `claude plugin update mend@mend`, or the marketplace's auto-update if you turn it
on, picks up new fixtures without a release. Because of this, `claude plugin validate .`
reports one warning, `No version specified`.

### Options

| Env var | Effect |
|---|---|
| `MEND_DEBUG=1` | Print hook errors and tracebacks on stderr. |
| `MEND_FIXTURES_DIR` | Use another catalog, such as your own fork's fixtures. |
| `MEND_HOOK_SEMGREP=1` | Use semgrep (if installed) in the post-edit check, not the fast built-in matcher. |

## Install (CLI and MCP server)

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

## Claude Code: MCP server only

If you don't want hooks, register just the MCP server:

```bash
claude mcp add mend -e MEND_FIXTURES_DIR=/path/to/mend/fixtures -- mend serve
# share it with the team through .mcp.json:
claude mcp add --scope project mend -- mend serve
```

The agent has to choose to call it. A line like this in `CLAUDE.md` helps:

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
