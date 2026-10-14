"""Run the MEND-Bench v2 pilot.

    python -m bench.v2.run --config bench/v2/run-config.yaml            # the configured pilot
    python -m bench.v2.run --agent replay --replay-source bad --scorer local --fixtures 'numpy-*'

For trial k in 1..K, for each fixture, for each arm: build the task project in a fresh temp
dir, apply the arm, check that the hidden test is absent and the prompt does not leak
versions, run the agent, score source-only against the hidden test, append a record to
<out>/results.jsonl. Trial-major order keeps runs that stop on budget paired.

Spend guard: the run stops launching trials once spent + per_trial_usd would exceed
min(run_usd, max_usd - prior_spend_usd). Each claude run also gets --max-budget-usd
per_trial_usd and --max-turns. A trial with no reported cost is charged per_trial_usd.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml

from bench.common import REPO_ROOT, load_fixtures, select_fixtures
from bench.v2 import agents
from bench.v2.arms import ARMS, apply_arm, public_catalog, read_hook_log
from bench.v2.report import write_report
from bench.v2.score import score_trial
from bench.v2.taskgen import build_task, find_leaks, hidden_test_present, materialize

DEFAULTS: dict[str, Any] = {
    "agent": "claude_code", "fixtures": "*", "arms": "A0,A1,A4", "trials": 3,
    "model": "claude-haiku-5-5", "max_turns": 15, "per_trial_usd": 0.10, "run_usd": 1.50,
    "max_usd": 5.0, "prior_spend_usd": 0.0, "max_trials": 300, "scorer": "uv",
    "local_python": sys.executable, "replay_source": "fixed", "agent_timeout": 900, "out": None,
}


def parse_args(argv: list[str]) -> dict[str, Any]:
    ap = argparse.ArgumentParser(prog="python -m bench.v2.run", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", help="YAML file with any of the options below")
    ap.add_argument("--agent", choices=["claude_code", "replay"])
    ap.add_argument("--fixtures", help="comma-separated fixture globs (id or package/id)")
    ap.add_argument("--arms", help="comma-separated subset of A0,A1,A4")
    ap.add_argument("--trials", type=int)
    ap.add_argument("--model")
    ap.add_argument("--max-turns", type=int)
    ap.add_argument("--per-trial-usd", type=float, help="--max-budget-usd for each claude run")
    ap.add_argument("--run-usd", type=float, help="spend cap for this run")
    ap.add_argument("--max-usd", type=float, help="overall cap across all runs")
    ap.add_argument("--prior-spend-usd", type=float, help="already spent by earlier runs")
    ap.add_argument("--max-trials", type=int, help="fail fast if fixtures x arms x trials exceeds this")
    ap.add_argument("--scorer", choices=["uv", "local"])
    ap.add_argument("--local-python", help="interpreter for --scorer local")
    ap.add_argument("--replay-source", choices=["bad", "fixed", "tamper-bad", "tamper-fixed"])
    ap.add_argument("--agent-timeout", type=float)
    ap.add_argument("--out")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and exit")
    ns = vars(ap.parse_args(argv))
    cfg = dict(DEFAULTS)
    if ns["config"]:
        cfg.update(yaml.safe_load(Path(ns["config"]).read_text(encoding="utf-8")) or {})
    cfg.update({k: v for k, v in ns.items() if v is not None and k != "config"})
    for key in ("fixtures", "arms"):
        if isinstance(cfg[key], list):
            cfg[key] = ",".join(cfg[key])
    cfg["arms"] = [a.strip() for a in str(cfg["arms"]).split(",") if a.strip()]
    bad = [a for a in cfg["arms"] if a not in ARMS]
    if bad:
        ap.error(f"unknown arm(s) {bad}; expected {ARMS}")
    return cfg


def mend_hook_available() -> bool:
    proc = subprocess.run([sys.executable, "-m", "mend.cli", "hook", "session-start"],
                          input=json.dumps({"hook_event_name": "SessionStart", "source": "startup",
                                            "cwd": tempfile.gettempdir()}),
                          capture_output=True, text=True, env={"PYTHONPATH": str(REPO_ROOT / "src"),
                                                               "PATH": "/usr/bin:/bin"})
    return "unknown command" not in proc.stderr


def make_agent(cfg: dict[str, Any]):
    if cfg["agent"] == "replay":
        return agents.Replay(cfg["replay_source"])
    return agents.ClaudeCode(cfg["model"], int(cfg["max_turns"]), float(cfg["per_trial_usd"]),
                             float(cfg["agent_timeout"]))


def main(argv: list[str] | None = None) -> int:
    cfg = parse_args(sys.argv[1:] if argv is None else argv)
    fixtures = [f for f in select_fixtures(load_fixtures(REPO_ROOT / "fixtures"), cfg["fixtures"])
                if str(f.status) == "verified"]
    if not fixtures:
        print(f"no verified fixtures match {cfg['fixtures']!r}", file=sys.stderr)
        return 2
    total = len(fixtures) * len(cfg["arms"]) * int(cfg["trials"])
    cap = min(float(cfg["run_usd"]), float(cfg["max_usd"]) - float(cfg["prior_spend_usd"]))
    specs = {f.id: build_task(f) for f in fixtures}
    leaks = {f.id: find_leaks(specs[f.id].prompt, f) for f in fixtures}
    print(f"plan: {len(fixtures)} fixtures x {len(cfg['arms'])} arms x {cfg['trials']} trials = {total} "
          f"trials; spend cap ${cap:.2f} (per trial <= ${float(cfg['per_trial_usd']):.2f})")
    if total > int(cfg["max_trials"]):
        print(f"refusing: {total} trials > max_trials {cfg['max_trials']}", file=sys.stderr)
        return 2
    if any(leaks.values()):
        print(f"refusing: prompts leak versions/fixes: { {k: v for k, v in leaks.items() if v} }",
              file=sys.stderr)
        return 2
    if cfg["agent"] == "claude_code" and cap < float(cfg["per_trial_usd"]):
        print(f"refusing: spend cap ${cap:.2f} leaves no room for one trial", file=sys.stderr)
        return 2
    if cfg["agent"] == "claude_code" and "A4" in cfg["arms"] and not mend_hook_available():
        print("refusing: `mend hook` is not available in src/mend; A4 cannot run", file=sys.stderr)
        return 2
    if cfg.pop("dry_run", False):
        for f in fixtures:
            print(f"  {f.id}")
        return 0

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{stamp}-v2-{cfg['agent']}" + (f"-{cfg['replay_source']}" if cfg["agent"] == "replay" else "")
    out = Path(cfg["out"] or REPO_ROOT / "bench" / "results" / run_id)
    out.mkdir(parents=True, exist_ok=True)
    meta = {**cfg, "run_id": run_id, "cap_usd": cap, "fixtures": [f.id for f in fixtures],
            "started": dt.datetime.now(dt.timezone.utc).isoformat(), "stopped_for_budget": 0}
    if cfg["agent"] != "replay":
        meta.pop("replay_source")
    agent = make_agent(cfg)
    tmp_root = Path(tempfile.mkdtemp(prefix="mend-v2-"))
    catalog = public_catalog(REPO_ROOT / "fixtures", tmp_root / "mend-catalog")
    plan = [(t, fx, arm) for t in range(int(cfg["trials"])) for fx in fixtures for arm in cfg["arms"]]
    spent = 0.0
    with (out / "results.jsonl").open("w", encoding="utf-8") as fh:
        for i, (trial, fx, arm) in enumerate(plan):
            if cfg["agent"] != "replay" and spent + float(cfg["per_trial_usd"]) > cap:
                meta["stopped_for_budget"] = len(plan) - i
                print(f"budget cap reached: {len(plan) - i} trial(s) not run", file=sys.stderr)
                break
            rec = run_trial(agent, fx, specs[fx.id], arm, trial, cfg, tmp_root, catalog, out)
            spent += rec.get("cost_usd") or 0.0
            rec.update(run_id=run_id, model=cfg["model"], spent_so_far_usd=round(spent, 4))
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            print(f"[{i + 1}/{total}] {fx.id:<45} {arm} t{trial} {rec['outcome']:<14} "
                  f"${rec.get('cost_usd') or 0:.3f} (total ${spent:.2f})", flush=True)
    meta["spend_usd"] = round(spent, 4)
    meta["finished"] = dt.datetime.now(dt.timezone.utc).isoformat()
    (out / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    shutil.rmtree(tmp_root, ignore_errors=True)
    print(f"\nspend ${spent:.4f}\nreport: {write_report(out)}")
    return 0


def run_trial(agent, fx, spec, arm: str, trial: int, cfg: dict[str, Any], tmp_root: Path,
              catalog: Path, out: Path) -> dict[str, Any]:
    tdir = Path(tempfile.mkdtemp(prefix=f"{fx.id[:40]}-{arm}-t{trial}-", dir=tmp_root))
    work = materialize(spec, tdir / "project")
    hook_log = tdir / "hooks.jsonl"
    apply_arm(arm, work, spec, hook_log, catalog)
    raw = out / "raw" / fx.id / arm / f"t{trial}"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "prompt.md").write_text(spec.prompt, encoding="utf-8")
    rec: dict[str, Any] = {"fixture": fx.id, "package": str(fx.package), "arm": arm, "trial": trial,
                           "description_source": spec.description_source}
    leaked = hidden_test_present(spec, work)
    if leaked:  # never expected: a harness bug, so stop loudly
        raise RuntimeError(f"hidden test found in workdir before agent run: {leaked}")
    agent.fixture = fx
    t0 = time.monotonic()
    try:
        meta = agent.run(spec.prompt, work, raw)
    except agents.AgentError as e:
        meta = {"cost_usd": 0.0, "agent_error": str(e)}
    rec["agent_seconds"] = round(time.monotonic() - t0, 1)
    rec.update({k: meta.get(k) for k in ("cost_usd", "cost_estimated", "num_turns", "result_subtype",
                                         "exit_code", "peeked", "agent_error") if k in meta})
    rec["tool_calls"] = len(meta.get("tool_calls", []))
    if arm == "A4":
        rec["hooks"] = read_hook_log(hook_log)
        if hook_log.is_file():
            shutil.copyfile(hook_log, raw / "hooks.jsonl")
    result = score_trial(fx, spec, work, cfg["scorer"], cfg["local_python"])
    if result.get("detail") == "no target.py" and "agent_error" not in rec:
        result["outcome"] = "other-failure"  # the agent ran but did not deliver: its failure, not infra
    (raw / "score_output.txt").write_text(result.pop("output_tail", ""), encoding="utf-8")
    rec.update(result)
    if (work / "target.py").is_file():
        shutil.copyfile(work / "target.py", raw / "target.py")
    shutil.rmtree(tdir, ignore_errors=True)
    return rec


if __name__ == "__main__":
    raise SystemExit(main())
