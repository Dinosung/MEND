#!/bin/sh
# Launcher for the MEND Claude Code plugin. Runs `mend <args>` from the plugin's own
# source tree (src/) and catalog (fixtures/) without needing `pip install`.
#
#   1. a python3/python >= 3.10 that already has pyyaml + packaging (+ mcp for `serve`)
#      -> PYTHONPATH="$ROOT/src" python -m mend.cli <args>      (fast, offline)
#   2. else `uv` -> uv run --no-project --with pyyaml --with packaging [...] python -m mend.cli
#      (downloads two small wheels once into uv's cache)
#   3. else: for `hook ...` exit 0 silently (a hook must never break the session);
#      for anything else print why and exit 1.
#
# In hook mode only exit codes 0 and 2 are passed through (2 = "show stderr to Claude"
# for PostToolUse); anything else becomes 0.

ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export MEND_FIXTURES_DIR="${MEND_FIXTURES_DIR:-$ROOT/fixtures}"

HOOK=0
[ "$1" = "hook" ] && HOOK=1

MODS="yaml, packaging"
WITH="--with pyyaml>=6 --with packaging>=23"
if [ "$1" = "serve" ]; then
  MODS="$MODS, mcp"
  WITH="$WITH --with mcp>=1.2"
fi

PY=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1 &&
     "$cand" -c "import sys; assert sys.version_info >= (3, 10); import $MODS" >/dev/null 2>&1; then
    PY="$cand"
    break
  fi
done

run() {
  if [ -n "$PY" ]; then
    "$PY" -m mend.cli "$@"
  elif command -v uv >/dev/null 2>&1; then
    # shellcheck disable=SC2086
    uv run --quiet --no-project --python ">=3.10" $WITH python -m mend.cli "$@"
  else
    [ -n "$MEND_DEBUG" ] || [ "$HOOK" = 0 ] &&
      echo "mend: needs python>=3.10 with modules ($MODS) importable, or uv on PATH" >&2
    return 127
  fi
}

if [ "$HOOK" = 1 ]; then
  run "$@"
  rc=$?
  [ "$rc" -eq 2 ] && exit 2
  exit 0
fi
run "$@"
