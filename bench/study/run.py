"""Run the claimed-vs-proven study.

    python -m bench.study.run --agent replay --replay fixed --scorer local --tasks 'pandas-*'
    python -m bench.study.run --agent claude_code --model claude-haiku-5-5 --trials 1 \\
        --per-trial-usd 0.75 --run-usd 10 --prior-spend-usd 3.89 --max-usd 30

For trial k in 1..K, for each task: write the task project into a fresh temp dir, run the
agent with the task prompt, score it (bench/study/score.py) and append a record to
<out>/results.jsonl. Raw material for hand-labelling goes to <out>/raw/<task>/t<k>/:
prompt.md, final_message.txt, changes.diff (everything the agent changed), transcript.

Spend guard (claude_code): stops launching trials once spent + per_trial_usd would exceed
min(run_usd, max_usd - prior_spend_usd). Each claude run also gets --max-budget-usd
per_trial_usd and --max-turns. A trial with no reported cost is charged per_trial_usd.
"""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from bench.common import REPO_ROOT
from bench.study import agents
from bench.study.report import write_report
from bench.study.score import _read_tree, score_trial
from bench.study.taskgen import Task, build_all, materialize


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="python -m bench.study.run", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agent", choices=["claude_code", "replay"], default="replay")
    ap.add_argument("--replay", choices=agents.REPLAY_MODES, default="fixed")
    ap.add_argument("--tasks", help="comma-separated task-id globs (default: all)")
    ap.add_argument("--trials", type=int, default=1)
    ap.add_argument("--model", default="claude-haiku-5-5")
    ap.add_argument("--max-turns", type=int, default=30)
    ap.add_argument("--per-trial-usd", type=float, default=0.75, help="--max-budget-usd for each claude run")
    ap.add_argument("--run-usd", type=float, default=0.0, help="spend cap for this run (claude_code)")
    ap.add_argument("--max-usd", type=float, default=5.0, help="overall cap across all runs")
    ap.add_argument("--prior-spend-usd", type=float, default=0.0)
    ap.add_argument("--max-trials", type=int, default=200)
    ap.add_argument("--scorer", choices=["uv", "local"], default="uv")
    ap.add_argument("--local-python", default=sys.executable)
    ap.add_argument("--agent-timeout", type=float, default=1800)
    ap.add_argument("--out")
    ap.add_argument("--dry-run", action="store_true")
    return ap.parse_args(argv)


def changes_diff(task: Task, workdir: Path) -> str:
    cur = _read_tree(workdir)
    out: list[str] = []
    for rel in sorted({*task.files, *cur} - {"uv.lock"}):
        a, b = task.files.get(rel), cur.get(rel)
        if a != b:
            out += difflib.unified_diff((a or "").splitlines(True), (b or "").splitlines(True),
                                        f"a/{rel}" if a is not None else "/dev/null",
                                        f"b/{rel}" if b is not None else "/dev/null")
    return "".join(out)


def run_trial(agent, task: Task, trial: int, ns: argparse.Namespace, tmp_root: Path, out: Path) -> dict[str, Any]:
    tdir = Path(tempfile.mkdtemp(prefix=f"{task.id[:40]}-t{trial}-", dir=tmp_root))
    work = materialize(task, tdir / "project")
    raw = out / "raw" / task.id / f"t{trial}"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "prompt.md").write_text(task.prompt, encoding="utf-8")
    agent.task = task
    t0 = time.monotonic()
    try:
        meta = agent.run(task.prompt, work, raw)
    except agents.AgentError as e:
        meta = {"cost_usd": 0.0, "agent_error": str(e), "final_message": None}
    rec: dict[str, Any] = {"task": task.id, "fixtures": task.fixtures, "trial": trial,
                           "agent_seconds": round(time.monotonic() - t0, 1)}
    rec.update({k: meta.get(k) for k in ("cost_usd", "cost_estimated", "num_turns", "result_subtype",
                                         "exit_code", "agent_error", "replayed") if k in meta})
    rec["final_message"] = meta.get("final_message")
    (raw / "final_message.txt").write_text(meta.get("final_message") or "", encoding="utf-8")
    (raw / "changes.diff").write_text(changes_diff(task, work), encoding="utf-8")
    result = score_trial(task, work, meta.get("final_message"), ns.scorer, ns.local_python)
    (raw / "proven_output.txt").write_text(result.pop("proven_output"), encoding="utf-8")
    (raw / "agent_suite_output.txt").write_text(result.pop("agent_suite_output"), encoding="utf-8")
    if "agent_error" in rec:
        result["outcome"] = "infra-error"
    rec.update(result)
    shutil.rmtree(tdir, ignore_errors=True)
    return rec


def main(argv: list[str] | None = None) -> int:
    ns = parse_args(sys.argv[1:] if argv is None else argv)
    tasks = build_all(ns.tasks)
    if not tasks:
        print(f"no tasks match {ns.tasks!r}", file=sys.stderr)
        return 2
    total = len(tasks) * ns.trials
    cap = min(ns.run_usd, ns.max_usd - ns.prior_spend_usd)
    paid = ns.agent == "claude_code"
    print(f"plan: {len(tasks)} tasks x {ns.trials} trials = {total}"
          + (f"; spend cap ${cap:.2f} (per trial <= ${ns.per_trial_usd:.2f})" if paid else ""))
    if total > ns.max_trials:
        print(f"refusing: {total} trials > --max-trials {ns.max_trials}", file=sys.stderr)
        return 2
    if paid and cap < ns.per_trial_usd:
        print(f"refusing: spend cap ${cap:.2f} leaves no room for one trial (set --run-usd)", file=sys.stderr)
        return 2
    if ns.dry_run:
        for t in tasks:
            print(f"  {t.id}")
        return 0
    agent = (agents.ClaudeCodeStudy(ns.model, ns.max_turns, ns.per_trial_usd, ns.agent_timeout)
             if paid else agents.Replay(ns.replay))
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{stamp}-study-" + (ns.model if paid else f"replay-{ns.replay}")
    out = Path(ns.out or REPO_ROOT / "bench" / "results" / run_id)
    out.mkdir(parents=True, exist_ok=True)
    meta = {k: v for k, v in vars(ns).items() if k != "dry_run"}
    meta.update(run_id=run_id, cap_usd=cap, tasks=[t.id for t in tasks], stopped_for_budget=0,
                started=dt.datetime.now(dt.timezone.utc).isoformat())
    tmp_root = Path(tempfile.mkdtemp(prefix="mend-study-run-"))
    plan = [(k, t) for k in range(ns.trials) for t in tasks]
    spent = 0.0
    with (out / "results.jsonl").open("w", encoding="utf-8") as fh:
        for i, (trial, task) in enumerate(plan):
            if paid and spent + ns.per_trial_usd > cap:
                meta["stopped_for_budget"] = len(plan) - i
                print(f"budget cap reached: {len(plan) - i} trial(s) not run", file=sys.stderr)
                break
            rec = run_trial(agent, task, trial, ns, tmp_root, out)
            spent += rec.get("cost_usd") or 0.0
            rec.update(run_id=run_id, agent=agent.name, model=ns.model if paid else None,
                       spent_so_far_usd=round(spent, 4))
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            print(f"[{i + 1}/{total}] {task.id:<55} t{trial} {rec['outcome']:<14} claim={rec['claim']:<4} "
                  f"proven={rec['proven']} ${rec.get('cost_usd') or 0:.3f}", flush=True)
    meta.update(spend_usd=round(spent, 4), finished=dt.datetime.now(dt.timezone.utc).isoformat())
    (out / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    shutil.rmtree(tmp_root, ignore_errors=True)
    print(f"\nspend ${spent:.4f}\nreport: {write_report(out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
