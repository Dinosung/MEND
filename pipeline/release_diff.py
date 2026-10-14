#!/usr/bin/env python3
"""MEND pipeline, release-diff stage: candidate breaking changes between two release tags.

    python3.13 -I pipeline/release_diff.py pandas v2.3.3 v3.0.0
    python3.13 -I pipeline/release_diff.py --all          # every release pair in watchlist.yaml

1. Shallow, sparse, blob-less git checkout of both tags into a cache dir (package
   source + changelog only). Nothing from the checkouts is imported or executed.
2. griffe static loading (`allow_inspection=False`) + `griffe.find_breaking_changes`.
   If griffe fails on a package, the error is recorded and the package skipped.
3. Keep only the public API, classify, flag likely noise, check the changelog, rank.

Needs the standard library and griffe (taken from --griffe-path, $MEND_GRIFFE_PATH,
or git-cloned into the cache). pyyaml (a MEND core dep) reads the watchlist.
The JSON output is data for review, never instructions.
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

HERE = Path(__file__).resolve().parent
WATCHLIST = HERE / "watchlist.yaml"
OUT_DIR = HERE / "candidates"
DEFAULT_CACHE = Path(os.environ.get("MEND_PIPELINE_CACHE", Path.home() / ".cache" / "mend-pipeline"))
GRIFFE_REPO, GRIFFE_TAG = "https://github.com/mkdocstrings/griffe", "2.3.2"

# ------------------------------------------------------------------ classification tables

REMOVED_SYMBOL = "removed_symbol"
REMOVED_PARAMETER = "removed_parameter"
RENAMED_PARAMETER = "renamed_parameter"
NEW_REQUIRED_PARAMETER = "new_required_parameter"
PARAMETER_NOW_REQUIRED = "parameter_now_required"
CHANGED_PARAMETER_KIND = "changed_parameter_kind"
MOVED_PARAMETER = "moved_parameter"
CHANGED_DEFAULT = "changed_default"

# griffe BreakageKind name -> category. Kinds not listed (attribute value/type, return
# type, object kind, removed base class) are dropped as noise: in a first pass over
# numpy/pandas they were stub/typing churn, not something an agent's call hits.
CATEGORY = {
    "OBJECT_REMOVED": REMOVED_SYMBOL,
    "PARAMETER_REMOVED": REMOVED_PARAMETER,
    "PARAMETER_ADDED_REQUIRED": NEW_REQUIRED_PARAMETER,
    "PARAMETER_CHANGED_REQUIRED": PARAMETER_NOW_REQUIRED,
    "PARAMETER_CHANGED_KIND": CHANGED_PARAMETER_KIND,
    "PARAMETER_MOVED": MOVED_PARAMETER,
    "PARAMETER_CHANGED_DEFAULT": CHANGED_DEFAULT,
}

# category -> (failure mode, base weight). "hard" = ImportError/AttributeError/TypeError
# on the old call pattern; "soft" = silently different behaviour.
PROFILE = {
    REMOVED_SYMBOL: ("hard", 5.0),
    REMOVED_PARAMETER: ("hard", 5.0),
    RENAMED_PARAMETER: ("hard", 5.5),
    NEW_REQUIRED_PARAMETER: ("hard", 4.0),
    PARAMETER_NOW_REQUIRED: ("hard", 4.0),
    CHANGED_PARAMETER_KIND: ("hard", 4.0),
    MOVED_PARAMETER: ("soft", 2.0),
    CHANGED_DEFAULT: ("soft", 2.5),
}

CALLABLE_DUNDERS = {"__init__", "__new__", "__call__", "__enter__", "__exit__", "__aenter__", "__aexit__"}
TEST_SEGMENTS = {"tests", "test", "testing", "_testing", "conftest", "benchmarks"}
INTERNAL_SEGMENTS = {"internal", "internals", "vendor", "_vendor", "externals", "compat"}
VARIADIC_NAMES = {"args", "kwargs", "kwds", "self", "cls"}

# ------------------------------------------------------------------ pure logic (unit-tested)


def is_dunder(seg: str) -> bool:
    return seg.startswith("__") and seg.endswith("__") and len(seg) > 4


def is_private_segment(seg: str) -> bool:
    """`_x` and `__x` are private; dunders are not."""
    return seg.startswith("_") and not is_dunder(seg)


def privacy_reason(path: str, internal: Iterable[str] = ()) -> str | None:
    """Why `path` is not public API ("test", "dunder", "private", "internal"), or None.

    `internal` entries are module names below the top-level package, single ("core")
    or dotted ("io.formats").
    """
    parts = path.split(".")
    for seg in parts:
        if seg in TEST_SEGMENTS or seg.startswith("test_"):
            return "test"
        if is_dunder(seg) and seg not in CALLABLE_DUNDERS:
            return "dunder"
        if is_private_segment(seg):
            return "private"
    inner = "." + ".".join(parts[1:]) + "."
    if any(f".{seg}." in inner for seg in INTERNAL_SEGMENTS | set(internal)):
        return "internal"
    return None


def build_public_index(alias_edges: Iterable[tuple[str, str]], defined: Iterable[str],
                       internal: Iterable[str] = ()) -> dict[str, list[str]]:
    """Map object paths to the public paths they are importable from (shortest first).

    `alias_edges` are re-exports (alias_path, target_path), followed through chains;
    `defined` are objects at their own path. Non-public spellings are skipped.
    """
    edges = dict(alias_edges)
    index: dict[str, set[str]] = {}
    for alias in edges:
        if privacy_reason(alias, internal) is None:
            index.setdefault(final_target(alias, edges), set()).add(alias)
    for path in defined:
        if privacy_reason(path, internal) is None:
            index.setdefault(path, set()).add(path)
    return {k: sorted(v, key=_path_order) for k, v in index.items()}


def final_target(path: str, edges: dict[str, str]) -> str:
    """Follow alias -> target chains (cycle-safe)."""
    seen = set()
    while path in edges and path not in seen:
        seen.add(path)
        path = edges[path]
    return path


def is_sentinel_rename(old: str | None, new: str | None) -> bool:
    """`notset` -> `NOTSET`, `NOT_SET` -> `NOTSET`: same sentinel, new spelling."""
    if not old or not new or old == new:
        return False
    norm = [re.sub(r"[^a-z]", "", v.rsplit(".", 1)[-1].lower()) for v in (old, new)]
    return norm[0] == norm[1] and all(re.fullmatch(r"[\w.]+", v) for v in (old, new))


def _path_order(path: str) -> tuple:
    return path.count("."), len(path), path


def public_path_for(path: str, index: dict[str, list[str]], internal: Iterable[str] = ()) -> str | None:
    """Shortest public spelling of `path` (an indexed prefix's alias + the remainder), or None."""
    parts = path.split(".")
    options = [path]
    for cut in range(1, len(parts) + 1):
        options += [".".join([alias, *parts[cut:]]) for alias in index.get(".".join(parts[:cut]), [])]
    public = [p for p in options if privacy_reason(p, internal) is None]
    return min(public, key=_path_order) if public else None


def _similarity(a: str, b: str) -> float:
    a, b = a.lower(), b.lower()
    if a in b or b in a:
        return 0.8
    if len(os.path.commonprefix([a, b])) >= 4:
        return 0.7
    return difflib.SequenceMatcher(None, a, b).ratio()


def detect_rename(removed: str, old_params: list[str], new_params: list[str]) -> str | None:
    """Guess the new name of a removed parameter: the new parameter at the same position
    (if it is the only new one or looks alike), else the most similar new name."""
    added = [p for p in new_params if p not in old_params and p not in VARIADIC_NAMES]
    if not added:
        return None
    if removed in old_params:
        i = old_params.index(removed)
        if i < len(new_params) and new_params[i] in added and (
                len(added) == 1 or _similarity(removed, new_params[i]) >= 0.4):
            return new_params[i]
    best = max(added, key=lambda c: _similarity(removed, c))
    return best if _similarity(removed, best) >= 0.6 else None


def classify(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Copy of a raw breakage record with category / failure_mode; None for noise kinds."""
    category = CATEGORY.get(raw["kind"])
    if category is None:
        return None
    cand = dict(raw)
    if category == REMOVED_PARAMETER:
        new_name = detect_rename(raw["param"], raw.get("old_params") or [], raw.get("new_params") or [])
        if new_name:
            category, cand["renamed_to"] = RENAMED_PARAMETER, new_name
    cand["category"] = category
    cand["failure_mode"] = PROFILE[category][0]
    return cand


def changelog_mentions(cand: dict[str, Any], paragraphs: list[str]) -> list[str]:
    """The candidate's identifiers if they occur together in one changelog paragraph, else [].

    Parameter changes need the parameter and its function/class name; removed
    symbols need the symbol name, plus the class name for class members.
    One- or two-letter names (`x`, `a`) never confirm.
    """
    names = [p for p in cand["public_path"].split(".") if p not in CALLABLE_DUNDERS]
    if cand.get("param"):
        terms = [cand["param"], names[-1]]
    elif len(names) >= 3 and names[-2][:1].isupper():
        terms = [names[-2], names[-1]]
    else:
        terms = [names[-1]]
    if min(len(t) for t in terms) < 3:
        return []
    patterns = [re.compile(r"(?<!\w)" + re.escape(t) + r"(?!\w)") for t in terms]
    if any(all(p.search(para) for p in patterns) for para in paragraphs):
        return terms
    return []


def score(cand: dict[str, Any], hot_symbols: Iterable[str] = ()) -> float:
    """Higher = better fixture candidate: hard failure, short public path, popular, documented."""
    s = PROFILE[cand["category"]][1]
    s += max(0.0, 3.0 - 0.75 * max(0, cand["public_path"].count(".") - 1))
    if set(cand["public_path"].split(".")) & set(hot_symbols):
        s += 3.0
    if cand.get("changelog_mentions"):
        s += 2.0
    flags = cand.get("flags", [])
    s -= 4.0 * ("reexported_elsewhere" in flags) + 4.0 * ("may_be_inherited" in flags)
    s -= 2.0 * ("module_getattr_shim" in flags) + 2.0 * ("stub_only" in flags)
    return round(s, 2)


def filter_and_rank(raws: list[dict[str, Any]], *, public_index: dict[str, list[str]],
                    new_index: dict[str, list[str]] | None = None,
                    getattr_modules: dict[str, set[str]] | None = None,
                    external_base_classes: Iterable[str] = (), internal: Iterable[str] = (),
                    hot_symbols: Iterable[str] = (), changelog_text: str = "",
                    limit: int = 200) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Classify, drop non-public and noise, flag, de-duplicate, rank.

    `new_index` is the new version's public index (canonical path -> public paths);
    a removed symbol whose `canonical` object is still public there was only moved.
    `getattr_modules` maps modules that define `__getattr__` (new version) to the
    string literals in them; `external_base_classes` are new-version classes with a
    base class from another library (a "removed" method may just be inherited now).
    Returns (candidates, dropped-count-by-reason).
    """
    new_index = new_index or {}
    external_base_classes = set(external_base_classes)
    getattr_modules = getattr_modules or {}
    paragraphs = [p for p in re.split(r"\n\s*\n", changelog_text) if p.strip()]
    dropped: dict[str, int] = {}
    best: dict[tuple, dict[str, Any]] = {}

    def drop(reason: str) -> None:
        dropped[reason] = dropped.get(reason, 0) + 1

    for raw in raws:
        cand = classify(raw)
        if cand is None:
            drop(raw["kind"].lower())
            continue
        param = cand.get("param")
        if param and (is_private_segment(param) or param in VARIADIC_NAMES):
            drop("private_parameter")
            continue
        if cand["category"] in (REMOVED_PARAMETER, RENAMED_PARAMETER) and "variadic" in (cand.get("old_value") or ""):
            drop("variadic_parameter")  # *args/**kw renamed or dropped: callers can't pass it by name
            continue
        if cand["category"] == REMOVED_PARAMETER and cand["path"].endswith(".__new__") and \
                (cand.get("old_params") or [None])[0] == param:
            drop("variadic_parameter")  # first parameter of __new__ is the class
            continue
        old_default, new_default = cand.get("old_value"), cand.get("new_value")
        if cand["category"] == CHANGED_DEFAULT:
            if "..." in (old_default, new_default):
                drop("stub_default")  # `...` placeholder in a .pyi stub vs a real default
                continue
            if is_sentinel_rename(old_default, new_default):
                drop("sentinel_rename")
                continue
            if new_default in ("'deprecated'", '"deprecated"', "'warn'"):
                drop("deprecation_sentinel")  # deprecation in progress: a warning, not a break yet
                continue
        public = public_path_for(cand["path"], public_index, internal)
        if public is None:
            drop(privacy_reason(cand["path"], internal) or "not_public")
            continue
        cand["public_path"] = public
        flags = set(cand.get("flags", []))
        if cand["category"] == REMOVED_SYMBOL:
            name = public.rsplit(".", 1)[-1]
            elsewhere = [p for p in new_index.get(cand.get("canonical", cand["path"]), []) if p != public]
            if elsewhere:
                flags.add("reexported_elsewhere")
                cand["still_exported_as"] = elsewhere[:5]
            parents = {cand["path"].rsplit(".", 1)[0], public.rsplit(".", 1)[0]}
            if any(name in getattr_modules.get(p, ()) for p in parents):
                # The new module's __getattr__ knows the name: a deprecation shim (still
                # works, warns) or a curated error (still fails). Needs a check to tell.
                flags.add("module_getattr_shim")
                cand["failure_mode"] = "shim"
            if parents & external_base_classes:
                flags.add("may_be_inherited")
        cand["flags"] = sorted(flags)
        cand["changelog_mentions"] = changelog_mentions(cand, paragraphs)
        cand["score"] = score(cand, hot_symbols)
        key = (cand["category"], public, param)
        if key in best:
            drop("duplicate")
        if key not in best or cand["score"] > best[key]["score"]:
            best[key] = cand

    ranked = sorted(best.values(), key=lambda c: (-c["score"], c["public_path"], c.get("param") or ""))
    if len(ranked) > limit:
        dropped["over_limit"] = len(ranked) - limit
    return ranked[:limit], dropped


def removed_reexports(old_edges: Iterable[tuple[str, str]], new_edges: Iterable[tuple[str, str]],
                      new_defined: Iterable[str]) -> list[dict[str, Any]]:
    """OBJECT_REMOVED records for package-level re-exports missing from the new version.

    griffe skips re-exports in packages without `__all__` (e.g. `from .core import
    Option` in click), so their removal would otherwise go unnoticed.
    """
    present = {a for a, _ in new_edges} | set(new_defined)
    return [{"kind": "OBJECT_REMOVED", "path": alias, "obj_kind": "alias", "old_value": target}
            for alias, target in old_edges if alias not in present]


def _string_literals(tree: ast.AST) -> set[str]:
    return {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and n.value.isidentifier()}


# ------------------------------------------------------------------ git + griffe


def git(*args: str, cwd: Path | None = None) -> str:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_LFS_SKIP_SMUDGE="1")
    res = subprocess.run(["git", "-c", "advice.detachedHead=false", "-c", "core.hooksPath=/dev/null", *args],
                         cwd=cwd, env=env, capture_output=True, text=True, timeout=900)
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {res.stderr.strip()[-500:]}")
    return res.stdout


def checkout(repo: str, tag: str, dirs: list[str], cache: Path) -> tuple[Path, str]:
    """Cached shallow, blob-less, sparse checkout of `repo` at `tag`; returns (path, commit date)."""
    dest = cache / "repos" / re.sub(r"\W+", "_", repo.split("github.com/")[-1]) / re.sub(r"[^\w.-]+", "_", tag)
    marker = dest / ".mend-checkout-ok"
    if not marker.exists():
        shutil.rmtree(dest, ignore_errors=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        git("clone", "--quiet", "--depth", "1", "--branch", tag, "--filter=blob:none", "--no-checkout", repo, str(dest))
        git("sparse-checkout", "set", "--cone", *sorted(set(dirs)), cwd=dest)
        git("checkout", "--quiet", cwd=dest)
        marker.write_text(git("log", "-1", "--format=%cs", cwd=dest).strip())
    return dest, marker.read_text().strip()[:10]


def import_griffe(griffe_path: str | None, cache: Path):
    """Import griffe from --griffe-path, $MEND_GRIFFE_PATH, or a git clone in the cache."""
    path = griffe_path or os.environ.get("MEND_GRIFFE_PATH")
    if not path:
        dest = cache / "griffe" / GRIFFE_TAG
        if not dest.exists():
            git("clone", "--quiet", "--depth", "1", "--branch", GRIFFE_TAG, GRIFFE_REPO, str(dest))
        path = str(dest / "packages" / "griffelib" / "src")
    sys.path.insert(0, path)
    import griffe  # type: ignore

    return griffe


def _skip_unresolvable_aliases(griffe: Any, skipped: list[str]) -> None:
    """Make griffe's diff skip aliases it cannot resolve (numpy 2.5 has a CyclicAliasError)
    instead of aborting the whole traversal."""
    from griffe._internal import diff as gdiff  # type: ignore

    orig = getattr(gdiff, "_mend_orig", gdiff._alias_incompatibilities)
    gdiff._mend_orig = orig

    def safe(old_obj, new_obj, *, seen_paths):
        try:
            yield from orig(old_obj, new_obj, seen_paths=seen_paths)
        except (griffe.CyclicAliasError, griffe.AliasResolutionError, RecursionError) as exc:
            skipped.append(f"{old_obj.path}: {type(exc).__name__}")

    gdiff._alias_incompatibilities = safe


def _short(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value)
    return s if len(s) <= 120 else s[:117] + "..."


def griffe_breakages(griffe: Any, old_root: Any, new_root: Any, skipped: list[str]) -> list[dict[str, Any]]:
    """Raw breakage records from griffe.find_breaking_changes."""
    _skip_unresolvable_aliases(griffe, skipped)
    raws = []
    for b in griffe.find_breaking_changes(old_root, new_root):
        kind, obj = b.kind.name, b.obj
        rec: dict[str, Any] = {"kind": kind, "path": obj.path, "obj_kind": obj.kind.value}
        if kind.startswith("PARAMETER_"):
            p = b.old_value if b.old_value is not None else b.new_value
            rec["param"] = p.name
            rec["new_params"] = [x.name for x in obj.parameters]
            try:
                rec["old_params"] = [x.name for x in old_root.modules_collection.get_member(obj.path).parameters]
            except Exception:  # noqa: BLE001 - object moved; rename detection just gets less info
                rec["old_params"] = []
            if kind == "PARAMETER_CHANGED_KIND":
                rec["old_value"], rec["new_value"] = b.old_value.kind.value, b.new_value.kind.value
            elif kind == "PARAMETER_CHANGED_DEFAULT":
                rec["old_value"], rec["new_value"] = _short(b.old_value.default), _short(b.new_value.default)
            elif b.old_value is not None:
                rec["old_value"] = p.kind.value + (f", default={_short(p.default)}" if p.default is not None else "")
        elif kind != "OBJECT_REMOVED":
            rec["old_value"] = _short(getattr(b.old_value, "value", b.old_value))
            rec["new_value"] = _short(getattr(b.new_value, "value", b.new_value))
        if b.details:
            rec["details"] = b.details
        try:
            rec["file"], rec["lineno"] = str(obj.relative_package_filepath), obj.lineno
            if rec["file"].endswith(".pyi"):
                rec["flags"] = ["stub_only"]
        except Exception:  # noqa: BLE001 - some aliases/modules have no file
            pass
        raws.append(rec)
    return raws


def griffe_walk(root: Any, own_packages: Iterable[str]):
    """(alias_edges, defined_paths, {module: getattr_literals}, external_base_classes)
    for a griffe package tree.

    Alias edges cover griffe-public aliases plus re-exports in package `__init__`s that
    resolve inside this library (wildcard-imported `typing.Any` etc. do not).
    """
    tops = {root.path.split(".")[0], *(p.split(".")[0] for p in own_packages)}
    edges, defined, getattr_mods, class_bases = [], [], {}, {}
    stack, seen = [root], set()
    while stack:
        mod = stack.pop()
        if mod.path in seen:
            continue
        seen.add(mod.path)
        defined.append(mod.path)
        for name, member in list(mod.members.items()):
            try:
                if member.is_alias:
                    try:
                        target = member.final_target.path
                    except Exception:  # noqa: BLE001 - unresolvable (often external, e.g. typing.Any)
                        if not member.is_public:
                            continue
                        target = member.target_path
                    if target != root.path and not is_private_segment(name) and (member.is_public or (
                            (mod.is_package or mod.is_subpackage) and target.split(".")[0] in tops)):
                        edges.append((member.path, target))
                elif member.is_module:
                    stack.append(member)
                elif name == "__getattr__" and member.is_function:
                    fp = mod.filepath[0] if isinstance(mod.filepath, list) else mod.filepath
                    getattr_mods[mod.path] = _string_literals(ast.parse(Path(fp).read_text(errors="replace")))
                elif not is_private_segment(name):
                    defined.append(member.path)
                    if member.is_class:
                        class_bases[member.path] = [getattr(b, "canonical_path", str(b)) for b in member.bases]
                        defined += [m.path for n, m in member.members.items()
                                    if not m.is_alias and (n in CALLABLE_DUNDERS or not is_private_segment(n))]
            except Exception:  # noqa: BLE001 - unresolvable alias / unreadable file: skip it
                continue
    return edges, defined, getattr_mods, classes_with_external_base(class_bases, tops)


def classes_with_external_base(class_bases: dict[str, list[str]], own_tops: Iterable[str]) -> set[str]:
    """Classes with a base (anywhere up their in-library hierarchy) from another library."""
    neutral = {"object", "typing", "typing_extensions", "abc", "enum", "builtins", "collections"}
    own = set(own_tops) | neutral
    found = {c for c, bases in class_bases.items() if any(b.split(".")[0] not in own for b in bases)}
    changed = True
    while changed:
        changed = False
        for cls, bases in class_bases.items():
            if cls not in found and any(b in found for b in bases):
                found.add(cls)
                changed = True
    return found


# ------------------------------------------------------------------ watchlist + driver


@dataclasses.dataclass
class Library:
    name: str
    repo: str
    packages: list[str]
    tag_pattern: str = ""
    src_root: str = "."
    src_root_overrides: dict[str, str] = dataclasses.field(default_factory=dict)
    changelog: list[str] = dataclasses.field(default_factory=list)
    hot_symbols: list[str] = dataclasses.field(default_factory=list)
    internal_segments: list[str] = dataclasses.field(default_factory=list)
    releases: list[dict[str, Any]] = dataclasses.field(default_factory=list)


def load_watchlist(path: Path = WATCHLIST) -> dict[str, Library]:
    import yaml

    return {e["name"]: Library(**e) for e in yaml.safe_load(path.read_text())["libraries"]}


def trim_changelog(text: str, old_tag: str) -> str:
    """Cut a cumulative changelog at the first heading of the old release series
    (e.g. `## 0.119.1 (...)`, `pytest 8.4.2`, `## Version 8.4.2` for old 0.119.x / 8.4.x),
    so only entries newer than the old release can corroborate a candidate."""
    m = re.search(r"\d+[._]\d+", old_tag)
    if not m:
        return text
    series = re.escape(m.group(0).replace("_", "."))
    heading = re.compile(r"^(?:#+\s*)?(?:[A-Za-z]+\s+)?\[?v?" + series + r"(?:\.\d+)?\]?\s*(?:\(|$)")
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if len(line) < 80 and heading.match(line.strip()):
            return "\n".join(lines[:i])
    return text


def read_changelog(root: Path, paths: list[str], old_tag: str = "") -> str:
    files: list[Path] = []
    for rel in paths:
        p = root / rel
        files += sorted(f for f in p.rglob("*") if f.is_file()) if p.is_dir() else [p] if p.is_file() else []
    return "\n\n".join(trim_changelog(f.read_text(encoding="utf-8", errors="replace"), old_tag) for f in files)


def run_diff(lib: Library, old_tag: str, new_tag: str, cache: Path, griffe_path: str | None = None,
             limit: int = 200) -> dict[str, Any]:
    trees = {}
    for side, tag in (("old", old_tag), ("new", new_tag)):
        src = lib.src_root_overrides.get(tag, lib.src_root)
        dirs = [str(Path(src) / p.replace(".", "/")) for p in lib.packages]
        dirs += [str(Path(c).parent) if Path(c).suffix else c for c in lib.changelog]
        path, date = checkout(lib.repo, tag, [d for d in dirs if d not in (".", "")], cache)
        trees[side] = {"tag": tag, "date": date, "src_root": src, "path": path}
    old_src = trees["old"]["path"] / trees["old"]["src_root"]
    new_src = trees["new"]["path"] / trees["new"]["src_root"]

    raws: list[dict[str, Any]] = []
    old_edges, old_defined, new_edges, new_defined = [], [], [], []
    getattr_mods: dict[str, set[str]] = {}
    external_based: set[str] = set()
    engines, errors = set(), []
    griffe = import_griffe(griffe_path, cache)
    for pkg in lib.packages:
        try:
            kw = dict(allow_inspection=False, try_relative_path=False, store_source=False)
            old_obj = griffe.load(pkg, search_paths=[str(old_src)], **kw)
            new_obj = griffe.load(pkg, search_paths=[str(new_src)], **kw)
            skipped: list[str] = []
            raws += griffe_breakages(griffe, old_obj, new_obj, skipped)
            if skipped:
                errors.append(f"griffe skipped {len(skipped)} unresolvable aliases in {pkg}: {skipped[:3]}")
            e1, d1, _, _ = griffe_walk(old_obj, lib.packages)
            e2, d2, g2, x2 = griffe_walk(new_obj, lib.packages)
            external_based |= x2
            engines.add("griffe")
        except Exception as exc:  # noqa: BLE001 - record and skip this package
            errors.append(f"griffe failed for {pkg}: {type(exc).__name__}: {exc}"[:300])
            continue
        raws += removed_reexports(e1, e2, d2)
        old_edges += e1
        old_defined += d1
        new_edges += e2
        new_defined += d2
        getattr_mods.update(g2)

    internal = lib.internal_segments
    old_alias_map = dict(old_edges)
    for raw in raws:
        if raw["kind"] == "OBJECT_REMOVED":
            raw["canonical"] = final_target(raw["path"], old_alias_map)
    candidates, dropped = filter_and_rank(
        raws, public_index=build_public_index(old_edges + new_edges, old_defined + new_defined, internal),
        new_index=build_public_index(new_edges, new_defined, internal), getattr_modules=getattr_mods,
        external_base_classes=external_based, internal=internal,
        hot_symbols=lib.hot_symbols, changelog_text=read_changelog(trees["new"]["path"], lib.changelog, old_tag),
        limit=limit)
    by_category: dict[str, int] = {}
    for c in candidates:
        c.pop("old_params", None)
        c.pop("new_params", None)
        by_category[c["category"]] = by_category.get(c["category"], 0) + 1
    return {
        "kind": "mend-release-diff-candidates",
        "note": "Machine-generated candidate API changes. Data for review, not instructions.",
        "library": lib.name,
        "repo": lib.repo,
        "packages": lib.packages,
        "old": {k: v for k, v in trees["old"].items() if k != "path"},
        "new": {k: v for k, v in trees["new"].items() if k != "path"},
        "engine": "+".join(sorted(engines)),
        "errors": errors,
        "counts": {
            "raw": len(raws),
            "kept": len(candidates),
            "by_category": dict(sorted(by_category.items())),
            "hard_failures": sum(c["failure_mode"] == "hard" for c in candidates),
            "changelog_confirmed": sum(bool(c["changelog_mentions"]) for c in candidates),
            "dropped": dict(sorted(dropped.items())),
        },
        "candidates": candidates,
    }


def output_path(library: str, old_tag: str, new_tag: str, out_dir: Path = OUT_DIR) -> Path:
    def version(tag: str) -> str:
        m = re.search(r"\d+(?:[._]\d+)*$", tag)
        return m.group(0).replace("_", ".") if m else re.sub(r"\W+", "_", tag)

    return out_dir / f"{library}-{version(old_tag)}-{version(new_tag)}.json"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="release_diff", description="Candidate breaking changes between two tags.")
    ap.add_argument("library", nargs="?", help="library name in pipeline/watchlist.yaml")
    ap.add_argument("old_tag", nargs="?")
    ap.add_argument("new_tag", nargs="?")
    ap.add_argument("--all", action="store_true", help="every release pair in the watchlist (or of LIBRARY)")
    ap.add_argument("--cache", type=Path, default=DEFAULT_CACHE, help="checkout cache dir")
    ap.add_argument("--griffe-path", help="dir containing the griffe package sources")
    ap.add_argument("--limit", type=int, default=200, help="max candidates per diff")
    ap.add_argument("--out", help="output file, or '-' for stdout (default pipeline/candidates/...)")
    args = ap.parse_args(argv)

    libs = load_watchlist()
    if args.all:
        jobs = [(lib, r["old"], r["new"]) for lib in libs.values() if args.library in (None, lib.name)
                for r in lib.releases]
    elif args.library in libs and args.old_tag and args.new_tag:
        jobs = [(libs[args.library], args.old_tag, args.new_tag)]
    else:
        ap.error("give LIBRARY OLD_TAG NEW_TAG (library from the watchlist), or --all")

    status = 0
    for lib, old, new in jobs:
        try:
            result = run_diff(lib, old, new, args.cache, args.griffe_path, args.limit)
        except Exception as exc:  # noqa: BLE001
            print(f"{lib.name} {old}..{new}: FAILED: {exc}", file=sys.stderr)
            status = 1
            continue
        text = json.dumps(result, indent=1) + "\n"
        if args.out == "-":
            sys.stdout.write(text)
            continue
        dest = Path(args.out) if args.out and len(jobs) == 1 else output_path(lib.name, old, new)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)
        c = result["counts"]
        print(f"{lib.name} {old}..{new}: engine={result['engine']} raw={c['raw']} kept={c['kept']} "
              f"hard={c['hard_failures']} changelog={c['changelog_confirmed']} -> {dest}", file=sys.stderr)
    return status


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
