"""Claude Code hook handlers: `mend hook session-start` and `mend hook post-tool-use`.

Both read the hook's JSON input from stdin (see https://code.claude.com/docs/en/hooks).

* session-start: prints `{"hookSpecificOutput": {"hookEventName": "SessionStart",
  "additionalContext": ...}}` with a few lines of *facts* about verified fixtures that
  match the project's dependency versions. Prints nothing when nothing is relevant.
* post-tool-use: scans the edited .py file. On findings it writes them to stderr and
  exits 2, which Claude Code shows to the model next to the tool result.

Hooks must never break a session: every unexpected error exits 0 silently
(set MEND_DEBUG=1 to see tracebacks on stderr). Fixture text is untrusted data and
goes through `render.sanitize`; output is phrased as facts, never as instructions.
"""

from __future__ import annotations

import json
import os
import re
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from mend.render import get, sanitize

MAX_FACTS = 8            # fact lines in SessionStart context (plus header/footer)
MAX_FINDINGS = 10        # finding lines on stderr for PostToolUse
DEP_FILES = ("pyproject.toml", "uv.lock", "poetry.lock", "setup.cfg")
FILE_TOOLS = {"Write", "Edit", "MultiEdit"}


def _debug(msg: str) -> None:
    if os.environ.get("MEND_DEBUG"):
        print(f"mend hook: {msg}", file=sys.stderr)


# --------------------------------------------------------------------------- inputs

def read_input(stream: TextIO) -> dict[str, Any]:
    raw = stream.read()
    data = json.loads(raw) if raw.strip() else {}
    if not isinstance(data, dict):
        raise ValueError("hook input is not a JSON object")
    return data


def fixtures_dir() -> Path | None:
    """$MEND_FIXTURES_DIR, else the repo's fixtures/ next to src/. Never ./fixtures:
    the hook's cwd is the user's project, whose own `fixtures/` is unrelated."""
    env = os.environ.get("MEND_FIXTURES_DIR")
    if env:
        return Path(env)
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if root and (Path(root) / "fixtures").is_dir():
        return Path(root) / "fixtures"
    here = Path(__file__).resolve().parent
    for cand in (here / "fixtures", here.parent.parent / "fixtures"):
        if cand.is_dir():
            return cand
    return None


def _has_dep_files(d: Path) -> bool:
    if any((d / f).is_file() for f in DEP_FILES):
        return True
    return any(d.glob("requirements*.txt"))


def find_project_root(start: Path, stop: Path | None = None) -> Path:
    """Nearest directory at/above `start` with dependency files. Stops at a `.git`
    directory, at `stop`, or at the filesystem root; falls back to `start`."""
    start = start if start.is_dir() else start.parent
    d = start
    while True:
        if _has_dep_files(d):
            return d
        if (d / ".git").exists() or (stop is not None and d == stop) or d.parent == d:
            return start
        d = d.parent


def _project_dir(data: dict[str, Any]) -> Path:
    cwd = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return find_project_root(Path(str(cwd)).resolve())


# --------------------------------------------------------------------------- versions

def _venv_versions(root: Path) -> dict[str, str]:
    """name -> version from *.dist-info in the project's virtualenv, if one exists."""
    from mend.lookup import normalize

    out: dict[str, str] = {}
    venvs = [root / n for n in (".venv", "venv", "env")]
    for venv in venvs:
        if not (venv / "pyvenv.cfg").is_file():
            continue
        for sp in list(venv.glob("lib/python*/site-packages")) + [venv / "Lib" / "site-packages"]:
            if not sp.is_dir():
                continue
            for di in sp.glob("*.dist-info"):
                name, _, ver = di.name[: -len(".dist-info")].rpartition("-")
                if name and ver:
                    out.setdefault(normalize(name), ver)
        if out:
            break
    return out


def declared_specifiers(root: Path) -> dict[str, str]:
    """name -> declared version specifier ('' if none) from requirements*.txt and
    pyproject.toml (PEP 621 + dependency-groups). Used only when no exact version is
    known, to drop fixtures whose range the declaration excludes (e.g. numpy<2)."""
    from packaging.requirements import InvalidRequirement, Requirement

    from mend.lookup import normalize, tomllib

    lines: list[str] = []
    for req in sorted(root.glob("requirements*.txt")):
        try:
            lines += req.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            pass
    pp = root / "pyproject.toml"
    if tomllib is not None and pp.is_file():
        try:
            data = tomllib.loads(pp.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - malformed pyproject is not our problem here
            data = {}
        project = data.get("project", {}) or {}
        lines += [str(x) for x in project.get("dependencies", []) or []]
        for grp in (project.get("optional-dependencies", {}) or {}).values():
            lines += [str(x) for x in grp or []]
        for grp in (data.get("dependency-groups", {}) or {}).values():
            lines += [x for x in grp or [] if isinstance(x, str)]
    out: dict[str, str] = {}
    for line in lines:
        line = line.split(" #", 1)[0].strip()
        if not line or line.startswith(("#", "-")):
            continue
        try:
            req = Requirement(line)
        except InvalidRequirement:
            continue
        out.setdefault(normalize(req.name), str(req.specifier))
    return out


def project_versions(root: Path) -> tuple[dict[str, str | None], dict[str, str]]:
    """(deps, declared specifiers). deps maps name -> pinned/locked version, falling
    back to the version installed in the project's .venv, else None."""
    from mend.lookup import parse_dependencies

    deps = parse_dependencies(root)
    if any(v is None for v in deps.values()):
        venv = _venv_versions(root)
        for name, ver in deps.items():
            if ver is None and name in venv:
                deps[name] = venv[name]
    return deps, declared_specifiers(root)


def _spec_overlaps(fixture_spec: str, declared: str) -> bool:
    """Heuristic: can a version satisfy both specifiers? Probes the boundary
    versions named in either spec plus a very high version."""
    from packaging.specifiers import InvalidSpecifier, SpecifierSet
    from packaging.version import InvalidVersion, Version

    try:
        fs, ds = SpecifierSet(fixture_spec or ""), SpecifierSet(declared or "")
    except InvalidSpecifier:
        return True
    probes: list[Version] = [Version("9999")]
    for spec in list(fs) + list(ds):
        try:
            v = Version(spec.version.replace(".*", ""))
        except InvalidVersion:
            continue
        rel = list(v.release) + [0] * (3 - len(v.release))
        probes += [v, Version(".".join(map(str, rel[:2] + [rel[2] + 1]))),
                   Version(f"{rel[0]}.{rel[1] + 1}"), Version(f"{rel[0] + 1}")]
    return any(fs.contains(p, prereleases=True) and ds.contains(p, prereleases=True)
               for p in probes)


def _spec_implies(declared: str, fixture_spec: str) -> bool:
    """Heuristic: does every version allowed by `declared` fall in `fixture_spec`?
    (e.g. declared pydantic>=2.5 implies fixture range >=2.0)."""
    from packaging.specifiers import InvalidSpecifier, SpecifierSet
    from packaging.version import InvalidVersion, Version

    if not declared:
        return False
    try:
        ds, fs = SpecifierSet(declared), SpecifierSet(fixture_spec or "")
    except InvalidSpecifier:
        return False
    probes = [Version("0"), Version("9999")]
    for spec in list(ds) + list(fs):
        try:
            v = Version(spec.version.replace(".*", ""))
        except InvalidVersion:
            continue
        rel = list(v.release) + [0] * (3 - len(v.release))
        probes += [v, Version(".".join(map(str, rel[:2] + [rel[2] + 1])))]
        if rel[2] > 0:
            probes.append(Version(".".join(map(str, rel[:2] + [rel[2] - 1]))))
        elif rel[1] > 0:
            probes.append(Version(f"{rel[0]}.{rel[1] - 1}.99"))
        elif rel[0] > 0:
            probes.append(Version(f"{rel[0] - 1}.99.99"))
    inside = [p for p in probes if ds.contains(p, prereleases=True)]
    return bool(inside) and all(fs.contains(p, prereleases=True) for p in inside)


def _lower_bound(spec: str) -> tuple[int, ...]:
    """Highest lower bound in a range like '>=2.4' -> (2, 4); () if none. Newer
    breakages sort first: they are the ones least likely to be in model training data."""
    best: tuple[int, ...] = ()
    for m in re.finditer(r"(>=|>|==|~=)\s*([0-9][0-9.]*)", spec or ""):
        v = tuple(int(x) for x in m.group(2).strip(".").split(".") if x)
        best = max(best, v)
    return best


@dataclass
class Match:
    fixture: Any
    package: str
    version: str | None   # project version (pinned/locked/installed), None if unknown
    declared: str = ""    # declared specifier, used when version is unknown
    implied: bool = False  # declared specifier implies the fixture's range


def relevant_fixtures(fixtures: list[Any], deps: dict[str, str | None],
                      declared: dict[str, str]) -> list[Match]:
    """Verified fixtures whose range matches the project's known version (or is implied
    by its declared specifier) first, then those whose version is unknown but not
    excluded by the declaration. Within each group, newer breakages first."""
    from mend.lookup import lookup, normalize

    verified = [f for f in fixtures if str(get(f, "status", default="")) == "verified"]
    known: list[Match] = []
    unknown: list[Match] = []
    for fx in lookup(verified, deps, limit=10**6):  # drops known-version mismatches
        pkg = normalize(str(get(fx, "package", default="")))
        ver, decl = deps.get(pkg), declared.get(pkg, "")
        spec = str(get(fx, "versions", default=""))
        if ver is not None:
            known.append(Match(fx, pkg, ver))
        elif _spec_implies(decl, spec):
            known.append(Match(fx, pkg, None, decl, implied=True))
        elif _spec_overlaps(spec, decl):
            unknown.append(Match(fx, pkg, None, decl))
    key = lambda m: tuple(-x for x in _lower_bound(str(get(m.fixture, "versions", default=""))))  # noqa: E731
    known.sort(key=key)      # stable: keeps lookup order within equal bounds
    unknown.sort(key=key)
    return known + unknown


# --------------------------------------------------------------------------- phrasing

def _code(text: Any, max_len: int = 70) -> str:
    s = sanitize(text, max_len=max_len).replace("`", "'")
    return f"`{s}`" if s else ""


def _first_line(text: Any, max_len: int = 90) -> str:
    """First line of an error message, quoted so it reads as observed output."""
    s = str(text or "").strip().splitlines()
    s = sanitize(s[0] if s else "", max_len=max_len).replace("`", "'").replace('"', "'")
    return f'"{s}"' if s else ""


def _range(m: Match) -> str:
    """'In numpy>=2.4 (project: numpy 2.4.1)', 'In pydantic>=2.0 (project requires
    pydantic>=2.5)' or 'If pydantic>=2.0 (project pins no pydantic version)'."""
    spec = sanitize(get(m.fixture, "versions", default=""), max_len=40)
    pkg = sanitize(m.package, max_len=60)
    if m.version is not None:
        return f"In {pkg}{spec} (project: {pkg} {sanitize(m.version, max_len=40)})"
    if m.implied:
        return f"In {pkg}{spec} (project requires {pkg}{sanitize(m.declared, max_len=40)})"
    return f"If {pkg}{spec} (project pins no {pkg} version)"


def fact_line(m: Match) -> str:
    fx = m.fixture
    fid = sanitize(get(fx, "id"), max_len=100)
    bad = _code(get(fx, "failure", "bad_pattern"))
    fix = _code(get(fx, "failure", "fix_pattern"))
    symptom = _first_line(get(fx, "failure", "symptom"))
    parts = [f"{_range(m)}, {bad} results in {symptom}" if symptom else f"{_range(m)}, {bad} fails"]
    if fix:
        parts.append(f"the working form is {fix}")
    return "- " + "; ".join(parts) + f". [mend:{fid}]"


def session_context(matches: list[Match]) -> str:
    lines = ["MEND verified known-failure data for this project's dependencies "
             "(reference facts, from the MEND catalog):"]
    lines += [fact_line(m) for m in matches[:MAX_FACTS]]
    extra = len(matches) - MAX_FACTS
    tail = "Full records with working code: MEND MCP tool mend_get_fixture <id>."
    if extra > 0:
        tail = f"{extra} more matching record(s) are available via the mend_lookup MCP tool. " + tail
    lines.append(tail)
    return "\n".join(lines)


# --------------------------------------------------------------------------- handlers

def _load(fixtures_root: Path | None) -> list[Any]:
    from mend.fixture import load_all

    if fixtures_root is None or not fixtures_root.is_dir():
        _debug(f"no fixtures directory ({fixtures_root})")
        return []
    return load_all(str(fixtures_root))


def session_start(data: dict[str, Any], out: TextIO) -> int:
    root = _project_dir(data)
    deps, declared = project_versions(root)
    if not deps:
        _debug(f"no dependencies found under {root}")
        return 0
    matches = relevant_fixtures(_load(fixtures_dir()), deps, declared)
    if not matches:
        return 0
    payload = {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                      "additionalContext": session_context(matches)}}
    out.write(json.dumps(payload) + "\n")
    return 0


def edited_paths(data: dict[str, Any]) -> list[Path]:
    ti = data.get("tool_input") or {}
    tr = data.get("tool_response") or {}
    cands = []
    if isinstance(ti, dict):
        cands.append(ti.get("file_path"))
    if isinstance(tr, dict):
        cands.append(tr.get("filePath"))
    base = Path(str(data.get("cwd") or os.getcwd()))
    out: list[Path] = []
    for c in cands:
        if isinstance(c, str) and c:
            p = Path(c)
            p = p if p.is_absolute() else base / p
            if p not in out:
                out.append(p)
    return out


_LINE_RE = re.compile(r"\s+")


def _source_line(path: Path, line: int) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return _LINE_RE.sub(" ", lines[line - 1]).strip() if 0 < line <= len(lines) else ""
    except OSError:
        return ""


def finding_line(path: Path, line: int, m: Match, display: str) -> str:
    fx = m.fixture
    fid = sanitize(get(fx, "id"), max_len=100)
    code = _code(_source_line(path, line), max_len=100)
    symptom = _first_line(get(fx, "failure", "symptom"))
    fix = _code(get(fx, "failure", "fix_pattern"))
    title = sanitize(get(fx, "title"), max_len=140)
    s = f"{display}:{line}: {code} matches a verified known failure ({title}). " if code else \
        f"{display}:{line}: matches a verified known failure ({title}). "
    s += _range(m) + (f", this code results in {symptom}" if symptom else ", this code fails")
    if fix:
        s += f"; the working form is {fix}"
    return s + f". [mend:{fid}]"


def post_tool_use(data: dict[str, Any], err: TextIO) -> int:
    tool = data.get("tool_name")
    if tool and tool not in FILE_TOOLS:
        return 0
    paths = [p for p in edited_paths(data) if p.suffix == ".py" and p.is_file()]
    if not paths:
        return 0
    # The edited file's own project (nearest dependency files above it), else the session's.
    root = find_project_root(paths[0].resolve().parent)
    if not _has_dep_files(root):
        root = _project_dir(data)
    deps, declared = project_versions(root)
    if not deps:
        return 0
    matches = relevant_fixtures(_load(fixtures_dir()), deps, declared)
    if not matches:
        return 0
    from mend.check import check_paths

    by_id = {str(get(m.fixture, "id")): m for m in matches}
    use_semgrep = bool(os.environ.get("MEND_HOOK_SEMGREP"))  # semgrep is slow per edit
    findings = check_paths(paths, [m.fixture for m in matches], use_semgrep=use_semgrep)
    lines = []
    for f in findings:
        m = by_id.get(f.fixture_id)
        if m is None:
            continue
        p = Path(f.path)
        try:
            display = str(p.resolve().relative_to(root.resolve()))
        except ValueError:
            display = str(p)
        lines.append(finding_line(p, f.line, m, display))
    if not lines:
        return 0
    head = (f"MEND: {len(lines)} line(s) in the edited file match verified known-failure "
            "records for this project's dependency versions (reference data):")
    shown = lines[:MAX_FINDINGS]
    if len(lines) > MAX_FINDINGS:
        shown.append(f"... and {len(lines) - MAX_FINDINGS} more.")
    err.write("\n".join([head] + shown) + "\n")
    return 2


HANDLERS = {"session-start": "session_start", "post-tool-use": "post_tool_use"}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {"-h", "--help"} or argv[0] not in HANDLERS:
        print("usage: mend hook {session-start|post-tool-use} < hook-input.json\n\n"
              "Claude Code hook handlers. Read hook JSON on stdin; never fail the session.",
              file=sys.stderr if argv and argv[0] not in {"-h", "--help"} else sys.stdout)
        return 0 if argv and argv[0] in {"-h", "--help"} else 2
    event = argv[0]
    try:
        data = read_input(sys.stdin)
        if event == "session-start":
            return session_start(data, sys.stdout)
        return post_tool_use(data, sys.stderr)
    except Exception:  # noqa: BLE001 - a hook must never break the session
        if os.environ.get("MEND_DEBUG"):
            traceback.print_exc()
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
