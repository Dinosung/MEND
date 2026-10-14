from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from mend import verify
from mend.fixture import Fixture, load_fixture
from mend.verify import RunResult, evaluate, filter_changed, uv_command, verify_fixture

FID = "demo-thing-moved"


def make_fixture(root: Path, fid: str = FID, deps: list[str] | None = None) -> Fixture:
    d = root / "demo" / fid
    for sub in ("bad", "fixed", "check"):
        (d / sub).mkdir(parents=True)
    meta = {
        "id": fid,
        "title": "t",
        "summary": "s",
        "ecosystem": "python",
        "package": "demo",
        "versions": ">=2",
        "tags": ["x"],
        "failure": {"kind": "api-removed", "symptom": "s", "bad_pattern": "b", "fix_pattern": "f"},
        "repro": {"python": "3.12", "deps": deps or ["demo==2.1.0", "demo-extras==1.0"]},
        "provenance": {"sources": [{"type": "docs", "url": "https://example.org"}], "license": "MIT"},
        "status": "verified",
    }
    (d / "fixture.yaml").write_text(yaml.safe_dump(meta))
    (d / "bad" / "target.py").write_text("x = 1\n")
    (d / "fixed" / "target.py").write_text("x = 2\n")
    (d / "check" / "test_check.py").write_text("def test_x():\n    import target\n    assert target.x == 2\n")
    return load_fixture(d)


def run(code: int, ran: bool = True, timed_out: bool = False, out: str = "") -> RunResult:
    return RunResult(exit_code=code, duration=1.0, output=out, pytest_ran=ran, timed_out=timed_out)


class FakePopen:
    """Stands in for subprocess.Popen: records calls, writes the junit report when pytest 'runs'."""

    calls: list[dict[str, Any]] = []
    # side ("bad"/"fixed") -> (exit code, pytest_ran, output)
    script: dict[str, tuple[int, bool, str]] = {}
    timeout_sides: set[str] = set()

    def __init__(self, cmd: list[str], *, env: dict[str, str], **kw: Any) -> None:
        self.cmd, self.env, self.kw = cmd, env, kw
        self.side = Path(env["PYTHONPATH"]).name
        FakePopen.calls.append({"cmd": cmd, "env": env, "side": self.side, **kw})
        self.returncode: int | None = None
        self.pid = 999_999

    def communicate(self, timeout: float | None = None) -> tuple[str, None]:
        if self.side in FakePopen.timeout_sides and timeout is not None:
            raise subprocess.TimeoutExpired(self.cmd, timeout)
        code, ran, out = FakePopen.script[self.side]
        if ran:
            junit = next(a for a in self.cmd if a.startswith("--junitxml="))
            Path(junit.split("=", 1)[1]).write_text("<testsuites/>")
        self.returncode = code
        return out, None

    def kill(self) -> None:
        pass


@pytest.fixture
def fake_popen(monkeypatch: pytest.MonkeyPatch) -> type[FakePopen]:
    FakePopen.calls = []
    FakePopen.script = {}
    FakePopen.timeout_sides = set()
    monkeypatch.setattr(verify.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(verify.os, "killpg", lambda *a: None)
    monkeypatch.setattr(verify.shutil, "which", lambda name: f"/usr/bin/{name}")
    return FakePopen


# --------------------------------------------------------------------------- command


def test_uv_command_matches_reference(tmp_path: Path) -> None:
    fx = make_fixture(tmp_path)
    assert uv_command(fx) == [
        "uv", "run", "--isolated", "--no-project", "--python", "3.12",
        "--with", "demo==2.1.0", "--with", "demo-extras==1.0", "--with", "pytest",
        "pytest", "-q", "-p", "no:cacheprovider", str(fx.check_dir),
    ]  # fmt: skip


def test_docker_command_mounts_readonly(tmp_path: Path) -> None:
    fx = make_fixture(tmp_path)
    cmd = verify.docker_command(fx, "bad", tmp_path / "out", "c1")
    assert cmd[:2] == ["docker", "run"]
    assert f"{fx.path}:/fixture:ro" in cmd
    assert "PYTHONPATH=/fixture/bad" in cmd
    assert "python:3.12-slim" in cmd
    script = cmd[-1]
    assert "pip install" in script and "demo==2.1.0" in script and "pytest" in script
    assert script.endswith("/fixture/check")


# --------------------------------------------------------------------------- evaluate


def test_evaluate_verified() -> None:
    r = evaluate(FID, fixed=run(0), bad=run(1))
    assert r.ok and r.bad_failed and r.fixed_passed and not r.infra_error
    assert r.outcome == "ok" and r.bad_exit == 1 and r.fixed_exit == 0


def test_evaluate_bad_collection_error_counts_as_failure() -> None:
    r = evaluate(FID, fixed=run(0), bad=run(2))
    assert r.ok and r.bad_failed and "collection" in r.reason


def test_evaluate_bad_passes_is_real_failure() -> None:
    r = evaluate(FID, fixed=run(0), bad=run(0))
    assert not r.ok and not r.infra_error and not r.bad_failed
    assert "not reproduced" in r.reason and r.outcome == "fail"


def test_evaluate_fixed_tests_fail() -> None:
    r = evaluate(FID, fixed=run(1), bad=None)
    assert not r.ok and not r.infra_error and not r.fixed_passed
    assert r.bad_exit is None


@pytest.mark.parametrize("code", [2, 3, 4])
def test_evaluate_fixed_pytest_errors_are_infra(code: int) -> None:
    r = evaluate(FID, fixed=run(code), bad=None)
    assert not r.ok and r.infra_error and r.outcome == "error"


def test_evaluate_fixed_no_tests() -> None:
    r = evaluate(FID, fixed=run(5), bad=None)
    assert not r.ok and "no tests" in r.reason


def test_evaluate_setup_failure_is_infra() -> None:
    r = evaluate(FID, fixed=run(2, ran=False, out="error: failed to fetch"), bad=None)
    assert r.infra_error and "before pytest ran" in r.reason
    assert "failed to fetch" in r.logs["fixed"]


def test_evaluate_bad_setup_failure_is_infra() -> None:
    r = evaluate(FID, fixed=run(0), bad=run(1, ran=False))
    assert not r.ok and r.infra_error


@pytest.mark.parametrize("side", ["fixed", "bad"])
def test_evaluate_timeout_is_infra(side: str) -> None:
    timed = run(-1, ran=False, timed_out=True)
    r = evaluate(FID, fixed=timed if side == "fixed" else run(0), bad=timed if side == "bad" else None)
    assert r.infra_error and "timed out" in r.reason


@pytest.mark.parametrize("code", [3, 4, 5])
def test_evaluate_bad_unexpected_exit_is_infra(code: int) -> None:
    r = evaluate(FID, fixed=run(0), bad=run(code))
    assert not r.ok and r.infra_error


def test_logs_are_tailed() -> None:
    out = "\n".join(f"line {i}" for i in range(500))
    r = evaluate(FID, fixed=run(1, out=out), bad=None)
    lines = r.logs["fixed"].splitlines()
    assert len(lines) == verify.LOG_TAIL_LINES and lines[-1] == "line 499"


# --------------------------------------------------------------------------- verify_fixture (mocked subprocess)


def test_verify_fixture_runs_fixed_then_bad(tmp_path: Path, fake_popen: type[FakePopen], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEND_SENTINEL", "keep-me")
    fx = make_fixture(tmp_path)
    fake_popen.script = {"fixed": (0, True, "1 passed"), "bad": (1, True, "1 failed")}
    r = verify_fixture(fx)
    assert r.ok and r.durations.keys() == {"fixed", "bad"}
    assert [c["side"] for c in fake_popen.calls] == ["fixed", "bad"]
    for call in fake_popen.calls:
        assert call["env"]["PYTHONPATH"] == str(fx.path / call["side"])
        assert call["env"]["MEND_SENTINEL"] == "keep-me"  # copy of os.environ
        cmd = call["cmd"]
        assert cmd[:4] == ["uv", "run", "--isolated", "--no-project"]
        assert cmd[-1] == str(fx.check_dir)
        assert any(a.startswith("--junitxml=") for a in cmd)


def test_verify_fixture_skips_bad_when_fixed_fails(tmp_path: Path, fake_popen: type[FakePopen]) -> None:
    fx = make_fixture(tmp_path)
    fake_popen.script = {"fixed": (1, True, "1 failed")}
    r = verify_fixture(fx)
    assert not r.ok and not r.infra_error
    assert [c["side"] for c in fake_popen.calls] == ["fixed"]


def test_verify_fixture_network_failure(tmp_path: Path, fake_popen: type[FakePopen]) -> None:
    fx = make_fixture(tmp_path)
    fake_popen.script = {"fixed": (2, False, "error: Failed to fetch https://pypi.org/simple/demo/")}
    r = verify_fixture(fx)
    assert r.infra_error and not r.ok
    assert "pypi.org" in r.logs["fixed"]


def test_verify_fixture_timeout(tmp_path: Path, fake_popen: type[FakePopen]) -> None:
    fx = make_fixture(tmp_path)
    fake_popen.script = {"fixed": (0, True, "")}
    fake_popen.timeout_sides = {"fixed"}
    r = verify_fixture(fx, timeout=1)
    assert r.infra_error and "timed out" in r.reason


def test_verify_fixture_missing_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(verify.shutil, "which", lambda name: None)
    r = verify_fixture(make_fixture(tmp_path))
    assert r.infra_error and "not found" in r.reason


# --------------------------------------------------------------------------- selection + CLI


def test_filter_changed(tmp_path: Path) -> None:
    a = make_fixture(tmp_path, "demo-a")
    b = make_fixture(tmp_path, "demo-b")
    changed = {b.path / "check" / "test_check.py", tmp_path / "README.md"}
    assert filter_changed([a, b], changed) == [b]
    assert filter_changed([a, b], set()) == []


def test_main_json_report_and_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    make_fixture(tmp_path, "demo-good")
    make_fixture(tmp_path, "demo-bad")

    def fake_verify(fx: Fixture, backend: str, timeout: float) -> verify.VerifyResult:
        good = fx.id == "demo-good"
        return evaluate(fx.id, fixed=run(0), bad=run(1 if good else 0))

    monkeypatch.setattr(verify, "verify_fixture", fake_verify)
    assert verify.main([str(tmp_path), "--json", "-j", "2"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["summary"] == {"total": 2, "ok": 1, "fail": 1, "error": 0}
    assert [r["fixture_id"] for r in report["results"]] == ["demo-bad", "demo-good"]
    assert report["results"][1]["outcome"] == "ok"


def test_main_table_all_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    make_fixture(tmp_path)
    monkeypatch.setattr(verify, "verify_fixture", lambda fx, b, t: evaluate(fx.id, fixed=run(0), bad=run(1)))
    assert verify.main([str(tmp_path / "demo" / FID)]) == 0
    out = capsys.readouterr().out
    assert FID in out and "OK" in out and "1 ok" in out


def test_main_changed_since(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    make_fixture(tmp_path, "demo-a")
    b = make_fixture(tmp_path, "demo-b")
    monkeypatch.setattr(verify, "changed_files", lambda ref: {b.path / "fixture.yaml"})
    seen: list[str] = []

    def fake_verify(fx: Fixture, backend: str, timeout: float) -> verify.VerifyResult:
        seen.append(fx.id)
        return evaluate(fx.id, fixed=run(0), bad=run(1))

    monkeypatch.setattr(verify, "verify_fixture", fake_verify)
    assert verify.main([str(tmp_path), "--changed-since", "origin/main"]) == 0
    assert seen == ["demo-b"]


def test_main_nothing_to_verify(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert verify.main([str(tmp_path)]) == 0
    assert "no fixtures" in capsys.readouterr().out


def test_changed_files_with_real_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil

    if shutil.which("git") is None:
        pytest.skip("git not installed")

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.org")
    git("config", "user.name", "t")
    a = make_fixture(tmp_path, "demo-a")
    b = make_fixture(tmp_path, "demo-b")
    git("add", ".")
    git("commit", "-q", "-m", "init")
    git("checkout", "-q", "-b", "feature")
    (b.path / "fixed" / "target.py").write_text("x = 3\n")
    git("commit", "-q", "-am", "change b")
    (a.path / "notes.txt").write_text("untracked\n")
    monkeypatch.chdir(tmp_path)
    changed = verify.changed_files("main")
    assert filter_changed([a, b], changed) == [a, b]
    assert (b.path / "fixed" / "target.py").resolve() in changed
