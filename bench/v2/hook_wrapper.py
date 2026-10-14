"""Claude Code hook shim for arm A4: runs `python -m mend.cli hook <event>` and logs the call.

    hook_wrapper.py --log LOG --catalog DIR --src DIR (session-start|post-tool-use)

stdin (the hook JSON), stdout, stderr and the exit code pass through unchanged, except
that a missing `mend hook` command (unknown-command exit 2) is turned into exit 1 so
Claude Code never shows the agent a bogus "finding". One JSON line per call goes to LOG.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--src", required=True)
    ap.add_argument("event", choices=["session-start", "post-tool-use"])
    args = ap.parse_args(argv)
    payload = sys.stdin.read()
    env = dict(os.environ, PYTHONPATH=args.src, MEND_FIXTURES_DIR=args.catalog)
    t0 = time.monotonic()
    proc = subprocess.run([sys.executable, "-m", "mend.cli", "hook", args.event], input=payload,
                          capture_output=True, text=True, env=env, timeout=55)
    code = proc.returncode
    if code == 2 and "unknown command" in proc.stderr:
        code = 1
    try:
        tool = json.loads(payload)
    except json.JSONDecodeError:
        tool = {}
    with open(args.log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "event": args.event, "exit_code": code, "seconds": round(time.monotonic() - t0, 2),
            "tool_name": tool.get("tool_name"),
            "file_path": (tool.get("tool_input") or {}).get("file_path"),
            "stdout_chars": len(proc.stdout), "stderr": proc.stderr[-2000:],
        }) + "\n")
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
