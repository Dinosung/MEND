"""Claude Code hook handlers: `mend hook session-start` and `mend hook post-tool-use`.

Both read the hook's JSON input on stdin (https://code.claude.com/docs/en/hooks).

* session-start: prints SessionStart `additionalContext` with a few facts about verified
  fixtures that apply to the project's dependencies; prints nothing if none apply.
* post-tool-use: scans the edited .py file; on findings writes them to stderr and exits
  2, which Claude Code shows to the model.

A hook must never break a session: any error exits 0 (MEND_DEBUG=1 prints it).
Fixture text is untrusted and goes through `render.sanitize`; output states facts.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

from mend.render import get, sanitize

MAX_FACTS = 8
MAX_FINDINGS = 10
FILE_TOOLS = {"Write", "Edit", "MultiEdit"}


def fixtures_dir() -> Path:
    """$MEND_FIXTURES_DIR, else the catalog shipped with MEND (never the user's ./fixtures)."""
    env = os.environ.get("MEND_FIXTURES_DIR")
    return Path(env) if env else Path(__file__).resolve().parents[2] / "fixtures"


def relevant(project: Path) -> list[tuple[Any, str | None]]:
    """(fixture, project version or None) for verified fixtures matching the project."""
    from mend.fixture import load_all
    from mend.lookup import lookup, normalize, parse_dependencies

    deps = parse_dependencies(project)
    root = fixtures_dir()
    if not deps or not root.is_dir():
        return []
    verified = [f for f in load_all(str(root)) if get(f, "status") == "verified"]
    return [(fx, deps.get(normalize(str(get(fx, "package")))))
            for fx in lookup(verified, deps, limit=len(verified))]


def _code(text: Any) -> str:
    s = sanitize(text, max_len=100).replace("`", "'")
    return f"`{s}`" if s else ""


def describe(fx: Any, version: str | None) -> str:
    """'In numpy>=2.4 (project: 2.4.1), `np.trapz(...)` results in "...";
    the working form is `np.trapezoid(...)`. [mend:id]'"""
    pkg = sanitize(get(fx, "package"), max_len=60)
    spec = sanitize(get(fx, "versions"), max_len=40)
    where = (f"In {pkg}{spec} (project: {sanitize(version, max_len=40)})" if version
             else f"If {pkg}{spec} (version not pinned)")
    symptom = str(get(fx, "failure", "symptom") or "").strip().splitlines()
    symptom = sanitize(symptom[0] if symptom else "", max_len=90).replace('"', "'")
    s = f"{where}, {_code(get(fx, 'failure', 'bad_pattern'))} "
    s += f'results in "{symptom}"' if symptom else "fails"
    fix = _code(get(fx, "failure", "fix_pattern"))
    if fix:
        s += f"; the working form is {fix}"
    return s + f". [mend:{sanitize(get(fx, 'id'), max_len=100)}]"


def session_start(data: dict[str, Any]) -> int:
    matches = relevant(Path(data.get("cwd") or os.getcwd()))
    if not matches:
        return 0
    lines = ["MEND verified known-failure facts for this project's dependencies:"]
    lines += ["- " + describe(fx, v) for fx, v in matches[:MAX_FACTS]]
    lines.append("Full records: MEND MCP tool mend_get_fixture <id>.")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                             "additionalContext": "\n".join(lines)}}))
    return 0


def post_tool_use(data: dict[str, Any]) -> int:
    from mend.check import check_paths

    if data.get("tool_name") not in FILE_TOOLS:
        return 0
    cwd = Path(data.get("cwd") or os.getcwd())
    path = (data.get("tool_input") or {}).get("file_path")
    if not path or not path.endswith(".py"):
        return 0
    path = cwd / path  # an absolute file_path stays absolute
    if not path.is_file():
        return 0
    matches = {get(fx, "id"): (fx, v) for fx, v in relevant(cwd)}
    findings = [f for f in check_paths([path], [fx for fx, _ in matches.values()],
                                       use_semgrep=False) if f.fixture_id in matches]
    if not findings:
        return 0
    lines = [f"MEND: the edited file matches verified known failures for this project's "
             f"dependency versions:"]
    lines += [f"{f.path}:{f.line}: " + describe(*matches[f.fixture_id])
              for f in findings[:MAX_FINDINGS]]
    print("\n".join(lines), file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    handlers = {"session-start": session_start, "post-tool-use": post_tool_use}
    if not argv or argv[0] not in handlers:
        print("usage: mend hook {session-start|post-tool-use} < hook-input.json",
              file=sys.stderr)
        return 0 if argv[:1] in (["-h"], ["--help"]) else 2
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        if not isinstance(data, dict):
            return 0
        return handlers[argv[0]](data)
    except Exception:  # noqa: BLE001 - a hook must never break the session
        if os.environ.get("MEND_DEBUG"):
            traceback.print_exc()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
