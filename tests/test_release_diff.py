"""Tests for pipeline/release_diff.py: pure filtering / classification logic (no network, no git)."""

from __future__ import annotations

import importlib.util
import json
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("release_diff", ROOT / "pipeline" / "release_diff.py")
rd = importlib.util.module_from_spec(_spec)
sys.modules["release_diff"] = rd
_spec.loader.exec_module(rd)


# ---------------------------------------------------------------- privacy


@pytest.mark.parametrize("path,reason", [
    ("pandas.DataFrame.to_csv", None),
    ("pandas.DataFrame.__init__", None),
    ("pandas._libs.lib.foo", "private"),
    ("pandas.core.frame._helper", "private"),
    ("numpy.testing.assert_equal", "test"),
    ("pkg.tests.test_x.f", "test"),
    ("pkg.mod.Cls.__repr__", "dunder"),
    ("pkg.vendor.six.moves", "internal"),
    ("pytest.fixture", None),  # 'pytest' contains 'test' but is not a test module
])
def test_privacy_reason(path, reason):
    assert rd.privacy_reason(path) == reason


def test_privacy_reason_dotted_internal_segments():
    assert rd.privacy_reason("pandas.io.formats.style.Styler", ["io.formats"]) == "internal"
    assert rd.privacy_reason("pandas.io.parsers.read_csv", ["io.formats"]) is None


def test_is_private_segment():
    assert rd.is_private_segment("_x")
    assert rd.is_private_segment("__x")
    assert not rd.is_private_segment("__init__")
    assert not rd.is_private_segment("x")


# ---------------------------------------------------------------- public path mapping


def test_public_index_maps_canonical_to_reexport_and_follows_chains():
    edges = [("pkg.Frame", "pkg.core.api.Frame"), ("pkg.core.api.Frame", "pkg.core.frame.Frame")]
    idx = rd.build_public_index(edges, ["pkg.core.frame.Frame", "pkg.io.read"], ["core"])
    assert idx["pkg.core.frame.Frame"][0] == "pkg.Frame"
    assert rd.public_path_for("pkg.core.frame.Frame.to_csv", idx, ["core"]) == "pkg.Frame.to_csv"
    assert rd.public_path_for("pkg.core.frame.Frame.__init__", idx, ["core"]) == "pkg.Frame.__init__"
    assert rd.public_path_for("pkg.io.read", idx, ["core"]) == "pkg.io.read"


def test_public_path_prefers_shortest_spelling_even_if_method_indexed():
    idx = rd.build_public_index([("click.Option", "click.core.Option")],
                                ["click.core.Option", "click.core.Option.__init__"], [])
    assert rd.public_path_for("click.core.Option.__init__", idx, []) == "click.Option.__init__"


def test_public_path_none_for_private_or_internal_only():
    idx = rd.build_public_index([], ["pkg.core.thing"], ["core"])
    assert rd.public_path_for("pkg.core.thing", idx, ["core"]) is None
    assert rd.public_path_for("pkg.Cls._private_method", {"pkg.Cls": ["pkg.Cls"]}, []) is None
    assert rd.public_path_for("pkg.Cls.__repr__", {"pkg.Cls": ["pkg.Cls"]}, []) is None


# ---------------------------------------------------------------- classification


def test_classify_maps_griffe_kinds():
    assert rd.classify({"kind": "ATTRIBUTE_CHANGED_VALUE", "path": "p.__version__"}) is None
    assert rd.classify({"kind": "OBJECT_REMOVED", "path": "p.f"})["category"] == rd.REMOVED_SYMBOL
    c = rd.classify({"kind": "PARAMETER_ADDED_REQUIRED", "path": "p.f", "param": "x"})
    assert (c["category"], c["failure_mode"]) == (rd.NEW_REQUIRED_PARAMETER, "hard")
    c = rd.classify({"kind": "PARAMETER_CHANGED_DEFAULT", "path": "p.f", "param": "x"})
    assert (c["category"], c["failure_mode"]) == (rd.CHANGED_DEFAULT, "soft")
    c = rd.classify({"kind": "PARAMETER_CHANGED_KIND", "path": "p.f", "param": "x",
                     "old_value": "positional or keyword", "new_value": "keyword-only"})
    assert c["category"] == rd.CHANGED_PARAMETER_KIND


def test_classify_detects_rename():
    c = rd.classify({"kind": "PARAMETER_REMOVED", "path": "np.trapezoid", "param": "dx",
                     "old_params": ["y", "x", "dx", "axis"], "new_params": ["y", "x", "delta", "axis"]})
    assert c["category"] == rd.RENAMED_PARAMETER
    assert c["renamed_to"] == "delta"
    c = rd.classify({"kind": "PARAMETER_REMOVED", "path": "f", "param": "regex",
                     "old_params": ["a", "regex"], "new_params": ["a"]})
    assert c["category"] == rd.REMOVED_PARAMETER


@pytest.mark.parametrize("removed,old,new,expected", [
    ("allow_redirects", ["url", "allow_redirects"], ["url", "follow_redirects"], "follow_redirects"),
    ("min_items", ["t", "min_items"], ["t", "strict", "min_length"], "min_length"),
    ("foo", ["foo"], ["bar"], "bar"),                   # same position, only new parameter
    ("verbose", ["a", "verbose"], ["a"], None),          # pure removal
    ("color", ["x", "color"], ["x", "y", "zzzz"], None),  # nothing similar
])
def test_detect_rename(removed, old, new, expected):
    assert rd.detect_rename(removed, old, new) == expected


# ---------------------------------------------------------------- changelog + scoring + filtering


def test_changelog_mentions_whole_words_only():
    cand = {"public_path": "numpy.trapz", "param": None}
    assert rd.changelog_mentions(cand, ["``np.trapz`` has been removed"]) == ["trapz"]
    assert rd.changelog_mentions(cand, ["trapzoid things"]) == []
    cand = {"public_path": "pandas.DataFrame.to_csv", "param": "line_terminator"}
    assert rd.changelog_mentions(cand, ["removed line_terminator from to_csv"]) == ["line_terminator", "to_csv"]
    # parameter and function must co-occur in one paragraph
    assert rd.changelog_mentions(cand, ["line_terminator was removed", "to_csv is fast"]) == []


def test_changelog_mentions_class_member_needs_class_name():
    cand = {"public_path": "sqlalchemy.Select.select", "param": None}
    assert rd.changelog_mentions(cand, ["use :func:`_sql.select` instead"]) == []
    assert rd.changelog_mentions(cand, ["The ``Select.select()`` method was removed"]) == ["Select", "select"]


@pytest.mark.parametrize("text,old_tag,kept", [
    ("## 0.120.0\nnew stuff\n## 0.119.1 (2025-10-20)\nold stuff", "0.119.1", "new stuff"),
    ("pytest 9.0.0\nnew\npytest 8.4.2 (2025-09-03)\nold", "8.4.2", "new"),
    ("## Version 8.5.0\nnew\n## Version 8.4.2\nold", "8.4.2", "new"),
    ("## v2.14.0\nnew\n## v2.13.4 (2026-05-06)\nold", "v2.13.5", "new"),
    ("Full Changelog: v0.125.0...v1.0.0\nnew\n## 0.125.0 (2026)\nold", "v0.125.0", "new"),
    ("Upgrade to\n2.3 to get warnings (prose, not a heading)\nnew", "v2.3.3", "new"),
])
def test_trim_changelog(text, old_tag, kept):
    out = rd.trim_changelog(text, old_tag)
    assert kept in out and "\nold" not in out


def test_score_orders_hard_public_hot_above_soft_deep():
    hard = rd.classify({"kind": "OBJECT_REMOVED", "path": "numpy.trapz"})
    hard.update(public_path="numpy.trapz", flags=[], changelog_mentions=["trapz"])
    soft = rd.classify({"kind": "PARAMETER_CHANGED_DEFAULT", "path": "numpy.lib.mod.Cls.meth", "param": "x"})
    soft.update(public_path="numpy.lib.mod.Cls.meth", flags=[], changelog_mentions=[])
    assert rd.score(hard, ["trapz"]) > rd.score(soft, ["trapz"])
    moved = dict(hard, flags=["reexported_elsewhere"])
    assert rd.score(moved, ["trapz"]) < rd.score(hard, ["trapz"])


def test_filter_and_rank_end_to_end():
    raws = [
        {"kind": "OBJECT_REMOVED", "path": "pkg.trapz"},
        {"kind": "OBJECT_REMOVED", "path": "pkg.moved_fn", "canonical": "pkg.impl.moved_fn"},  # moved
        {"kind": "OBJECT_REMOVED", "path": "pkg.core.frame.Frame.append"},
        {"kind": "OBJECT_REMOVED", "path": "pkg._private"},
        {"kind": "OBJECT_REMOVED", "path": "pkg.tests.helper"},
        {"kind": "ATTRIBUTE_CHANGED_VALUE", "path": "pkg.__version__"},
        {"kind": "PARAMETER_REMOVED", "path": "pkg.core.frame.Frame.to_csv", "param": "_internal"},
        {"kind": "PARAMETER_REMOVED", "path": "pkg.core.frame.Frame.to_csv", "param": "line_terminator",
         "old_params": ["self", "path", "line_terminator"], "new_params": ["self", "path", "lineterminator"]},
        {"kind": "OBJECT_REMOVED", "path": "pkg.shimmed"},
        {"kind": "PARAMETER_CHANGED_DEFAULT", "path": "pkg.trapz", "param": "dx", "old_value": "...",
         "new_value": "1.0"},
        {"kind": "PARAMETER_CHANGED_DEFAULT", "path": "pkg.trapz", "param": "x", "old_value": "notset",
         "new_value": "NOTSET"},
        {"kind": "PARAMETER_CHANGED_DEFAULT", "path": "pkg.trapz", "param": "y", "old_value": "'l2'",
         "new_value": "'deprecated'"},
        {"kind": "PARAMETER_REMOVED", "path": "pkg.Frame.__new__", "param": "subtype",
         "old_value": "positional or keyword", "old_params": ["subtype", "shape"], "new_params": ["cls", "shape"]},
        {"kind": "PARAMETER_REMOVED", "path": "pkg.trapz", "param": "hints",
         "old_value": "variadic keyword", "old_params": ["hints"], "new_params": ["instance"]},
    ]
    index = rd.build_public_index([("pkg.Frame", "pkg.core.frame.Frame")], ["pkg.trapz", "pkg.moved_fn",
                                  "pkg.shimmed"], ["core"])
    new_index = {"pkg.impl.moved_fn": ["pkg.sub.moved_fn"], "pkg.other.trapz": ["pkg.other.trapz"]}
    cands, dropped = rd.filter_and_rank(raws, public_index=index, new_index=new_index,
                                        getattr_modules={"pkg": {"shimmed"}}, internal=["core"],
                                        hot_symbols=["Frame"], changelog_text="line_terminator was removed")
    by_path = {(c["public_path"], c.get("param")): c for c in cands}
    assert ("pkg.trapz", None) in by_path
    assert ("pkg.Frame.append", None) in by_path
    renamed = by_path[("pkg.Frame.to_csv", "line_terminator")]
    assert renamed["category"] == rd.RENAMED_PARAMETER and renamed["renamed_to"] == "lineterminator"
    assert renamed["changelog_mentions"] == []  # 'to_csv' not in the same paragraph
    assert "reexported_elsewhere" in by_path[("pkg.moved_fn", None)]["flags"]
    assert by_path[("pkg.moved_fn", None)]["still_exported_as"] == ["pkg.sub.moved_fn"]
    shim = by_path[("pkg.shimmed", None)]
    assert "module_getattr_shim" in shim["flags"] and shim["failure_mode"] == "shim"
    assert dropped["attribute_changed_value"] == 1
    assert dropped["stub_default"] == 1
    assert dropped["sentinel_rename"] == 1
    assert dropped["deprecation_sentinel"] == 1
    assert dropped["variadic_parameter"] == 2
    # same name elsewhere is not "moved" unless it is the same canonical object
    assert "reexported_elsewhere" not in by_path[("pkg.trapz", None)]["flags"]
    assert dropped["private_parameter"] == 1
    assert dropped.get("private") == 1 and dropped.get("test") == 1
    # top candidate is the renamed hot-path parameter confirmed by the changelog
    assert cands[0]["public_path"] == "pkg.Frame.to_csv"
    scores = [c["score"] for c in cands]
    assert scores == sorted(scores, reverse=True)


def test_filter_dedupes_and_limits():
    raws = [{"kind": "OBJECT_REMOVED", "path": f"pkg.f{i}"} for i in range(10)]
    raws += [{"kind": "OBJECT_REMOVED", "path": "pkg.f0"}]
    cands, dropped = rd.filter_and_rank(raws, public_index={}, limit=5)
    assert len(cands) == 5
    assert dropped["duplicate"] == 1
    assert dropped["over_limit"] == 5


@pytest.mark.parametrize("old,new,expected", [
    ("notset", "NOTSET", True), ("NOT_SET", "NOTSET", True), ("_pytest.compat.NOTSET", "NOTSET", True),
    ("None", "0", False), ("'l2'", "'L2'", False), (None, "x", False),
])
def test_is_sentinel_rename(old, new, expected):
    assert rd.is_sentinel_rename(old, new) is expected


def test_classes_with_external_base_follows_hierarchy():
    bases = {"fastapi.params.Param": ["pydantic.fields.FieldInfo"], "fastapi.params.Query": ["fastapi.params.Param"],
             "fastapi.Other": ["object"], "fastapi.Enumish": ["enum.Enum"]}
    assert rd.classes_with_external_base(bases, ["fastapi"]) == {"fastapi.params.Param", "fastapi.params.Query"}


def test_removed_reexports():
    old = [("click.BaseCommand", "click.core.BaseCommand"), ("click.Option", "click.core.Option")]
    new = [("click.Option", "click.core.Option")]
    raws = rd.removed_reexports(old, new, ["click.core.Command"])
    assert [r["path"] for r in raws] == ["click.BaseCommand"]
    assert raws[0]["kind"] == "OBJECT_REMOVED"


# ---------------------------------------------------------------- misc helpers / data files


def test_output_path_uses_versions():
    assert rd.output_path("sqlalchemy", "rel_2_0_54", "rel_2_1_0").name == "sqlalchemy-2.0.54-2.1.0.json"
    assert rd.output_path("langchain-core", "langchain-core==0.3.79", "langchain-core==1.0.0").name \
        == "langchain-core-0.3.79-1.0.0.json"


def test_watchlist_parses_and_is_consistent():
    yaml = pytest.importorskip("yaml")  # noqa: F841
    libs = rd.load_watchlist()
    assert len(libs) >= 10
    for cfg in libs.values():
        assert cfg.repo.startswith("https://github.com/")
        assert cfg.packages and cfg.releases
        for rel in cfg.releases:
            assert rel["old"] != rel["new"]


def test_candidate_files_are_wellformed_data():
    files = sorted((ROOT / "pipeline" / "candidates").glob("*.json"))
    if not files:
        pytest.skip("no candidate outputs committed")
    for f in files:
        d = json.loads(f.read_text())
        assert d["kind"] == "mend-release-diff-candidates"
        assert len(d["candidates"]) <= 200
        for c in d["candidates"]:
            assert c["category"] and c["public_path"] and c["failure_mode"] in {"hard", "soft", "none", "shim"}


def test_griffe_integration_on_tiny_package(tmp_path):
    """Optional: only when griffe is importable (e.g. MEND_GRIFFE_PATH set)."""
    import os
    gp = os.environ.get("MEND_GRIFFE_PATH")
    if gp and gp not in sys.path:
        sys.path.insert(0, gp)
    griffe = pytest.importorskip("griffe")
    for ver, body in (("old", "def f(a, b=1): ...\ndef g(): ...\n"), ("new", "def f(a, *, c): ...\n")):
        (tmp_path / ver / "tinypkg").mkdir(parents=True)
        (tmp_path / ver / "tinypkg" / "__init__.py").write_text("__all__ = ['f', 'g']\n" + body)
    kw = dict(allow_inspection=False, try_relative_path=False)
    old = griffe.load("tinypkg", search_paths=[str(tmp_path / "old")], **kw)
    new = griffe.load("tinypkg", search_paths=[str(tmp_path / "new")], **kw)
    raws = rd.griffe_breakages(griffe, old, new, [])
    kinds = {(r["kind"], r.get("param")) for r in raws}
    assert ("OBJECT_REMOVED", None) in kinds
    assert ("PARAMETER_REMOVED", "b") in kinds
    assert ("PARAMETER_ADDED_REQUIRED", "c") in kinds
