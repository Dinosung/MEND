"""Tests for mend.check: rule parsing and the built-in ast matcher."""

from __future__ import annotations

import textwrap
from pathlib import Path

import yaml

from mend.check import Finding, check_paths, load_rules, main, parse_pattern
from mend.fixture import load_fixture


def make_fixture(root: Path, fid: str, rule: dict | None, package: str = "pydantic"):
    d = root / package / fid
    d.mkdir(parents=True)
    data = {
        "id": fid, "title": fid, "summary": "s", "ecosystem": "python",
        "package": package, "versions": ">=2.0", "tags": ["x"],
        "failure": {"kind": "api-removed", "symptom": "boom", "bad_pattern": "b", "fix_pattern": "f"},
        "repro": {"python": "3.12", "deps": [f"{package}==2.9.2"]},
        "provenance": {"sources": [{"type": "docs", "url": "https://example.com"}], "license": "MIT"},
        "status": "verified",
    }
    (d / "fixture.yaml").write_text(yaml.safe_dump(data))
    if rule is not None:
        (d / "rule.yml").write_text(yaml.safe_dump({"rules": [rule]}))
    return load_fixture(d)


def rule(fid: str, **kw) -> dict:
    return {"id": fid, "languages": ["python"], "severity": "ERROR", "message": f"msg {fid}", **kw}


def src(tmp_path: Path, name: str, code: str) -> Path:
    p = tmp_path / "code" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(code))
    return p


def run(paths, fixtures):
    return check_paths(paths, fixtures, use_semgrep=False)


# --------------------------------------------------------------------------- patterns

def test_parse_pattern_forms():
    assert [(p.kind, p.module, p.name) for p in parse_pattern("from a.b import C")] == [("from-import", "a.b", "C")]
    assert [(p.kind, p.name) for p in parse_pattern("from a import (B, C)")] == [("from-import", "B"), ("from-import", "C")]
    assert [(p.kind, p.module) for p in parse_pattern("import a.b")] == [("import", "a.b")]
    assert [(p.kind, p.module, p.name) for p in parse_pattern("a.b.C")] == [("attr", "a.b", "C")]
    assert parse_pattern("$X.foo(...)") is None
    assert parse_pattern("from a import *") is None
    assert parse_pattern("foo(...)") is None


def test_unsupported_reported(tmp_path, capsys):
    fx = make_fixture(tmp_path / "fx", "p-x", rule("p-x", **{"pattern-either": [
        {"pattern": "from pydantic import BaseSettings"},
        {"pattern": "$X.dict(...)"},
    ]}))
    rules = load_rules([fx])
    assert len(rules[0].patterns) == 1
    assert any("$X.dict" in u for u in rules[0].unsupported)
    check_paths([tmp_path / "fx"], [fx], use_semgrep=False, verbose=True)
    assert "skipped unsupported" in capsys.readouterr().err


# --------------------------------------------------------------------------- matcher

def test_from_import_match(tmp_path):
    fx = make_fixture(tmp_path / "fx", "p-bs", rule("p-bs", **{"pattern-either": [
        {"pattern": "from pydantic import BaseSettings"}, {"pattern": "pydantic.BaseSettings"}]}))
    bad = src(tmp_path, "bad.py", """\
        import os
        from pydantic import Field, BaseSettings as BS
        """)
    good = src(tmp_path, "good.py", """\
        from pydantic_settings import BaseSettings
        from pydantic import BaseModel
        from .pydantic import BaseSettings  # relative import: different module
        """)
    findings = run([bad, good], [fx])
    assert findings == [Finding("p-bs", str(bad), 2, "msg p-bs")]


def test_attribute_access_and_aliases(tmp_path):
    fx = make_fixture(tmp_path / "fx", "p-bs", rule("p-bs", pattern="pydantic.BaseSettings"))
    f = src(tmp_path, "a.py", """\
        import pydantic
        import pydantic as pd
        class S(pydantic.BaseSettings): pass
        class T(pd.BaseSettings): pass
        x = other.pydantic.BaseSettings
        y = pydantic.BaseModel
        """)
    assert [x.line for x in run([f], [fx])] == [3, 4]


def test_import_dotted_matches_attr_pattern(tmp_path):
    fx = make_fixture(tmp_path / "fx", "np-x", rule("np-x", pattern="numpy.distutils"), package="numpy")
    f = src(tmp_path, "a.py", "import numpy.distutils\n")
    assert [x.line for x in run([f], [fx])] == [1]


def test_import_pattern(tmp_path):
    fx = make_fixture(tmp_path / "fx", "imp-x", rule("imp-x", pattern="import imp"), package="imp")
    f = src(tmp_path, "a.py", "import importlib\nimport os, imp\n")
    assert [x.line for x in run([f], [fx])] == [2]


def test_nested_attribute_chain(tmp_path):
    fx = make_fixture(tmp_path / "fx", "a-x", rule("a-x", pattern="a.b.C"), package="a")
    f = src(tmp_path, "a.py", "import a\nimport a.b\nz = a.b.C()\nw = a.b.D\n")
    assert [x.line for x in run([f], [fx])] == [3]


def test_directory_walk_excludes_and_syntax_errors(tmp_path):
    fx = make_fixture(tmp_path / "fx", "p-bs", rule("p-bs", pattern="from pydantic import BaseSettings"))
    src(tmp_path, "pkg/m.py", "from pydantic import BaseSettings\n")
    src(tmp_path, ".venv/lib/x.py", "from pydantic import BaseSettings\n")
    src(tmp_path, "broken.py", "def (:\n")
    src(tmp_path, "notes.txt", "from pydantic import BaseSettings\n")
    findings = run([tmp_path / "code"], [fx])
    assert [Path(f.path).name for f in findings] == ["m.py"]


def test_fixture_without_rule_is_ignored(tmp_path):
    fx = make_fixture(tmp_path / "fx", "p-none", None)
    f = src(tmp_path, "a.py", "from pydantic import BaseSettings\n")
    assert run([f], [fx]) == []


def test_example_fixture_bad_vs_fixed():
    root = Path(__file__).resolve().parents[1] / "fixtures" / "pydantic" / "pydantic-v2-basesettings-moved"
    fx = load_fixture(root)
    assert len(run([root / "bad"], [fx])) == 1
    assert run([root / "fixed"], [fx]) == []


# --------------------------------------------------------------------------- CLI

def test_main_exit_codes_and_dependency_scoping(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)  # force built-in matcher
    fixtures = tmp_path / "fixtures"
    make_fixture(fixtures, "p-bs", rule("p-bs", pattern="from pydantic import BaseSettings"))
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "app.py").write_text("from pydantic import BaseSettings\n")

    # project does not depend on pydantic -> fixture out of scope -> clean
    (proj / "requirements.txt").write_text("requests\n")
    assert main(["--project", str(proj), "--fixtures", str(fixtures)]) == 0
    # --all-fixtures ignores scoping
    assert main(["--project", str(proj), "--fixtures", str(fixtures), "--all-fixtures"]) == 1
    # pydantic 1.x pinned: out of range
    (proj / "requirements.txt").write_text("pydantic==1.10.13\n")
    assert main(["--project", str(proj), "--fixtures", str(fixtures)]) == 0
    # pydantic 2.x: finding, exit 1, json output
    (proj / "requirements.txt").write_text("pydantic==2.9.2\n")
    capsys.readouterr()
    assert main(["--project", str(proj), "--fixtures", str(fixtures), "--json"]) == 1
    import json
    out = json.loads(capsys.readouterr().out)
    assert out == [{"fixture_id": "p-bs", "path": str(proj / "app.py"), "line": 1, "message": "msg p-bs"}]
