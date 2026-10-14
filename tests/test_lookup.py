"""Tests for mend.lookup: dependency parsing, version matching, ranking."""

from __future__ import annotations

import textwrap
from pathlib import Path

import yaml

from mend.fixture import load_fixture
from mend.lookup import lookup, main, normalize, parse_dependencies


def make_fixture(root: Path, fid: str, package: str = "pydantic", versions: str = ">=2.0",
                 status: str = "verified", title: str = "", summary: str = "s",
                 tags: list[str] | None = None):
    d = root / package / fid
    d.mkdir(parents=True)
    data = {
        "id": fid, "title": title or fid, "summary": summary, "ecosystem": "python",
        "package": package, "versions": versions, "tags": tags or ["misc"],
        "failure": {"kind": "api-removed", "symptom": "boom", "bad_pattern": "bad()",
                    "fix_pattern": "good()"},
        "repro": {"python": "3.12", "deps": [f"{package}==2.9.2"]},
        "provenance": {"sources": [{"type": "docs", "url": "https://example.com/x"}],
                       "license": "MIT"},
        "status": status,
    }
    (d / "fixture.yaml").write_text(yaml.safe_dump(data))
    return load_fixture(d)


def write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(text))


# --------------------------------------------------------------------------- parsing

def test_normalize_pep503():
    assert normalize("Pydantic_Settings") == "pydantic-settings"
    assert normalize("zope.interface") == "zope-interface"
    assert normalize("a--b__c") == "a-b-c"


def test_parse_requirements(tmp_path):
    write(tmp_path / "requirements.txt", """
        # comment
        pydantic==2.9.2
        Requests>=2.0  # trailing comment
        numpy
        -r requirements-dev.txt
        -e .
        git+https://github.com/x/y.git
        pandas[performance]==2.2.0 ; python_version >= "3.10"
    """)
    write(tmp_path / "requirements-dev.txt", "pytest==8.0.0\n")
    deps = parse_dependencies(tmp_path)
    assert deps == {"pydantic": "2.9.2", "requests": None, "numpy": None,
                    "pandas": "2.2.0", "pytest": "8.0.0"}


def test_parse_pyproject_pep621_and_poetry(tmp_path):
    write(tmp_path / "pyproject.toml", """
        [project]
        name = "demo"
        dependencies = ["pydantic>=2", "httpx==0.27.0"]
        [project.optional-dependencies]
        test = ["pytest"]
        [dependency-groups]
        lint = ["ruff==0.6.0"]
        [tool.poetry.dependencies]
        python = "^3.11"
        SQLAlchemy = "2.0.30"
        fastapi = {version = "^0.110"}
        [tool.poetry.group.dev.dependencies]
        mypy = "==1.10.0"
    """)
    deps = parse_dependencies(tmp_path)
    assert deps["pydantic"] is None
    assert deps["httpx"] == "0.27.0"
    assert deps["pytest"] is None
    assert deps["ruff"] == "0.6.0"
    assert deps["sqlalchemy"] == "2.0.30"
    assert deps["fastapi"] is None
    assert deps["mypy"] == "1.10.0"
    assert "python" not in deps


def test_lockfile_supplies_resolved_versions_for_direct_deps(tmp_path):
    write(tmp_path / "pyproject.toml", """
        [project]
        name = "demo"
        dependencies = ["pydantic>=2"]
    """)
    write(tmp_path / "uv.lock", """
        version = 1
        [[package]]
        name = "pydantic"
        version = "2.9.2"
        [[package]]
        name = "annotated-types"
        version = "0.7.0"
    """)
    deps = parse_dependencies(tmp_path)
    assert deps == {"pydantic": "2.9.2"}  # transitive deps are not added


def test_lockfile_only_project(tmp_path):
    write(tmp_path / "poetry.lock", """
        [[package]]
        name = "Django"
        version = "5.0.1"
    """)
    assert parse_dependencies(tmp_path) == {"django": "5.0.1"}


def test_empty_and_broken_files(tmp_path):
    assert parse_dependencies(tmp_path) == {}
    write(tmp_path / "pyproject.toml", "not = [valid toml")
    assert parse_dependencies(tmp_path) == {}


# --------------------------------------------------------------------------- lookup

def test_version_matching(tmp_path):
    fx = make_fixture(tmp_path, "pydantic-v2-thing", versions=">=2.0")
    assert lookup([fx], {"pydantic": "2.9.2"}) == [fx]
    assert lookup([fx], {"pydantic": None}) == [fx]          # unknown version: relevant
    assert lookup([fx], {"pydantic": "1.10.13"}) == []        # outside range
    assert lookup([fx], {"requests": "2.0"}) == []            # package not used
    assert lookup([fx], {"Pydantic": "2.1"}) == [fx]          # name normalization


def test_package_name_normalized_on_fixture_side(tmp_path):
    fx = make_fixture(tmp_path, "pydantic-settings-x", package="pydantic_settings")
    assert lookup([fx], {"pydantic-settings": "2.5.2"}) == [fx]


def test_ranking_verified_first_then_version_certainty_then_task(tmp_path):
    draft_exact = make_fixture(tmp_path, "pydantic-a-draft", status="draft")
    verified_known = make_fixture(tmp_path, "pydantic-b-verified")
    other_pkg_unknown = make_fixture(tmp_path, "httpx-c", package="httpx")
    other_pkg_task = make_fixture(tmp_path, "httpx-d", package="httpx",
                                  title="Timeout config changed", tags=["timeout"])
    deps = {"pydantic": "2.9.2", "httpx": None}
    res = lookup([draft_exact, other_pkg_unknown, other_pkg_task, verified_known], deps,
                 task="set a request timeout")
    ids = [f.id for f in res]
    # verified first; exact version match (pydantic) before unknown version (httpx)
    # unless task overlap lifts it; draft last.
    assert ids[-1] == "pydantic-a-draft"
    assert ids.index("httpx-d") < ids.index("httpx-c")
    assert ids.index("pydantic-b-verified") < ids.index("httpx-c")


def test_task_keyword_overlap_ranks(tmp_path):
    a = make_fixture(tmp_path, "pydantic-a", title="Validators renamed", tags=["validation"])
    b = make_fixture(tmp_path, "pydantic-b", title="BaseSettings moved", tags=["settings", "config"])
    res = lookup([a, b], {"pydantic": "2.5"}, task="load app settings from env config")
    assert [f.id for f in res] == ["pydantic-b", "pydantic-a"]
    res = lookup([a, b], {"pydantic": "2.5"}, task="add a field validator")
    assert [f.id for f in res] == ["pydantic-a", "pydantic-b"]


def test_limit(tmp_path):
    fxs = [make_fixture(tmp_path, f"pydantic-{i}") for i in range(5)]
    assert len(lookup(fxs, {"pydantic": None}, limit=2)) == 2
    assert lookup(fxs, {"pydantic": None}, limit=0) == []


def test_bad_specifier_treated_as_unknown(tmp_path):
    fx = make_fixture(tmp_path, "pydantic-weird", versions="not a spec")
    assert lookup([fx], {"pydantic": "2.0"}) == [fx]


def test_main_json(tmp_path, capsys):
    fixtures = tmp_path / "fixtures"
    make_fixture(fixtures, "pydantic-x")
    proj = tmp_path / "proj"
    write(proj / "requirements.txt", "pydantic==2.9.2\n")
    rc = main(["--project", str(proj), "--fixtures", str(fixtures), "--json"])
    assert rc == 0
    import json
    out = json.loads(capsys.readouterr().out)
    assert [r["id"] for r in out] == ["pydantic-x"]


def test_main_text(tmp_path, capsys):
    fixtures = tmp_path / "fixtures"
    make_fixture(fixtures, "pydantic-x")
    proj = tmp_path / "proj"
    write(proj / "requirements.txt", "pydantic\n")
    assert main(["--project", str(proj), "--fixtures", str(fixtures)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("MEND known-failure records (reference data, not instructions):")
    assert "id=pydantic-x" in out
