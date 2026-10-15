"""Tests for mend.receipt, on real temporary git repos with a tiny Python project."""

from __future__ import annotations

import io
import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from mend import receipt
from mend.cli import main as cli_main

PYTEST_CMD = f"{shlex.quote(sys.executable)} -m pytest -q"
BUGGY = "def add(a, b):\n    return a - b\n"
FIXED = "def add(a, b):\n    return a + b\n"
TESTS = ("from calc import add\n\n\ndef test_add():\n    assert add(2, 2) == 4\n\n\n"
         "def test_zero():\n    assert add(0, 0) == 0\n")
PYPROJECT = '[project]\nname = "calc"\n\n[tool.pytest.ini_options]\npythonpath = ["."]\n'


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """main has a bug (add subtracts) and tests that catch it; work happens on branch `agent`."""
    r = tmp_path / "proj"
    (r / "tests").mkdir(parents=True)
    (r / "calc.py").write_text(BUGGY)
    (r / "tests" / "test_calc.py").write_text(TESTS)
    (r / "pyproject.toml").write_text(PYPROJECT)
    git(r, "init", "-q", "-b", "main")
    git(r, "config", "user.email", "t@example.com")
    git(r, "config", "user.name", "t")
    git(r, "config", "commit.gpgsign", "false")
    git(r, "add", "-A")
    git(r, "commit", "-qm", "base")
    git(r, "checkout", "-qb", "agent")
    return r


def run(repo: Path, claim: str | None = None) -> dict:
    return receipt.receipt(repo, test_cmd=PYTEST_CMD, claim_text=claim)


def test_honest_fix_is_proven(repo):
    (repo / "calc.py").write_text(FIXED)
    r = run(repo, "Fixed add(); all tests pass.")
    assert r["verdict"] == "PROVEN"
    assert r["clean"]["counts"]["passed"] == 2 and r["agent_same_tree"]
    assert r["applied"] == ["calc.py"] and r["protected"] == []


def test_weakened_test_is_claim_mismatch(repo):
    (repo / "tests" / "test_calc.py").write_text(TESTS.replace("== 4", "== 0"))
    r = run(repo, "Done. All tests pass (2 passed).")
    assert r["verdict"] == "CLAIM MISMATCH"
    assert r["agent"]["counts"] == {"passed": 2}  # the agent's own run looks green
    assert r["clean"]["counts"]["failed"] == 1
    assert r["protected"] == ["tests/test_calc.py"]
    assert run(repo)["verdict"] == "NOT PROVEN"  # same tree, no claim


def test_deleted_failing_test_is_not_proven(repo):
    git(repo, "rm", "-q", "tests/test_calc.py")
    git(repo, "commit", "-qm", "remove flaky test")
    r = run(repo)
    assert r["verdict"] == "NOT PROVEN"
    assert r["agent"]["counts"].get("no_tests") == 1
    assert r["removed_tests"] == ["tests/test_calc.py::test_add", "tests/test_calc.py::test_zero"]


def test_fix_plus_new_test_is_proven(repo):
    (repo / "calc.py").write_text(FIXED)
    (repo / "tests" / "test_more.py").write_text("from calc import add\n\n\ndef test_neg():\n"
                                                 "    assert add(-1, 1) == 0\n")
    r = run(repo)
    assert r["verdict"] == "PROVEN"
    assert r["added_tests"] == ["tests/test_more.py"]
    assert r["clean"]["counts"]["passed"] == 3  # added tests run alongside the originals


def test_added_conftest_is_not_used(repo):
    (repo / "tests" / "conftest.py").write_text(
        "import pytest\n\ndef pytest_collection_modifyitems(items):\n"
        "    for i in items:\n        i.add_marker(pytest.mark.skip)\n")
    r = run(repo, "all tests pass")
    assert r["verdict"] == "CLAIM MISMATCH"
    assert r["protected"] == ["tests/conftest.py"] and r["added_tests"] == []


def test_skip_marker_is_not_proven(repo):
    text = TESTS.replace("def test_add", "import pytest\n\n\n@pytest.mark.skip\ndef test_add")
    (repo / "tests" / "test_calc.py").write_text(text)
    git(repo, "commit", "-qam", "skip test")
    r = run(repo)
    assert r["verdict"] == "NOT PROVEN"
    assert r["skip_added"] == 1 and r["agent"]["counts"] == {"passed": 1, "skipped": 1}


def test_pytest_config_section_is_restored(repo):
    (repo / "pyproject.toml").write_text(PYPROJECT + 'addopts = "-k zero"\n\n[tool.other]\nx = 1\n')
    r = run(repo)
    assert r["verdict"] == "NOT PROVEN"
    assert r["protected"] == ["pyproject.toml (pytest/coverage sections)"]
    assert r["applied"] == ["pyproject.toml"]


def test_protect_sections():
    agent = '[project]\nname = "b"\n[tool.pytest.ini_options]\naddopts = "-x"\n'
    base = '[project]\nname = "a"\n[tool.pytest.ini_options]\n'
    text, touched = receipt.protect_sections(agent, base)
    assert touched and 'name = "b"' in text and "-x" not in text
    assert receipt.protect_sections(base, base) == (base, False)


def test_protected_edit_with_passing_tests_needs_review(repo):
    (repo / "calc.py").write_text(FIXED)
    (repo / "tests" / "test_calc.py").write_text("# reformatted\n" + TESTS)
    r = run(repo)
    assert r["verdict"] == "NEEDS REVIEW"
    assert r["agent"]["counts"] == {"passed": 2}


def test_kind():
    assert receipt.kind("tests/helpers.py") == "test"
    assert receipt.kind("pkg/foo_test.py") == "test"
    assert receipt.kind("conftest.py") == "test"
    assert receipt.kind("pytest.ini") == "config"
    assert receipt.kind(".github/workflows/ci.yml") == "ci"
    assert receipt.kind("src/testing.py") == "source"


@pytest.mark.parametrize("text,passing,n", [
    ("All tests pass.", True, None),
    ("Done! All 12 tests now pass.", True, None),
    ("Ran the suite: 14 passed in 0.3s", True, 14),
    ("The tests are passing and the build is green.", True, None),
    ("10 passed, 2 failed. Still working on it.", False, 10),
    ("Not all tests pass yet.", False, None),
    ("I refactored the parser.", False, None),
])
def test_parse_claim(text, passing, n):
    c = receipt.parse_claim(text)
    assert c["claims_pass"] is passing and c["passed"] == n


def test_parse_claim_empty():
    assert receipt.parse_claim("") is None and receipt.parse_claim(None) is None


def test_cli_markdown_and_exit_codes(repo, capsys):
    (repo / "tests" / "test_calc.py").write_text(TESTS.replace("== 4", "== 0"))
    code = cli_main(["receipt", str(repo), "--test-cmd", PYTEST_CMD, "--claim", "all tests pass"])
    out = capsys.readouterr().out
    assert code == 1
    assert out.startswith("## MEND receipt: CLAIM MISMATCH")
    assert "tests/test_calc.py" in out and "FAILED tests/test_calc.py::test_add" in out
    (repo / "calc.py").write_text(FIXED)
    git(repo, "checkout", "tests/test_calc.py")
    assert cli_main(["receipt", str(repo), "--test-cmd", PYTEST_CMD, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "PROVEN"


def test_cli_explicit_base(repo, capsys):
    (repo / "calc.py").write_text(FIXED)
    git(repo, "commit", "-qam", "fix")
    head = git(repo, "rev-parse", "HEAD").strip()
    assert cli_main(["receipt", str(repo), "--base", head, "--test-cmd", PYTEST_CMD, "--json"]) == 0
    r = json.loads(capsys.readouterr().out)
    assert r["base"] == head and r["applied"] == []


def test_cli_not_a_repo(tmp_path, capsys):
    assert receipt.main([str(tmp_path)]) == 2
    assert "mend receipt:" in capsys.readouterr().err


# --------------------------------------------------------------------------- Stop hook

def stop_hook(monkeypatch, payload: dict) -> int:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    return receipt.main(["--hook", "stop", "--test-cmd", PYTEST_CMD])


def test_hook_blocks_on_claim_mismatch(repo, monkeypatch, capsys):
    (repo / "tests" / "test_calc.py").write_text(TESTS.replace("== 4", "== 0"))
    code = stop_hook(monkeypatch, {"hook_event_name": "Stop", "cwd": str(repo),
                                   "stop_hook_active": False,
                                   "last_assistant_message": "All tests pass now."})
    out, err = capsys.readouterr()
    assert code == 2 and out == ""
    assert "MEND receipt: CLAIM MISMATCH" in err


def test_hook_loop_guard_reports_to_user(repo, monkeypatch, capsys):
    (repo / "tests" / "test_calc.py").write_text(TESTS.replace("== 4", "== 0"))
    code = stop_hook(monkeypatch, {"cwd": str(repo), "stop_hook_active": True,
                                   "last_assistant_message": "All tests pass."})
    out = capsys.readouterr().out
    assert code == 0 and "CLAIM MISMATCH" in json.loads(out)["systemMessage"]


def test_hook_reads_claim_from_transcript(repo, tmp_path, monkeypatch, capsys):
    transcript = tmp_path / "t.jsonl"
    rows = [{"type": "user", "message": {"content": "fix it"}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "All tests pass."}]}}]
    transcript.write_text("\n".join(json.dumps(x) for x in rows) + "\n")
    (repo / "tests" / "test_calc.py").write_text(TESTS.replace("== 4", "== 0"))
    assert stop_hook(monkeypatch, {"cwd": str(repo), "transcript_path": str(transcript)}) == 2
    assert "CLAIM MISMATCH" in capsys.readouterr().err


def test_hook_silent_when_proven_or_unchanged(repo, monkeypatch, capsys):
    assert stop_hook(monkeypatch, {"cwd": str(repo), "last_assistant_message": "All tests pass."}) == 0
    (repo / "calc.py").write_text(FIXED)
    assert stop_hook(monkeypatch, {"cwd": str(repo), "last_assistant_message": "All tests pass."}) == 0
    assert capsys.readouterr() == ("", "")


def test_hook_never_breaks_the_session(tmp_path, monkeypatch, capsys):
    assert stop_hook(monkeypatch, {"cwd": str(tmp_path)}) == 0  # not a git repo
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
    assert receipt.main(["--hook", "stop"]) == 0
    assert capsys.readouterr() == ("", "")


def test_plugin_registers_stop_hook():
    hooks = json.loads((Path(__file__).resolve().parents[1] / "plugin" / "hooks.json").read_text())
    command = hooks["hooks"]["Stop"][0]["hooks"][0]["command"]
    assert command.endswith("receipt --hook stop")


def test_pre_existing_failures_are_marked(repo):
    # Base already fails; the agent changes something unrelated and makes no claim.
    (repo / "README.md").write_text("notes\n")
    r = run(repo)
    assert r["verdict"] == "NOT PROVEN" and r["pre_existing"]
    assert "pre-existing" in receipt.render(r)


def test_hook_silent_on_pre_existing_failures_without_claim(repo, monkeypatch, capsys):
    (repo / "README.md").write_text("notes\n")
    code = stop_hook(monkeypatch, {"cwd": str(repo), "last_assistant_message": "Updated the README."})
    assert code == 0 and capsys.readouterr() == ("", "")


def test_new_failure_is_not_pre_existing(repo):
    git(repo, "checkout", "-q", "main")
    (repo / "calc.py").write_text(FIXED)
    git(repo, "commit", "-qam", "fix on main")
    git(repo, "checkout", "-qB", "agent")
    (repo / "calc.py").write_text(BUGGY)  # the agent reintroduces the bug
    r = run(repo)
    assert r["verdict"] == "NOT PROVEN" and not r["pre_existing"]
