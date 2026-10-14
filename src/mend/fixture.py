"""Fixture model: loading, discovery and validation of `fixture.yaml` entries.

See docs/FIXTURE_SPEC.md for the format. Loading is lenient (missing fields get
empty defaults) so that `validate()` can report every problem at once instead of
failing on the first one.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml
from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

FIXTURE_FILE = "fixture.yaml"
DEFAULT_ROOT = "fixtures"
ENV_FIXTURES_DIR = "MEND_FIXTURES_DIR"

ECOSYSTEMS = ("python",)
FAILURE_KINDS = (
    "api-removed",
    "api-renamed",
    "signature-changed",
    "behavior-changed",
    "deprecated-broken",
)
STATUSES = ("draft", "verified")
SOURCE_TYPES = ("issue", "pr", "docs", "changelog", "advisory", "other")
MAX_FILE_LINES = 60

_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_PYTHON_RE = re.compile(r"^3\.\d+$")
_URL_RE = re.compile(r"^https?://[^\s/]+\.[^\s]+$")


class FixtureError(Exception):
    """A fixture.yaml could not be read or parsed at all."""


@dataclass
class Failure:
    kind: str = ""
    symptom: str = ""
    bad_pattern: str = ""
    fix_pattern: str = ""


@dataclass
class Repro:
    python: str = ""
    deps: list[str] = field(default_factory=list)


@dataclass
class Source:
    type: str = ""
    url: str = ""


@dataclass
class Provenance:
    sources: list[Source] = field(default_factory=list)
    license: str = ""


@dataclass
class Fixture:
    """One fixture, mirroring fixture.yaml. `path` is the fixture directory."""

    id: str
    title: str
    summary: str
    ecosystem: str
    package: str
    versions: str
    tags: list[str]
    failure: Failure
    repro: Repro
    provenance: Provenance
    status: str
    path: Path
    #: Keys present in fixture.yaml that are not part of the spec.
    extra: dict[str, Any] = field(default_factory=dict)
    #: Problems found while loading (missing required keys, wrong YAML types).
    load_errors: list[str] = field(default_factory=list)

    @property
    def bad_dir(self) -> Path:
        return self.path / "bad"

    @property
    def fixed_dir(self) -> Path:
        return self.path / "fixed"

    @property
    def check_dir(self) -> Path:
        return self.path / "check"

    @property
    def rule_path(self) -> Path | None:
        rule = self.path / "rule.yml"
        return rule if rule.is_file() else None

    def to_dict(self) -> dict[str, Any]:
        """The fixture.yaml-shaped data plus `path` (as a string)."""
        data = asdict(self)
        data.pop("extra")
        data.pop("load_errors")
        data["path"] = str(self.path)
        return data


_REQUIRED_KEYS = (
    "id",
    "title",
    "summary",
    "ecosystem",
    "package",
    "versions",
    "tags",
    "failure",
    "repro",
    "provenance",
    "status",
)


def _str(value: Any) -> str:
    if value is None:
        return ""
    return value.strip() if isinstance(value, str) else str(value)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _str_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [_str(v) for v in value]
    if value is None:
        return []
    return [_str(value)]


def _load_errors(data: Mapping[str, Any]) -> list[str]:
    errors = [f"missing required field '{k}'" for k in _REQUIRED_KEYS if data.get(k) in (None, "", [], {})]
    python = _mapping(data.get("repro")).get("python")
    if python is not None and not isinstance(python, str):
        errors.append(f"repro.python must be a quoted string (got {python!r}; 3.10 would load as 3.1)")
    for key in ("versions",):
        if data.get(key) is not None and not isinstance(data.get(key), str):
            errors.append(f"{key} must be a string")
    for key in ("failure", "repro", "provenance"):
        if data.get(key) is not None and not isinstance(data.get(key), Mapping):
            errors.append(f"{key} must be a mapping")
    if data.get("tags") is not None and not isinstance(data.get("tags"), list):
        errors.append("tags must be a list")
    return errors


def _from_dict(data: Mapping[str, Any], path: Path) -> Fixture:
    failure = _mapping(data.get("failure"))
    repro = _mapping(data.get("repro"))
    prov = _mapping(data.get("provenance"))
    raw_sources = prov.get("sources") if isinstance(prov.get("sources"), list) else []
    sources = [
        Source(type=_str(s.get("type")), url=_str(s.get("url")))
        for s in raw_sources
        if isinstance(s, Mapping)
    ]
    known = {f.name for f in fields(Fixture)}
    return Fixture(
        id=_str(data.get("id")),
        title=_str(data.get("title")),
        summary=_str(data.get("summary")),
        ecosystem=_str(data.get("ecosystem")),
        package=_str(data.get("package")),
        versions=_str(data.get("versions")),
        tags=_str_list(data.get("tags")),
        failure=Failure(
            kind=_str(failure.get("kind")),
            symptom=_str(failure.get("symptom")),
            bad_pattern=_str(failure.get("bad_pattern")),
            fix_pattern=_str(failure.get("fix_pattern")),
        ),
        repro=Repro(python=_str(repro.get("python")), deps=_str_list(repro.get("deps"))),
        provenance=Provenance(sources=sources, license=_str(prov.get("license"))),
        status=_str(data.get("status")),
        path=path,
        extra={k: v for k, v in data.items() if k not in known},
        load_errors=_load_errors(data),
    )


def load_fixture(path: str | os.PathLike[str]) -> Fixture:
    """Load a fixture from its directory or from its fixture.yaml path."""
    p = Path(path)
    yaml_path = p if p.name == FIXTURE_FILE else p / FIXTURE_FILE
    try:
        text = yaml_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FixtureError(f"{yaml_path}: cannot read: {exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise FixtureError(f"{yaml_path}: invalid YAML: {exc}") from exc
    if not isinstance(data, Mapping):
        raise FixtureError(f"{yaml_path}: top level must be a mapping")
    return _from_dict(data, yaml_path.parent.resolve())


def resolve_root(root: str | os.PathLike[str] | None = DEFAULT_ROOT) -> Path:
    """Resolve the catalog root.

    `None` means "the default catalog": `$MEND_FIXTURES_DIR` if set, else
    `./fixtures`. The literal default `"fixtures"` also falls back to
    `$MEND_FIXTURES_DIR` when `./fixtures` does not exist (e.g. an installed
    package run outside the repo). Relative paths resolve against the cwd.
    """
    env = os.environ.get(ENV_FIXTURES_DIR)
    if root is None:
        return Path(env or DEFAULT_ROOT).resolve()
    p = Path(root)
    if str(root) == DEFAULT_ROOT and not p.is_dir() and env:
        return Path(env).resolve()
    return p.resolve()


def iter_fixture_files(root: str | os.PathLike[str] | None = DEFAULT_ROOT) -> Iterator[Path]:
    """Yield every fixture.yaml under `root` in a stable order."""
    base = resolve_root(root)
    if base.is_file() and base.name == FIXTURE_FILE:
        yield base
        return
    if not base.is_dir():
        return
    for p in sorted(base.rglob(FIXTURE_FILE)):
        if not any(part.startswith(".") for part in p.relative_to(base).parts):
            yield p


def load_all(root: str | os.PathLike[str] | None = DEFAULT_ROOT) -> list[Fixture]:
    """Load every fixture under `root`. Raises FixtureError on unparseable files."""
    return [load_fixture(p) for p in iter_fixture_files(root)]


# --------------------------------------------------------------------------- validation


def _validate_deps(fx: Fixture) -> list[str]:
    errors: list[str] = []
    if not fx.repro.deps:
        return ["repro.deps: must list at least one exact pin (name==version)"]
    pinned: dict[str, str] = {}
    for dep in fx.repro.deps:
        try:
            req = Requirement(dep)
        except InvalidRequirement as exc:
            errors.append(f"repro.deps: invalid requirement {dep!r}: {exc}")
            continue
        specs = list(req.specifier)
        if req.url or req.marker or len(specs) != 1 or specs[0].operator != "==" or "*" in specs[0].version:
            errors.append(f"repro.deps: {dep!r} must be an exact pin like 'name==1.2.3'")
            continue
        name = canonicalize_name(req.name)
        if name in pinned:
            errors.append(f"repro.deps: {req.name!r} is pinned more than once")
        pinned[name] = specs[0].version
    if fx.package:
        version = pinned.get(canonicalize_name(fx.package))
        if version is None and not errors:
            errors.append(f"repro.deps: must pin the fixture package {fx.package!r}")
        elif version is not None and fx.versions:
            try:
                in_range = Version(version) in SpecifierSet(fx.versions)
            except (InvalidSpecifier, InvalidVersion):
                in_range = True  # reported elsewhere
            if not in_range:
                errors.append(
                    f"repro.deps: pinned {fx.package}=={version} is outside versions {fx.versions!r}"
                )
    return errors


def _validate_files(fx: Fixture) -> list[str]:
    errors: list[str] = []
    for rel in ("bad/target.py", "fixed/target.py"):
        if not (fx.path / rel).is_file():
            errors.append(f"missing file {rel}")
    if not fx.check_dir.is_dir():
        errors.append("missing directory check/")
    elif not any(fx.check_dir.glob("test_*.py")):
        errors.append("check/ contains no test_*.py file")
    candidates = [fx.path / "bad/target.py", fx.path / "fixed/target.py"]
    if fx.check_dir.is_dir():
        candidates += sorted(fx.check_dir.glob("*.py"))
    for f in candidates:
        if f.is_file():
            n = len(f.read_text(encoding="utf-8", errors="replace").splitlines())
            if n > MAX_FILE_LINES:
                errors.append(f"{f.relative_to(fx.path)} has {n} lines (max {MAX_FILE_LINES})")
    rule = fx.path / "rule.yml"
    if rule.exists():
        try:
            data = yaml.safe_load(rule.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            errors.append(f"rule.yml: does not parse: {exc}")
        else:
            rules = data.get("rules") if isinstance(data, Mapping) else None
            if not isinstance(rules, list) or not rules:
                errors.append("rule.yml: must contain a non-empty 'rules' list")
            elif not all(isinstance(r, Mapping) and r.get("id") for r in rules):
                errors.append("rule.yml: every rule needs an 'id'")
    return errors


def validate(fixture: Fixture) -> list[str]:
    """Return a list of human-readable spec violations (empty if valid)."""
    fx = fixture
    errors = list(fx.load_errors)

    if fx.id:
        if not _ID_RE.match(fx.id):
            errors.append(f"id {fx.id!r} must be kebab-case (a-z, 0-9, '-')")
        if fx.id != fx.path.name:
            errors.append(f"id {fx.id!r} must equal directory name {fx.path.name!r}")
        if fx.package:
            prefix = canonicalize_name(fx.package) + "-"
            if not fx.id.startswith(prefix):
                errors.append(f"id {fx.id!r} must be prefixed with the package: {prefix!r}")
    if fx.ecosystem and fx.ecosystem not in ECOSYSTEMS:
        errors.append(f"ecosystem {fx.ecosystem!r} not one of {', '.join(ECOSYSTEMS)}")
    if fx.versions:
        try:
            SpecifierSet(fx.versions)
        except InvalidSpecifier:
            errors.append(f"versions {fx.versions!r} is not a valid PEP 440 specifier set")
    if not all(fx.tags):
        errors.append("tags: must be non-empty strings")

    if not fx.failure.kind:
        errors.append("missing required field 'failure.kind'")
    elif fx.failure.kind not in FAILURE_KINDS:
        errors.append(f"failure.kind {fx.failure.kind!r} not one of {', '.join(FAILURE_KINDS)}")
    for key in ("symptom", "bad_pattern", "fix_pattern"):
        if not getattr(fx.failure, key):
            errors.append(f"missing required field 'failure.{key}'")

    if not fx.repro.python:
        errors.append("missing required field 'repro.python'")
    elif not _PYTHON_RE.match(fx.repro.python):
        errors.append(f"repro.python {fx.repro.python!r} must look like '3.12'")
    errors += _validate_deps(fx)

    if not fx.provenance.license:
        errors.append("missing required field 'provenance.license'")
    if not fx.provenance.sources:
        errors.append("provenance.sources: need at least one source with a public http(s) URL")
    for i, src in enumerate(fx.provenance.sources):
        if src.type not in SOURCE_TYPES:
            errors.append(f"provenance.sources[{i}].type {src.type!r} not one of {', '.join(SOURCE_TYPES)}")
        if not _URL_RE.match(src.url):
            errors.append(f"provenance.sources[{i}].url {src.url!r} is not an http(s) URL")

    if fx.status and fx.status not in STATUSES:
        errors.append(f"status {fx.status!r} not one of {', '.join(STATUSES)}")
    if fx.extra:
        errors.append(f"unknown top-level field(s): {', '.join(sorted(map(str, fx.extra)))}")

    errors += _validate_files(fx)
    return errors


def validate_all(fixtures: Iterable[Fixture]) -> dict[Path, list[str]]:
    """Validate each fixture plus catalog-wide rules (unique ids). Only failures are returned."""
    results: dict[Path, list[str]] = {}
    seen: dict[str, Path] = {}
    for fx in fixtures:
        errors = validate(fx)
        if fx.id in seen:
            errors.append(f"duplicate id {fx.id!r} (also at {seen[fx.id]})")
        elif fx.id:
            seen[fx.id] = fx.path
        if errors:
            results[fx.path] = errors
    return results


# --------------------------------------------------------------------------- CLI


def _table(rows: list[list[str]], headers: list[str]) -> str:
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(headers)]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    lines = [fmt.format(*headers), fmt.format(*("-" * w for w in widths))]
    lines += [fmt.format(*r) for r in rows]
    return "\n".join(line.rstrip() for line in lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mend list", description="List fixtures in the catalog.")
    parser.add_argument("--root", default=None, help=f"catalog root (default: ${ENV_FIXTURES_DIR} or ./fixtures)")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--validate", action="store_true", help="validate every fixture; exit 1 on errors")
    args = parser.parse_args(argv)

    root = resolve_root(args.root)
    fixtures: list[Fixture] = []
    problems: dict[Path, list[str]] = {}
    for yaml_path in iter_fixture_files(root):
        try:
            fixtures.append(load_fixture(yaml_path))
        except FixtureError as exc:
            problems[yaml_path.parent] = [str(exc)]

    if args.validate:
        problems.update(validate_all(fixtures))
        total = len(fixtures) + sum(1 for p in problems if p not in {f.path for f in fixtures})
        if args.json:
            report = {
                "root": str(root),
                "count": total,
                "errors": {str(p): errs for p, errs in sorted(problems.items())},
            }
            print(json.dumps(report, indent=2))
        else:
            for p, errs in sorted(problems.items()):
                for err in errs:
                    print(f"{p}: {err}", file=sys.stderr)
            print(f"{total} fixture(s) under {root}: {total - len(problems)} valid, {len(problems)} invalid")
        return 1 if problems else 0

    for p, errs in problems.items():
        print(f"{p}: {errs[0]}", file=sys.stderr)
    if args.json:
        print(json.dumps([f.to_dict() for f in fixtures], indent=2))
    else:
        rows = [[f.id, f.package, f.failure.kind, f.status] for f in fixtures]
        print(_table(rows, ["ID", "PACKAGE", "KIND", "STATUS"]))
        print(f"\n{len(fixtures)} fixture(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
