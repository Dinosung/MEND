"""MEND-Bench v2 pilot harness: task building, leak checks, source-only scoring, stats, budget."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bench.common import load_fixtures, select_fixtures
from bench.v2 import agents, run, stats
from bench.v2.arms import apply_arm, read_hook_log, versions_line
from bench.v2.score import sanitize, score_trial
from bench.v2.taskgen import (
    build_task,
    find_leaks,
    hidden_test_present,
    materialize,
)

FIXTURES = load_fixtures(ROOT / "fixtures")
PY313 = shutil.which("python3.13")


def fx(fid: str):
    return select_fixtures(FIXTURES, fid)[0]


# --------------------------------------------------------------------------- tasks

def test_task_project_layout_and_hidden_test_absent(tmp_path):
    f = fx("numpy-trapz-removed")
    spec = build_task(f)
    work = materialize(spec, tmp_path / "project")
    for rel in ("pyproject.toml", "CLAUDE.md", "README.md", "helpers.py", "main.py", "tests/test_helpers.py"):
        assert (work / rel).is_file(), rel
    assert '"numpy==2.5.3"' in (work / "pyproject.toml").read_text()
    assert not (work / "target.py").exists()
    assert not list(work.rglob("test_check.py"))
    assert hidden_test_present(spec, work) == []
    shutil.copy(f.path / "check" / "test_check.py", work / "tests" / "copied.py")
    assert hidden_test_present(spec, work) == ["tests/copied.py"]


@pytest.mark.parametrize("f", [f for f in FIXTURES if f.status == "verified"], ids=lambda f: f.id)
def test_prompts_do_not_leak_versions(f):
    spec = build_task(f)
    assert find_leaks(spec.prompt, f) == []
    assert "target.py" in spec.prompt


def test_leak_checker_catches_versions_and_fixes():
    f = fx("numpy-trapz-removed")
    assert find_leaks("We use numpy 2.5.3 here.", f)
    assert find_leaks("This targets NumPy 2 semantics.", f)
    assert find_leaks("pin numpy==2.5.3", f)
    assert find_leaks("call np.trapezoid(y, x); np.isin(a, b) please", f)
    assert find_leaks("after the upgrade to the new release", f)
    assert find_leaks("Integrate the curve with numpy.", f) == []


def test_arms(tmp_path):
    f = fx("starlette-1-on-startup-removed")
    spec = build_task(f)
    base = (materialize(spec, tmp_path / "a0") / "CLAUDE.md").read_text()
    a1 = materialize(spec, tmp_path / "a1")
    apply_arm("A1", a1, spec, tmp_path / "h.jsonl", tmp_path)
    assert (a1 / "CLAUDE.md").read_text() == base + "\nThis project uses starlette 1.6.0, httpx2 2.13.0.\n"
    assert versions_line(["numpy==2.5.3"]) == "This project uses numpy 2.5.3."
    a4 = materialize(spec, tmp_path / "a4")
    apply_arm("A4", a4, spec, tmp_path / "h.jsonl", tmp_path / "cat")
    hooks = json.loads((a4 / ".claude" / "settings.json").read_text())["hooks"]
    assert hooks["SessionStart"][0]["matcher"] == "startup"
    assert hooks["PostToolUse"][0]["matcher"] == "Write|Edit|MultiEdit"
    for ev in ("SessionStart", "PostToolUse"):
        h = hooks[ev][0]["hooks"][0]
        assert h["type"] == "command" and "hook_wrapper.py" in h["command"]
    assert (a4 / "CLAUDE.md").read_text() == base


def test_hook_log_summary(tmp_path):
    log = tmp_path / "hooks.jsonl"
    rows = [{"event": "session-start", "exit_code": 0, "stdout_chars": 120},
            {"event": "post-tool-use", "exit_code": 0, "stdout_chars": 0},
            {"event": "post-tool-use", "exit_code": 2, "stdout_chars": 0},
            {"event": "post-tool-use", "exit_code": 1, "stdout_chars": 0}]
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    s = read_hook_log(log)
    assert s == {"session_start_calls": 1, "session_start_injected": True, "post_tool_use_calls": 3,
                 "post_tool_use_blocks": 1, "hook_errors": 1}
    assert read_hook_log(tmp_path / "missing.jsonl")["post_tool_use_calls"] == 0


def test_parse_stream_json():
    lines = [
        {"type": "system", "subtype": "init"},
        {"type": "system", "subtype": "hook_response", "hook_event": "SessionStart", "exit_code": 0},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Write", "input": {"file_path": "/w/target.py"}}]}},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Read", "input": {"file_path": "/repo/fixtures/x/check/test_check.py"}}]}},
        {"type": "result", "subtype": "success", "total_cost_usd": 0.0123, "num_turns": 4},
    ]
    meta = agents.parse_stream("\n".join(json.dumps(x) for x in lines) + "\nnot json\n")
    assert meta["cost_usd"] == 0.0123 and meta["num_turns"] == 4
    assert meta["tool_calls"] == ["Write", "Read"]
    assert meta["peeked"] is True
    assert len(meta["hook_events"]) == 1


# --------------------------------------------------------------------------- scoring

def test_sanitize_discards_test_tampering(tmp_path):
    f = fx("numpy-trapz-removed")
    spec = build_task(f)
    work = materialize(spec, tmp_path / "project")
    shutil.copy(f.path / "bad" / "target.py", work / "target.py")
    agents.plant_tampering(work)
    (work / "numpy.py").write_text("trapz = lambda *a: 0.65\n")
    (work / "pkg").mkdir()
    (work / "pkg" / "util.py").write_text("X = 1\n")
    out = tmp_path / "src"
    out.mkdir()
    info = sanitize(work, out, spec)
    kept = sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file())
    assert {"helpers.py", "main.py", "pkg/util.py", "target.py"} <= set(kept)
    for gone in ("conftest.py", "sitecustomize.py", "pytest.ini", "numpy.py", "tests/conftest.py"):
        assert not (out / gone).exists(), gone
    assert set(info["tampered"]) >= {"conftest.py", "sitecustomize.py", "pytest.ini",
                                     "tests/conftest.py", "tests/test_helpers.py"}
    clean = materialize(spec, tmp_path / "clean")
    out2 = tmp_path / "src2"
    out2.mkdir()
    assert sanitize(clean, out2, spec)["tampered"] == []


needs_py313 = pytest.mark.skipif(PY313 is None, reason="python3.13 with numpy needed for local scoring")


@needs_py313
@pytest.mark.parametrize("source,expected", [("bad", "known-failure"), ("fixed", "pass"),
                                             ("tamper-bad", "known-failure")])
def test_replay_scoring_local(tmp_path, source, expected):
    f = fx("numpy-trapz-removed")
    spec = build_task(f)
    work = materialize(spec, tmp_path / "project")
    agent = agents.Replay(source)
    agent.fixture = f
    agent.run(spec.prompt, work, tmp_path)
    res = score_trial(f, spec, work, scorer="local", python=PY313)
    assert res["outcome"] == expected, res
    assert bool(res["tampered_tests"]) == source.startswith("tamper")


# --------------------------------------------------------------------------- stats

def test_wilson():
    lo, hi = stats.wilson(0, 10)
    assert lo == 0.0 and abs(hi - 0.2775) < 1e-3
    lo, hi = stats.wilson(5, 10)
    assert abs(lo - 0.2366) < 1e-3 and abs(hi - 0.7634) < 1e-3


def test_mcnemar_exact():
    assert stats.mcnemar_exact(0, 0) == 1.0
    assert abs(stats.mcnemar_exact(0, 6) - 0.03125) < 1e-12
    assert abs(stats.mcnemar_exact(1, 5) - 0.21875) < 1e-12
    assert stats.mcnemar_exact(3, 3) == 1.0


def _recs(table):
    """table: {(fixture, arm): [outcomes]}"""
    return [{"fixture": t, "arm": a, "outcome": o, "package": t.split("-")[0]}
            for (t, a), outs in table.items() for o in outs]


def test_paired_and_arm_summary():
    K, P, I = "known-failure", "pass", "infra-error"
    recs = _recs({("t1", "A0"): [K, K], ("t1", "A4"): [P, P],
                  ("t2", "A0"): [K, P], ("t2", "A4"): [P, P],
                  ("t3", "A0"): [P, P], ("t3", "A4"): [P, I],
                  ("t4", "A0"): [K, K], ("t4", "A4"): [K, K]})
    a0 = stats.arm_summary(recs, "A0")
    assert (a0["scored"], a0["failures"], a0["failure_rate"]) == (8, 5, 5 / 8)
    a4 = stats.arm_summary(recs, "A4")
    assert (a4["scored"], a4["infra"], a4["failures"]) == (7, 1, 2)
    p = stats.paired(recs, "A0", "A4")
    assert p["tasks"] == 4
    assert abs(p["mean_diff"] - (-1 - 0.5 + 0 + 0) / 4) < 1e-12
    assert p["mcnemar"]["a_fail_only"] == 2 and p["mcnemar"]["b_fail_only"] == 0
    lo, hi = p["bootstrap95"]
    assert lo <= p["mean_diff"] <= hi <= 0


def test_hook_rates():
    recs = [{"arm": "A4", "hooks": {"session_start_injected": True, "post_tool_use_calls": 2,
                                    "post_tool_use_blocks": 1, "hook_errors": 0}},
            {"arm": "A4", "hooks": {"session_start_injected": True, "post_tool_use_calls": 1,
                                    "post_tool_use_blocks": 0, "hook_errors": 0}}]
    h = stats.hook_rates(recs)
    assert h["blocked"] == 0.5 and h["post_tool_use_fired"] == 1.0 and h["total_blocks"] == 1


# --------------------------------------------------------------------------- runner guards

class FakeAgent:
    name = "fake"

    def __init__(self, cost):
        self.cost, self.calls, self.fixture = cost, 0, None

    def run(self, prompt, workdir, rawdir):
        self.calls += 1
        shutil.copy(self.fixture.path / "fixed" / "target.py", workdir / "target.py")
        return {"cost_usd": self.cost, "num_turns": 3}


def test_runner_refuses_too_many_trials(tmp_path):
    assert run.main(["--agent", "replay", "--trials", "100", "--fixtures", "numpy-*",
                     "--out", str(tmp_path)]) == 2


@needs_py313
def test_runner_budget_cap_stops_and_records_spend(tmp_path, monkeypatch):
    fake = FakeAgent(cost=0.30)
    monkeypatch.setattr(run, "make_agent", lambda cfg: fake)
    monkeypatch.setattr(run, "mend_hook_available", lambda: True)
    code = run.main(["--agent", "claude_code", "--fixtures", "numpy-trapz-removed", "--arms", "A0,A1",
                     "--trials", "3", "--per-trial-usd", "0.40", "--run-usd", "0.95",
                     "--scorer", "local", "--local-python", PY313, "--out", str(tmp_path)])
    assert code == 0
    # 0.0 -> 0.3 -> 0.6 (a third would need 0.6 + 0.4 > 0.95): two trials, a complete pair
    assert fake.calls == 2
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["spend_usd"] == 0.6 and summary["run"]["stopped_for_budget"] == 4
    recs = [json.loads(x) for x in (tmp_path / "results.jsonl").read_text().splitlines()]
    assert [r["arm"] for r in recs] == ["A0", "A1"] and all(r["outcome"] == "pass" for r in recs)
    assert (tmp_path / "report.md").is_file()
