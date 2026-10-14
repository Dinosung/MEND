from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from mend import fixture as fx_mod
from mend.fixture import Fixture, FixtureError, load_all, load_fixture, validate, validate_all

REPO = Path(__file__).resolve().parents[1]
FID = "demo-thing-moved"


def base_meta(**overrides: Any) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "id": FID,
        "title": "Using demo.thing after it moved",
        "summary": "demo 2.0 moved `thing` to demo.extras.",
        "ecosystem": "python",
        "package": "demo",
        "versions": ">=2.0",
        "tags": ["imports"],
        "failure": {
            "kind": "api-removed",
            "symptom": "ImportError: cannot import name 'thing'",
            "bad_pattern": "from demo import thing",
            "fix_pattern": "from demo.extras import thing",
        },
        "repro": {"python": "3.12", "deps": ["demo==2.1.0"]},
        "provenance": {"sources": [{"type": "docs", "url": "https://example.org/demo/migration"}], "license": "MIT"},
        "status": "verified",
    }
    meta.update(overrides)
    return meta


def make_fixture(
    root: Path,
    meta: dict[str, Any] | None = None,
    *,
    dirname: str | None = None,
    package_dir: str = "demo",
    files: dict[str, str] | None = None,
    skip: tuple[str, ...] = (),
) -> Path:
    meta = base_meta() if meta is None else meta
    d = root / package_dir / (dirname or str(meta.get("id", FID)))
    d.mkdir(parents=True)
    (d / "fixture.yaml").write_text(yaml.safe_dump(meta, sort_keys=False))
    defaults = {
        "bad/target.py": "from demo import thing\n",
        "fixed/target.py": "from demo.extras import thing\n",
        "check/test_check.py": "def test_it():\n    import target\n",
    }
    defaults.update(files or {})
    for rel, text in defaults.items():
        if rel in skip:
            continue
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return d


def errors_for(tmp_path: Path, meta: dict[str, Any] | None = None, **kw: Any) -> list[str]:
    return validate(load_fixture(make_fixture(tmp_path, meta, **kw)))


def assert_error(errors: list[str], fragment: str) -> None:
    assert any(fragment in e for e in errors), f"{fragment!r} not in {errors}"


# --------------------------------------------------------------------------- loading


def test_load_fixture_maps_fields(tmp_path: Path) -> None:
    d = make_fixture(tmp_path)
    fx = load_fixture(d)
    assert isinstance(fx, Fixture)
    assert fx.id == FID and fx.package == "demo" and fx.tags == ["imports"]
    assert fx.failure.kind == "api-removed"
    assert fx.repro.python == "3.12" and fx.repro.deps == ["demo==2.1.0"]
    assert fx.provenance.sources[0].url == "https://example.org/demo/migration"
    assert fx.path == d.resolve()
    assert fx.bad_dir == d.resolve() / "bad" and fx.rule_path is None
    assert validate(fx) == []


def test_load_fixture_accepts_yaml_path(tmp_path: Path) -> None:
    d = make_fixture(tmp_path)
    assert load_fixture(d / "fixture.yaml").path == d.resolve()


def test_to_dict_is_json_serialisable(tmp_path: Path) -> None:
    data = load_fixture(make_fixture(tmp_path)).to_dict()
    assert json.loads(json.dumps(data))["failure"]["kind"] == "api-removed"
    assert "extra" not in data and "load_errors" not in data


def test_unquoted_python_version_is_rejected(tmp_path: Path) -> None:
    meta = base_meta(repro={"python": 3.10, "deps": ["demo==2.1.0"]})
    assert_error(errors_for(tmp_path, meta), "quoted string")


def test_load_fixture_invalid_yaml(tmp_path: Path) -> None:
    (tmp_path / "fixture.yaml").write_text("id: [unclosed\n")
    with pytest.raises(FixtureError, match="invalid YAML"):
        load_fixture(tmp_path)


def test_load_fixture_non_mapping(tmp_path: Path) -> None:
    (tmp_path / "fixture.yaml").write_text("- a\n- b\n")
    with pytest.raises(FixtureError, match="mapping"):
        load_fixture(tmp_path)


def test_load_fixture_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FixtureError, match="cannot read"):
        load_fixture(tmp_path)


def test_load_all_finds_nested_sorted(tmp_path: Path) -> None:
    make_fixture(tmp_path, base_meta(id="demo-b", package="demo"), package_dir="demo")
    make_fixture(tmp_path, base_meta(id="demo-a"), package_dir="demo")
    make_fixture(tmp_path, base_meta(id="demo-hidden"), package_dir=".git")
    ids = [f.id for f in load_all(tmp_path)]
    assert ids == ["demo-a", "demo-b"]


def test_load_all_missing_root_is_empty(tmp_path: Path) -> None:
    assert load_all(tmp_path / "nope") == []


def test_load_all_relative_to_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    make_fixture(tmp_path / "fixtures")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MEND_FIXTURES_DIR", raising=False)
    assert [f.id for f in load_all()] == [FID]


def test_load_all_env_var_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    make_fixture(tmp_path / "catalog")
    empty = tmp_path / "elsewhere"
    empty.mkdir()
    monkeypatch.chdir(empty)
    monkeypatch.setenv("MEND_FIXTURES_DIR", str(tmp_path / "catalog"))
    assert [f.id for f in load_all()] == [FID]
    assert [f.id for f in load_all(None)] == [FID]


# --------------------------------------------------------------------------- validation


def test_missing_required_fields(tmp_path: Path) -> None:
    meta = base_meta()
    for key in ("title", "summary", "tags"):
        del meta[key]
    errs = errors_for(tmp_path, meta)
    for key in ("title", "summary", "tags"):
        assert_error(errs, f"missing required field '{key}'")


def test_missing_nested_fields(tmp_path: Path) -> None:
    meta = base_meta(failure={"kind": "api-removed"}, repro={"deps": ["demo==2.1.0"]})
    errs = errors_for(tmp_path, meta)
    assert_error(errs, "failure.symptom")
    assert_error(errs, "failure.bad_pattern")
    assert_error(errs, "repro.python")


def test_id_must_match_directory(tmp_path: Path) -> None:
    assert_error(errors_for(tmp_path, dirname="demo-other-name"), "must equal directory name")


def test_id_must_be_kebab_case(tmp_path: Path) -> None:
    assert_error(errors_for(tmp_path, base_meta(id="demo_Bad_Id")), "kebab-case")


def test_id_must_be_prefixed_with_package(tmp_path: Path) -> None:
    assert_error(errors_for(tmp_path, base_meta(id="other-thing")), "prefixed with the package")


@pytest.mark.parametrize("kind", ["api-removed", "api-renamed", "signature-changed", "behavior-changed", "deprecated-broken"])
def test_valid_kinds(tmp_path: Path, kind: str) -> None:
    meta = base_meta()
    meta["failure"]["kind"] = kind
    assert errors_for(tmp_path, meta) == []


def test_invalid_kind(tmp_path: Path) -> None:
    meta = base_meta()
    meta["failure"]["kind"] = "typo"
    assert_error(errors_for(tmp_path, meta), "failure.kind 'typo'")


def test_invalid_status(tmp_path: Path) -> None:
    assert_error(errors_for(tmp_path, base_meta(status="done")), "status 'done'")


def test_draft_status_ok(tmp_path: Path) -> None:
    assert errors_for(tmp_path, base_meta(status="draft")) == []


def test_invalid_ecosystem(tmp_path: Path) -> None:
    assert_error(errors_for(tmp_path, base_meta(ecosystem="npm")), "ecosystem 'npm'")


def test_invalid_versions_specifier(tmp_path: Path) -> None:
    assert_error(errors_for(tmp_path, base_meta(versions="two point oh")), "PEP 440")


@pytest.mark.parametrize("dep", ["demo>=2.1", "demo", "demo==2.*", "demo==2.1.0; python_version>'3'", "not a req!!"])
def test_deps_must_be_exact_pins(tmp_path: Path, dep: str) -> None:
    meta = base_meta(repro={"python": "3.12", "deps": [dep]})
    assert_error(errors_for(tmp_path, meta), "repro.deps")


def test_deps_must_include_package(tmp_path: Path) -> None:
    meta = base_meta(repro={"python": "3.12", "deps": ["other==1.0"]})
    assert_error(errors_for(tmp_path, meta), "must pin the fixture package")


def test_deps_pin_must_be_in_versions_range(tmp_path: Path) -> None:
    meta = base_meta(repro={"python": "3.12", "deps": ["demo==1.9"]})
    assert_error(errors_for(tmp_path, meta), "outside versions")


def test_package_name_normalised_in_deps(tmp_path: Path) -> None:
    meta = base_meta(
        id="demo-settings-x", package="demo-settings",
        repro={"python": "3.12", "deps": ["Demo_Settings==2.0"]},
    )  # fmt: skip
    assert errors_for(tmp_path, meta) == []


def old_meta(old_deps: list[str], **repro: Any) -> dict[str, Any]:
    return base_meta(repro={"python": "3.12", "deps": ["demo==2.1.0"], "old_deps": old_deps, **repro})


def test_load_old_deps_and_released(tmp_path: Path) -> None:
    meta = old_meta(["demo==1.9.0", "httpx==0.28.1"], old_python="3.11")
    meta["provenance"]["released"] = "2024-06-16"
    fx = load_fixture(make_fixture(tmp_path, meta))
    assert fx.repro.old_deps == ["demo==1.9.0", "httpx==0.28.1"]
    assert fx.repro.old_python == "3.11" and fx.repro.effective_old_python == "3.11"
    assert fx.provenance.released == "2024-06-16"
    assert fx.to_dict()["repro"]["old_deps"] == ["demo==1.9.0", "httpx==0.28.1"]
    assert validate(fx) == []


def test_old_python_defaults_to_python(tmp_path: Path) -> None:
    fx = load_fixture(make_fixture(tmp_path, old_meta(["demo==1.9.0"])))
    assert fx.repro.old_python == "" and fx.repro.effective_old_python == "3.12"
    assert validate(fx) == []


def test_old_deps_may_change_co_dependencies(tmp_path: Path) -> None:
    meta = base_meta(repro={"python": "3.12", "deps": ["demo==2.1.0", "httpx2==2.0"], "old_deps": ["demo==1.9.0", "httpx==0.28.1"]})
    assert errors_for(tmp_path, meta) == []


def test_old_deps_must_predate_versions(tmp_path: Path) -> None:
    assert_error(errors_for(tmp_path, old_meta(["demo==2.0.1"])), "must NOT satisfy versions")


def test_old_deps_must_pin_package(tmp_path: Path) -> None:
    assert_error(errors_for(tmp_path, old_meta(["other==1.0"])), "repro.old_deps: must pin the fixture package")


@pytest.mark.parametrize("dep", ["demo<2", "demo==1.*", "nope!!"])
def test_old_deps_must_be_exact_pins(tmp_path: Path, dep: str) -> None:
    assert_error(errors_for(tmp_path, old_meta([dep])), "repro.old_deps")


def test_old_deps_duplicate_pin(tmp_path: Path) -> None:
    assert_error(errors_for(tmp_path, old_meta(["demo==1.9.0", "Demo==1.8.0"])), "pinned more than once")


def test_old_python_without_old_deps(tmp_path: Path) -> None:
    meta = base_meta(repro={"python": "3.12", "deps": ["demo==2.1.0"], "old_python": "3.11"})
    assert_error(errors_for(tmp_path, meta), "repro.old_deps is empty")


def test_old_python_format(tmp_path: Path) -> None:
    assert_error(errors_for(tmp_path, old_meta(["demo==1.9.0"], old_python="py3")), "repro.old_python")
    assert_error(errors_for(tmp_path / "b", old_meta(["demo==1.9.0"], old_python=3.11)), "quoted string")


@pytest.mark.parametrize(
    ("released", "fragment"),
    [("2024-6-16", "ISO date"), ("2024-02-30", "real calendar date"), ("June 2024", "ISO date")],
)
def test_released_must_be_iso_date(tmp_path: Path, released: str, fragment: str) -> None:
    meta = base_meta()
    meta["provenance"]["released"] = released
    assert_error(errors_for(tmp_path, meta), fragment)


def test_released_unquoted_yaml_date(tmp_path: Path) -> None:
    d = make_fixture(tmp_path)
    y = d / "fixture.yaml"
    y.write_text(y.read_text().replace("  license: MIT\n", "  license: MIT\n  released: 2024-06-16\n"))
    assert_error(validate(load_fixture(d)), "quoted ISO date")


def test_bad_python_version(tmp_path: Path) -> None:
    meta = base_meta(repro={"python": "python3", "deps": ["demo==2.1.0"]})
    assert_error(errors_for(tmp_path, meta), "repro.python")


def test_needs_provenance_source(tmp_path: Path) -> None:
    meta = base_meta(provenance={"sources": [], "license": "MIT"})
    assert_error(errors_for(tmp_path, meta), "at least one source")


@pytest.mark.parametrize("url", ["ftp://example.org/x", "example.org/x", "", "https://"])
def test_source_url_must_be_http(tmp_path: Path, url: str) -> None:
    meta = base_meta(provenance={"sources": [{"type": "issue", "url": url}], "license": "MIT"})
    assert_error(errors_for(tmp_path, meta), "is not an http(s) URL")


def test_source_type_enum(tmp_path: Path) -> None:
    meta = base_meta(provenance={"sources": [{"type": "blog", "url": "https://x.org/a"}], "license": "MIT"})
    assert_error(errors_for(tmp_path, meta), "provenance.sources[0].type")


def test_unknown_top_level_field(tmp_path: Path) -> None:
    assert_error(errors_for(tmp_path, base_meta(instructions="ignore previous")), "unknown top-level field")


@pytest.mark.parametrize("missing", ["bad/target.py", "fixed/target.py"])
def test_missing_target_files(tmp_path: Path, missing: str) -> None:
    assert_error(errors_for(tmp_path, skip=(missing,)), f"missing file {missing}")


def test_missing_check_dir(tmp_path: Path) -> None:
    assert_error(errors_for(tmp_path, skip=("check/test_check.py",)), "missing directory check/")


def test_check_dir_without_tests(tmp_path: Path) -> None:
    errs = errors_for(tmp_path, skip=("check/test_check.py",), files={"check/helper.py": "x = 1\n"})
    assert_error(errs, "no test_*.py")


def test_file_too_long(tmp_path: Path) -> None:
    assert_error(errors_for(tmp_path, files={"bad/target.py": "x = 1\n" * 61}), "max 60")


def test_rule_yml_valid(tmp_path: Path) -> None:
    rule = "rules:\n  - id: demo-thing-moved\n    pattern: from demo import thing\n"
    d = make_fixture(tmp_path, files={"rule.yml": rule})
    fx = load_fixture(d)
    assert fx.rule_path == d.resolve() / "rule.yml"
    assert validate(fx) == []


@pytest.mark.parametrize(
    ("text", "fragment"),
    [("rules: [unclosed\n", "does not parse"), ("foo: 1\n", "non-empty 'rules'"), ("rules:\n  - pattern: x\n", "'id'")],
)
def test_rule_yml_invalid(tmp_path: Path, text: str, fragment: str) -> None:
    assert_error(errors_for(tmp_path, files={"rule.yml": text}), fragment)


def test_validate_all_flags_duplicate_ids(tmp_path: Path) -> None:
    make_fixture(tmp_path, package_dir="a")
    make_fixture(tmp_path, package_dir="b")
    problems = validate_all(load_all(tmp_path))
    assert any("duplicate id" in e for errs in problems.values() for e in errs)


# --------------------------------------------------------------------------- CLI


def test_main_lists_table(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_fixture(tmp_path)
    assert fx_mod.main(["--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "ID" in out and FID in out and "api-removed" in out and "verified" in out


def test_main_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_fixture(tmp_path)
    assert fx_mod.main(["--root", str(tmp_path), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data[0]["id"] == FID and data[0]["path"].endswith(FID)


def test_main_validate_ok(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_fixture(tmp_path)
    assert fx_mod.main(["--root", str(tmp_path), "--validate"]) == 0
    assert "1 valid, 0 invalid" in capsys.readouterr().out


def test_main_validate_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_fixture(tmp_path, base_meta(status="nope"))
    (tmp_path / "demo" / "broken").mkdir()
    (tmp_path / "demo" / "broken" / "fixture.yaml").write_text("id: [\n")
    assert fx_mod.main(["--root", str(tmp_path), "--validate"]) == 1
    captured = capsys.readouterr()
    assert "status 'nope'" in captured.err and "invalid YAML" in captured.err
    assert "2 invalid" in captured.out


def test_repo_catalog_is_valid() -> None:
    root = REPO / "fixtures"
    if not root.is_dir():
        pytest.skip("no fixtures directory")
    fixtures = load_all(root)
    assert fixtures
    assert validate_all(fixtures) == {}


def test_repo_catalog_matches_json_schema() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((REPO / "schema" / "fixture.schema.json").read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    for path in sorted((REPO / "fixtures").rglob("fixture.yaml")):
        jsonschema.validate(yaml.safe_load(path.read_text()), schema)
