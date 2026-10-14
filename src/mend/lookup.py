"""Find fixtures relevant to a project's dependencies and (optionally) a task."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from mend.render import fixture_summary, get, render_fixtures

try:  # Python >= 3.11
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:
        tomllib = None  # type: ignore[assignment]


def normalize(name: str) -> str:
    """PEP 503 name normalization."""
    return re.sub(r"[-_.]+", "-", name).lower().strip()


def _pinned_version(spec: str) -> str | None:
    """Return the version if a specifier is an exact pin (==X / ===X), else None."""
    try:
        ss = SpecifierSet(spec)
    except InvalidSpecifier:
        return None
    specs = list(ss)
    if len(specs) == 1 and specs[0].operator in ("==", "===") and "*" not in specs[0].version:
        return specs[0].version
    return None


def _add_req(deps: dict[str, str | None], line: str) -> None:
    line = line.split(" #", 1)[0].strip()
    if not line or line.startswith(("#", "-", "git+", "http:", "https:", "file:", ".")):
        return
    try:
        req = Requirement(line)
    except InvalidRequirement:
        return
    name = normalize(req.name)
    ver = _pinned_version(str(req.specifier)) if req.specifier else None
    if ver is not None or name not in deps:
        deps[name] = ver if ver is not None else deps.get(name)


def _parse_requirements(path: Path, deps: dict[str, str | None], seen: set[Path]) -> None:
    path = path.resolve()
    if path in seen or not path.is_file():
        return
    seen.add(path)
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        m = re.match(r"^(-r|--requirement|-c|--constraint)\s+(\S+)", line)
        if m:
            _parse_requirements(path.parent / m.group(2), deps, seen)
            continue
        _add_req(deps, line)


def _poetry_dep(deps: dict[str, str | None], name: str, value: Any) -> None:
    if normalize(name) == "python":
        return
    spec = value if isinstance(value, str) else (value.get("version") if isinstance(value, dict) else None)
    ver = None
    if isinstance(spec, str) and spec and spec[0].isdigit():  # poetry bare "1.2.3" == exact pin
        ver = spec
    elif isinstance(spec, str):
        ver = _pinned_version(spec)
    n = normalize(name)
    if ver is not None or n not in deps:
        deps[n] = ver if ver is not None else deps.get(n)


def _parse_pyproject(path: Path, deps: dict[str, str | None]) -> None:
    if tomllib is None or not path.is_file():
        return
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        return
    project = data.get("project", {}) or {}
    for line in project.get("dependencies", []) or []:
        _add_req(deps, str(line))
    for group in (project.get("optional-dependencies", {}) or {}).values():
        for line in group or []:
            _add_req(deps, str(line))
    for group in (data.get("dependency-groups", {}) or {}).values():
        for line in group or []:
            if isinstance(line, str):
                _add_req(deps, line)
    poetry = (data.get("tool", {}) or {}).get("poetry", {}) or {}
    for key in ("dependencies", "dev-dependencies"):
        for name, val in (poetry.get(key, {}) or {}).items():
            _poetry_dep(deps, name, val)
    for group in (poetry.get("group", {}) or {}).values():
        for name, val in ((group or {}).get("dependencies", {}) or {}).items():
            _poetry_dep(deps, name, val)


def _parse_lock(path: Path) -> dict[str, str]:
    """uv.lock and poetry.lock both use [[package]] name=/version= tables."""
    if tomllib is None or not path.is_file():
        return {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        return {}
    out: dict[str, str] = {}
    for pkg in data.get("package", []) or []:
        name, ver = pkg.get("name"), pkg.get("version")
        if name and ver:
            out[normalize(str(name))] = str(ver)
    return out


def parse_dependencies(project_dir: str | Path = ".") -> dict[str, str | None]:
    """Map normalized package name -> resolved/pinned version (or None if unknown).

    Reads requirements*.txt, pyproject.toml (PEP 621, dependency-groups, Poetry) and,
    when present, uv.lock / poetry.lock for resolved versions. Lock files only
    supply versions for packages already declared directly (to avoid matching on
    every transitive dependency) -- unless nothing is declared at all.
    """
    root = Path(project_dir)
    if root.is_file():
        root = root.parent
    deps: dict[str, str | None] = {}
    seen: set[Path] = set()
    for req in sorted(root.glob("requirements*.txt")) + sorted(root.glob("requirements/*.txt")):
        _parse_requirements(req, deps, seen)
    _parse_pyproject(root / "pyproject.toml", deps)
    locked: dict[str, str] = {}
    for lock in ("poetry.lock", "uv.lock"):
        locked.update(_parse_lock(root / lock))
    if locked:
        if not deps:
            deps = dict(locked)
        else:
            for name in deps:
                if name in locked:
                    deps[name] = locked[name]
    return deps


# --------------------------------------------------------------------------- ranking

_WORD_RE = re.compile(r"[a-z0-9]+")
_STOP = {"the", "a", "an", "to", "of", "in", "for", "and", "or", "with", "on", "is",
         "use", "using", "from", "my", "i", "it", "this", "that", "be", "add", "make"}


def _words(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOP and len(w) > 1}


def version_match(fx: Any, version: str | None) -> bool | None:
    """True/False if the version is known, None if unknown or spec unparsable."""
    if version is None:
        return None
    try:
        spec = SpecifierSet(str(get(fx, "versions", default="") or ""))
        return Version(version) in spec  # prereleases follow default semantics
    except (InvalidSpecifier, InvalidVersion):
        return None


def score(fx: Any, deps: dict[str, str | None], task: str | None = None) -> float | None:
    """Relevance score, or None if the fixture is not relevant."""
    pkg = normalize(str(get(fx, "package", default="")))
    if pkg not in deps:
        return None
    vm = version_match(fx, deps[pkg])
    if vm is False:
        return None
    s = 10.0 if vm else 5.0
    if task:
        tw = _words(task)
        text = " ".join([str(get(fx, "title", default="")), str(get(fx, "summary", default="")),
                         " ".join(map(str, get(fx, "tags", default=[]) or [])),
                         str(get(fx, "package", default=""))])
        s += 2.0 * len(tw & _words(text))
    if str(get(fx, "status", default="draft")) == "verified":
        s += 100.0  # verified always ranks before drafts
    return s


def lookup(fixtures: list[Any], deps: dict[str, str | None], task: str | None = None,
           limit: int = 10) -> list[Any]:
    deps = {normalize(k): v for k, v in deps.items()}
    scored = []
    for fx in fixtures:
        sc = score(fx, deps, task)
        if sc is not None:
            scored.append((sc, str(get(fx, "id", default="")), fx))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [fx for _, _, fx in scored[: max(0, limit)]]


# --------------------------------------------------------------------------- fixtures root

def fixtures_root(explicit: str | None = None) -> Path:
    """MEND_FIXTURES_DIR, else ./fixtures, else a fixtures dir near the package."""
    import os

    if explicit:
        return Path(explicit)
    env = os.environ.get("MEND_FIXTURES_DIR")
    if env:
        return Path(env)
    cwd = Path("fixtures")
    if cwd.is_dir():
        return cwd
    here = Path(__file__).resolve().parent
    for cand in (here / "fixtures", here.parent / "fixtures", here.parent.parent / "fixtures"):
        if cand.is_dir():
            return cand
    return cwd


def load_fixtures(root: str | Path | None = None) -> list[Any]:
    from mend.fixture import load_all

    return load_all(str(fixtures_root(str(root) if root else None)))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mend lookup", description=__doc__)
    ap.add_argument("--project", default=".", help="project directory (default: .)")
    ap.add_argument("--task", default=None, help="free-text description of the task")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--fixtures", default=None, help="fixtures root (default: $MEND_FIXTURES_DIR or ./fixtures)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    deps = parse_dependencies(args.project)
    results = lookup(load_fixtures(args.fixtures), deps, task=args.task, limit=args.limit)
    if args.json:
        print(json.dumps([fixture_summary(f) for f in results], indent=2))
    else:
        print(render_fixtures(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
