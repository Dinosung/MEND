"""Pilot arms. Each arm only changes files in the task workdir before the agent starts.

A0  no help. The project CLAUDE.md is the neutral base (every arm has it).
A1  one fact line appended to CLAUDE.md: "This project uses numpy 2.5.3."
A4  MEND hooks via a project-local .claude/settings.json:
      SessionStart -> `mend hook session-start` (inform; additionalContext)
      PostToolUse (Write|Edit|MultiEdit) -> `mend hook post-tool-use` (exit 2 = findings)
    Both go through bench/v2/hook_wrapper.py, which logs every call so the runner can
    count hook fires and blocks.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from bench.common import REPO_ROOT
from bench.v2.taskgen import TaskSpec, dep_name, dep_version

ARMS = ("A0", "A1", "A4")
WRAPPER = Path(__file__).resolve().parent / "hook_wrapper.py"


def versions_line(deps: list[str]) -> str:
    parts = [f"{dep_name(d)} {dep_version(d)}" for d in deps if dep_version(d)]
    return f"This project uses {', '.join(parts)}."


def hook_settings(hook_log: Path, catalog: Path, python: str = sys.executable,
                  wrapper: Path = WRAPPER, src: Path = REPO_ROOT / "src") -> dict:
    def cmd(event: str) -> dict:
        return {"type": "command", "timeout": 60,
                "command": f'"{python}" "{wrapper}" --log "{hook_log}" --catalog "{catalog}" '
                           f'--src "{src}" {event}'}
    return {"hooks": {
        "SessionStart": [{"matcher": "startup", "hooks": [cmd("session-start")]}],
        "PostToolUse": [{"matcher": "Write|Edit|MultiEdit", "hooks": [cmd("post-tool-use")]}],
    }}


def public_catalog(fixtures_root: Path, dest: Path) -> Path:
    """Copy of the catalog without check/ dirs, so A4's MEND data never exposes the
    hidden tests (fixture.yaml, bad/, fixed/ and rule.yml are what MEND serves anyway)."""
    if not dest.exists():
        shutil.copytree(fixtures_root, dest, ignore=shutil.ignore_patterns("check", "__pycache__"))
    return dest


def apply_arm(arm: str, workdir: Path, spec: TaskSpec, hook_log: Path, catalog: Path) -> None:
    if arm == "A0":
        return
    if arm == "A1":
        md = workdir / "CLAUDE.md"
        md.write_text(md.read_text(encoding="utf-8") + "\n" + versions_line(spec.deps) + "\n",
                      encoding="utf-8")
        return
    if arm == "A4":
        (workdir / ".claude").mkdir(exist_ok=True)
        (workdir / ".claude" / "settings.json").write_text(
            json.dumps(hook_settings(hook_log, catalog), indent=2) + "\n", encoding="utf-8")
        return
    raise ValueError(f"unknown arm {arm!r}; expected one of {ARMS}")


def read_hook_log(path: Path) -> dict:
    """Summarize hook_wrapper's JSONL log for one trial."""
    calls = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                calls.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    start = [c for c in calls if c.get("event") == "session-start"]
    post = [c for c in calls if c.get("event") == "post-tool-use"]
    return {
        "session_start_calls": len(start),
        "session_start_injected": any(c.get("stdout_chars", 0) > 0 and c.get("exit_code") == 0 for c in start),
        "post_tool_use_calls": len(post),
        "post_tool_use_blocks": sum(1 for c in post if c.get("exit_code") == 2),
        "hook_errors": sum(1 for c in calls if c.get("exit_code") not in (0, 2)),
    }
