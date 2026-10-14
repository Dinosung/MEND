"""Scan code for known bad patterns from fixture rule.yml files.

Uses semgrep when it is on PATH. Otherwise falls back to a small built-in matcher
(Python `ast`) that understands the simple pattern shapes most fixtures use:

    from A import B      import A      A.B   (dotted attribute access, also `import A.B`)

Patterns it cannot handle are skipped (reported with --verbose).
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

from mend.render import get

DEFAULT_EXCLUDES = {".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules",
                    "__pycache__", ".tox", ".nox", ".mypy_cache", ".pytest_cache",
                    "build", "dist", "site-packages"}


@dataclass
class Finding:
    fixture_id: str
    path: str
    line: int
    message: str


# --------------------------------------------------------------------------- rules

@dataclass
class Pattern:
    kind: str                 # "from-import" | "import" | "attr"
    module: str
    name: str | None = None   # for from-import


@dataclass
class Rule:
    fixture_id: str
    rule_id: str
    message: str
    rule_file: Path
    patterns: list[Pattern] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)


_DOTTED = r"[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*"
_FROM_RE = re.compile(rf"^from\s+({_DOTTED})\s+import\s+(.+)$")
_IMPORT_RE = re.compile(rf"^import\s+({_DOTTED})$")
_ATTR_RE = re.compile(rf"^({_DOTTED})\.([A-Za-z_]\w*)$")
_NAME_RE = re.compile(r"^[A-Za-z_]\w*$")


def parse_pattern(text: str) -> list[Pattern] | None:
    """Translate one semgrep pattern string into built-in patterns, or None."""
    t = " ".join(str(text).split())
    m = _FROM_RE.match(t)
    if m:
        names = [n.strip() for n in m.group(2).strip("()").split(",") if n.strip()]
        if names and all(_NAME_RE.match(n) for n in names):
            return [Pattern("from-import", m.group(1), n) for n in names]
        return None
    m = _IMPORT_RE.match(t)
    if m:
        return [Pattern("import", m.group(1))]
    m = _ATTR_RE.match(t)
    if m:
        return [Pattern("attr", m.group(1), m.group(2))]
    return None


def _collect(node: Any, rule: Rule) -> None:
    if isinstance(node, str):
        pats = parse_pattern(node)
        if pats is None:
            rule.unsupported.append(f"pattern {node!r}")
        else:
            rule.patterns.extend(pats)
        return
    if isinstance(node, dict):
        if "pattern" in node:
            _collect(node["pattern"], rule)
        if "pattern-either" in node:
            for item in node["pattern-either"] or []:
                _collect(item, rule)
        other = [k for k in node if k not in ("pattern", "pattern-either")]
        for k in other:
            rule.unsupported.append(f"operator {k!r}")
        return
    rule.unsupported.append(f"entry {node!r}")


def load_rules(fixtures: Iterable[Any]) -> list[Rule]:
    rules: list[Rule] = []
    for fx in fixtures:
        base = get(fx, "path")
        if not base:
            continue
        rf = Path(str(base)) / "rule.yml"
        if not rf.is_file():
            continue
        try:
            data = yaml.safe_load(rf.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        for r in data.get("rules", []) or []:
            if not isinstance(r, dict):
                continue
            langs = r.get("languages") or ["python"]
            if "python" not in langs and "py" not in langs:
                continue
            rule = Rule(fixture_id=str(get(fx, "id")), rule_id=str(r.get("id", get(fx, "id"))),
                        message=str(r.get("message", "")).strip(), rule_file=rf)
            if any(k in r for k in ("patterns", "pattern-regex", "pattern-not")):
                rule.unsupported.append("compound/regex operators at rule level")
            matched_any = False
            for k in ("pattern", "pattern-either"):
                if k in r:
                    matched_any = True
                    _collect({k: r[k]}, rule)
            if not matched_any and not rule.unsupported:
                rule.unsupported.append("no pattern/pattern-either")
            rules.append(rule)
    return rules


# --------------------------------------------------------------------------- matcher

def _match_tree(tree: ast.AST, rule: Rule, path: str) -> list[Finding]:
    out: list[Finding] = []
    seen: set[int] = set()
    # local name -> fully dotted module/attr it refers to (from `import` statements)
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    aliases[a.asname] = a.name
                else:
                    top = a.name.split(".")[0]
                    aliases[top] = top

    def hit(line: int) -> None:
        if line not in seen:
            seen.add(line)
            out.append(Finding(rule.fixture_id, path, line, rule.message))

    def dotted(n: ast.AST) -> str | None:
        parts = []
        while isinstance(n, ast.Attribute):
            parts.append(n.attr)
            n = n.value
        if isinstance(n, ast.Name):
            root = aliases.get(n.id)
            if root is None:
                return None
            parts.append(root)
            return ".".join(reversed(parts))
        return None

    for node in ast.walk(tree):
        for p in rule.patterns:
            if p.kind == "from-import" and isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module == p.module and any(a.name == p.name for a in node.names):
                    hit(node.lineno)
            elif p.kind == "import" and isinstance(node, ast.Import):
                if any(a.name == p.module for a in node.names):
                    hit(node.lineno)
            elif p.kind == "attr":
                full = f"{p.module}.{p.name}"
                if isinstance(node, ast.Import) and any(a.name == full for a in node.names):
                    hit(node.lineno)
                elif isinstance(node, ast.Attribute) and node.attr == p.name and dotted(node) == full:
                    hit(node.lineno)
    return out


def iter_python_files(paths: Iterable[str | Path], excludes: set[str] = DEFAULT_EXCLUDES) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        p = Path(p)
        if p.is_file():
            if p.suffix == ".py":
                files.append(p)
        elif p.is_dir():
            for dirpath, dirnames, filenames in os.walk(p):
                dirnames[:] = sorted(d for d in dirnames if d not in excludes)
                files.extend(Path(dirpath) / f for f in sorted(filenames) if f.endswith(".py"))
    return files


def builtin_check(paths: Iterable[str | Path], rules: list[Rule],
                  log: Any = None) -> list[Finding]:
    findings: list[Finding] = []
    for f in iter_python_files(paths):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"), filename=str(f))
        except SyntaxError as e:
            if log:
                log(f"skip {f}: syntax error: {e}")
            continue
        for rule in rules:
            if rule.patterns:
                findings.extend(_match_tree(tree, rule, str(f)))
    return findings


def semgrep_check(paths: Iterable[str | Path], rules: list[Rule], log: Any = None) -> list[Finding]:
    exe = shutil.which("semgrep")
    files = sorted({r.rule_file for r in rules})
    if not exe or not files:
        return []
    cmd = [exe, "scan", "--json", "--quiet", "--metrics=off", "--disable-version-check"]
    for rf in files:
        cmd += ["--config", str(rf)]
    cmd += [str(p) for p in paths]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        raise RuntimeError(f"semgrep failed (exit {proc.returncode}): {proc.stderr.strip()[:500]}")
    by_rule = {r.rule_id: r for r in rules}
    out: list[Finding] = []
    for res in data.get("results", []) or []:
        cid = str(res.get("check_id", ""))
        # semgrep prefixes config-file rule ids with a path-derived namespace
        rule = by_rule.get(cid) or next((r for rid, r in by_rule.items() if cid.endswith("." + rid)), None)
        fid = rule.fixture_id if rule else cid
        msg = (res.get("extra") or {}).get("message") or (rule.message if rule else "")
        out.append(Finding(fid, str(res.get("path", "")), int((res.get("start") or {}).get("line", 0)),
                           str(msg).strip()))
    if log:
        for err in data.get("errors", []) or []:
            log(f"semgrep: {err.get('message', err)}")
    return out


def check_paths(paths: Iterable[str | Path], fixtures: Iterable[Any], *,
                use_semgrep: bool | None = None, verbose: bool = False,
                log: Any = None) -> list[Finding]:
    """Scan `paths` for bad patterns of `fixtures`. Semgrep if available, else built-in."""
    paths = list(paths)
    if log is None and verbose:
        log = lambda m: print(m, file=sys.stderr)  # noqa: E731
    rules = load_rules(fixtures)
    if use_semgrep is None:
        use_semgrep = shutil.which("semgrep") is not None
    if use_semgrep:
        if log:
            log(f"using semgrep with {len(rules)} rule(s)")
        findings = semgrep_check(paths, rules, log=log)
    else:
        if log:
            log(f"semgrep not found; using built-in matcher with {len(rules)} rule(s)")
            for r in rules:
                for u in r.unsupported:
                    log(f"  {r.fixture_id}: skipped unsupported {u}")
        findings = builtin_check(paths, rules, log=log)
    findings.sort(key=lambda f: (f.path, f.line, f.fixture_id))
    return findings


def format_findings(findings: list[Finding]) -> str:
    if not findings:
        return "mend check: no known bad patterns found"
    lines = [f"{f.path}:{f.line}: [{f.fixture_id}] {f.message}" for f in findings]
    lines.append(f"mend check: {len(findings)} finding(s). Details: mend lookup / mend_get_fixture <id>")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from mend.lookup import load_fixtures, lookup, parse_dependencies

    ap = argparse.ArgumentParser(prog="mend check", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", help="files/dirs to scan (default: --project dir)")
    ap.add_argument("--project", default=".", help="project dir for dependency detection")
    ap.add_argument("--all-fixtures", action="store_true",
                    help="use every fixture, not only those relevant to project deps")
    ap.add_argument("--fixtures", default=None, help="fixtures root")
    ap.add_argument("--no-semgrep", action="store_true", help="force the built-in matcher")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    fixtures = load_fixtures(args.fixtures)
    if not args.all_fixtures:
        deps = parse_dependencies(args.project)
        fixtures = lookup(fixtures, deps, limit=10**6)
    if args.verbose:
        print(f"mend check: {len(fixtures)} fixture(s) in scope", file=sys.stderr)
    findings = check_paths(args.paths or [args.project], fixtures,
                           use_semgrep=False if args.no_semgrep else None, verbose=args.verbose)
    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2))
    else:
        print(format_findings(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
