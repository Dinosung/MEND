"""`mend` command-line entry point.

Each subcommand delegates to `<module>.main(argv) -> int`. Modules are imported
lazily so optional dependencies (mcp, semgrep) are only needed when used.
"""

from __future__ import annotations

import importlib
import sys

COMMANDS = {
    "list": ("mend.fixture", "List fixtures in the catalog"),
    "verify": ("mend.verify", "Verify fixtures: bad must fail, fixed must pass"),
    "lookup": ("mend.lookup", "Find fixtures relevant to a project's dependencies/task"),
    "check": ("mend.check", "Scan code for known bad patterns"),
    "serve": ("mend.mcp_server", "Run the MEND MCP server (stdio)"),
}


def _usage() -> str:
    lines = ["usage: mend <command> [args]", "", "commands:"]
    lines += [f"  {name:<8} {desc}" for name, (_, desc) in COMMANDS.items()]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {"-h", "--help"}:
        print(_usage())
        return 0
    if argv[0] in {"-V", "--version"}:
        from mend import __version__

        print(__version__)
        return 0
    name, rest = argv[0], argv[1:]
    if name not in COMMANDS:
        print(f"mend: unknown command {name!r}\n\n{_usage()}", file=sys.stderr)
        return 2
    module = importlib.import_module(COMMANDS[name][0])
    return int(module.main(rest) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
