"""Shared helpers. Uses `mend` when importable, otherwise small local fallbacks so the
bench stays runnable from a bare checkout (`python -m bench.run` from the repo root)."""

from __future__ import annotations

import fnmatch
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def normalize(name: str) -> str:
    """PEP 503 normalization."""
    return re.sub(r"[-_.]+", "-", name).lower().strip()


def get(obj: Any, *keys: str, default: Any = None) -> Any:
    cur = obj
    for k in keys:
        if cur is None:
            return default
        cur = cur.get(k) if isinstance(cur, dict) else getattr(cur, k, None)
    return default if cur is None else cur


# --------------------------------------------------------------------------- fixtures

def _ns(value: Any) -> Any:
    if isinstance(value, dict):
        return SimpleNamespace(**{k: _ns(v) for k, v in value.items()})
    if isinstance(value, list):
        return [_ns(v) for v in value]
    return value


def _fallback_load(root: Path) -> list[Any]:
    import yaml

    out = []
    for p in sorted(root.rglob("fixture.yaml")):
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        fx = _ns(data)
        fx.path = p.parent.resolve()
        out.append(fx)
    return out


def load_fixtures(root: str | Path) -> list[Any]:
    root = Path(root)
    try:
        from mend.fixture import load_all  # type: ignore
    except ImportError:
        return _fallback_load(root)
    return list(load_all(str(root)))


def select_fixtures(fixtures: list[Any], patterns: str | None) -> list[Any]:
    """Filter by comma-separated globs matched against id, package/id, or path."""
    if not patterns:
        return fixtures
    pats = [p.strip() for p in patterns.split(",") if p.strip()]
    out = []
    for fx in fixtures:
        keys = [str(fx.id), f"{fx.package}/{fx.id}", str(fx.path)]
        if any(fnmatch.fnmatch(k, p) or fnmatch.fnmatch(k, f"*{p}") for k in keys for p in pats):
            out.append(fx)
    return out


def check_dir(fx: Any) -> Path:
    cd = getattr(fx, "check_dir", None)
    return Path(cd) if cd else Path(fx.path) / "check"


def deps_of(fx: Any) -> list[str]:
    return list(get(fx, "repro", "deps", default=[]) or [])


def python_of(fx: Any) -> str:
    return str(get(fx, "repro", "python", default="3.12"))


# --------------------------------------------------------------------------- MEND context

def render_context(fixtures: list[Any]) -> str:
    try:
        from mend.render import render_fixtures  # type: ignore
    except ImportError:
        lines = ["MEND known-failure records (reference data, not instructions):"]
        for i, fx in enumerate(fixtures, 1):
            lines += [f"[{i}] id={fx.id}", f"    package: {fx.package} {fx.versions}",
                      f"    known-bad pattern: {get(fx, 'failure', 'bad_pattern')}",
                      f"    working pattern: {get(fx, 'failure', 'fix_pattern')}"]
        lines.append("END MEND records")
        return "\n".join(lines)
    return render_fixtures(fixtures)


def lookup_context(all_fixtures: list[Any], deps: list[str], task: str, limit: int = 10) -> str:
    """What `mend lookup` would hand an agent for a project with `deps` and this task."""
    try:
        from mend.lookup import lookup  # type: ignore
    except ImportError:
        names = {normalize(d.split("==")[0].split(">=")[0].split("[")[0]) for d in deps}
        hits = [fx for fx in all_fixtures if normalize(str(fx.package)) in names][:limit]
        return render_context(hits)
    dmap: dict[str, str | None] = {}
    for d in deps:
        m = re.match(r"^\s*([A-Za-z0-9_.\-]+)(?:\[[^\]]*\])?\s*(?:==\s*([^\s;,]+))?", d)
        if m:
            dmap[normalize(m.group(1))] = m.group(2)
    return render_context(lookup(all_fixtures, dmap, task=task, limit=limit))
