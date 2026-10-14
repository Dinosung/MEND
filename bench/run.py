"""Run MEND-Bench.

    python -m bench.run --agent anthropic_api --arms baseline,mend --fixtures 'pydantic-*' \
        --trials 5 --out bench/results/<run-id>/

For each fixture x arm x trial: create a fresh temp workdir (containing only a
requirements.txt with the pinned deps), let the agent solve the task, score target.py
with the fixture's own check, and append one record to <out>/results.jsonl. Agent
artifacts (target.py, transcripts) are kept under <out>/raw/. Finally writes
<out>/report.md (see bench/report.py).

Arms:
  baseline  mend_context=None
  mend      mend_context = what `mend lookup` returns for this project's deps + task
            (claude_code in --mend-mode mcp ignores the text and gets `mend serve` instead)

Offline smoke test (no network, no uv):
    python -m bench.run --agent replay --replay-source bad   --scorer local --fixtures-root bench/selftest/fixtures
    python -m bench.run --agent replay --replay-source fixed --scorer local --fixtures-root bench/selftest/fixtures
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

from bench.agents import AgentError, add_agent_args, make_agent
from bench.common import REPO_ROOT, deps_of, load_fixtures, lookup_context, select_fixtures
from bench.score import INFRA, ScoreResult, score
from bench.tasks import build_task

ARMS = ("baseline", "mend")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="python -m bench.run", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agent", required=True, choices=["replay", "anthropic_api", "claude_code"])
    ap.add_argument("--arms", default="baseline,mend")
    ap.add_argument("--fixtures", default=None, help="comma-separated id / package/id / path globs")
    ap.add_argument("--fixtures-root", dest="root", default=str(REPO_ROOT / "fixtures"))
    ap.add_argument("--include-drafts", action="store_true", help="also run status: draft fixtures")
    ap.add_argument("--trials", type=int, default=1)
    ap.add_argument("--out", default=None, help="output dir (default bench/results/<run-id>/)")
    ap.add_argument("--scorer", choices=["uv", "local"], default="uv")
    ap.add_argument("--uv-offline", action="store_true", help="pass --offline to uv (cache only)")
    ap.add_argument("--score-timeout", type=float, default=300)
    ap.add_argument("--llm-tasks", action="store_true", help="LLM-write tasks lacking an override")
    ap.add_argument("--keep-workdirs", action="store_true")
    ap.add_argument("--mend-exclude-self", action="store_true",
                    help="held-out: the with-MEND context omits the fixture under test "
                         "(measures spill-over, not recall). Context mode only; MCP serves the full catalog.")
    ap.add_argument("--hide-versions", action="store_true",
                    help="task text names dependencies without versions (closer to a real "
                         "repo where the agent must notice the lockfile itself)")
    add_agent_args(ap)
    args = ap.parse_args(argv)
    args.arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    bad = [a for a in args.arms if a not in ARMS]
    if bad:
        ap.error(f"unknown arm(s) {bad}; expected {ARMS}")
    return args


def run_id(args: argparse.Namespace) -> str:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tag = args.agent + (f"-{args.replay_source}" if args.agent == "replay" and
                        args.replay_source in ("bad", "fixed") else "")
    return f"{stamp}-{tag}"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rid = run_id(args)
    out = Path(args.out or REPO_ROOT / "bench" / "results" / rid)
    out.mkdir(parents=True, exist_ok=True)
    all_fixtures = load_fixtures(args.root)
    fixtures = select_fixtures(all_fixtures, args.fixtures)
    if not args.include_drafts:
        fixtures = [f for f in fixtures if str(getattr(f, "status", "")) == "verified"]
    if not fixtures:
        print(f"no fixtures selected under {args.root}", file=sys.stderr)
        return 2
    agent = make_agent(args.agent, args)
    meta = {"run_id": rid, "agent": args.agent, "model": args.model, "arms": args.arms,
            "trials": args.trials, "scorer": args.scorer, "fixtures_root": str(args.root),
            "fixtures": [f.id for f in fixtures], "mend_mode": args.mend_mode,
            "mend_exclude_self": args.mend_exclude_self,
            "hide_versions": args.hide_versions,
            "replay_source": args.replay_source if args.agent == "replay" else None,
            "python": sys.version.split()[0], "platform": platform.platform(),
            "started": dt.datetime.now(dt.timezone.utc).isoformat()}
    (out / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    templated = [f.id for f in fixtures if build_task(f).source == "template"]
    if templated and args.agent != "replay":
        print(f"warning: {len(templated)} fixture(s) use the generic template task (no "
              f"bench/tasks/<id>.md override); results for them are weak. Write overrides or "
              f"use --llm-tasks.", file=sys.stderr)
    results_path = out / "results.jsonl"
    total = len(fixtures) * len(args.arms) * args.trials
    n = 0
    with results_path.open("w", encoding="utf-8") as fh:
        for fx in fixtures:
            task = build_task(fx, use_llm=args.llm_tasks)
            if args.hide_versions:
                task.deps = [d.split("==")[0] for d in task.deps]
            pool = [f for f in all_fixtures if f.id != fx.id] if args.mend_exclude_self else all_fixtures
            ctx = lookup_context(pool, deps_of(fx), task.text)
            if hasattr(agent, "bind"):
                agent.bind(fx)
            for arm in args.arms:
                for trial in range(args.trials):
                    n += 1
                    rec = run_one(agent, fx, task, arm, trial, ctx if arm == "mend" else None, args, out)
                    rec.update(run_id=rid, agent=args.agent, model=args.model)
                    fh.write(json.dumps(rec) + "\n")
                    fh.flush()
                    print(f"[{n}/{total}] {fx.id:<45} {arm:<8} t{trial}  {rec['outcome']}"
                          + (f"  ({rec['match']})" if rec.get("match") else "")
                          + (f"  {rec['detail']}" if rec.get("detail") else ""))
    from bench.report import write_report

    report = write_report(out)
    print(f"\nresults: {results_path}\nreport:  {report}", flush=True)
    return 0


def run_one(agent, fx, task, arm: str, trial: int, ctx: str | None, args, out: Path) -> dict:
    wd = Path(tempfile.mkdtemp(prefix=f"mendbench-{fx.id[:30]}-{arm}-"))
    work = wd / "project"
    work.mkdir()
    (work / "requirements.txt").write_text("\n".join(deps_of(fx)) + "\n", encoding="utf-8")
    rec = {"fixture": fx.id, "package": str(fx.package), "arm": arm, "trial": trial,
           "task_source": task.source, "mend_context_chars": len(ctx) if ctx else 0}
    t0 = time.monotonic()
    try:
        agent.solve(task.text, work, ctx)
        res = score(fx, work, args.scorer, args.score_timeout, args.uv_offline)
    except AgentError as e:
        res = ScoreResult(INFRA, detail=f"agent error: {e}")
    except Exception as e:  # noqa: BLE001 - one bad trial must not kill the run
        res = ScoreResult(INFRA, detail=f"harness error: {type(e).__name__}: {e}")
        traceback.print_exc()
    rec["agent_seconds"] = round(time.monotonic() - t0 - res.duration, 2)
    rec.update(res.to_dict())
    raw = out / "raw" / fx.id / arm / f"t{trial}"
    raw.mkdir(parents=True, exist_ok=True)
    for name in ("target.py", "transcript.txt", "transcript.json", "transcript.jsonl",
                 "agent_meta.json", "agent_stderr.txt"):
        if (work / name).is_file():
            shutil.copyfile(work / name, raw / name)
    meta = raw / "agent_meta.json"
    if meta.is_file():
        try:
            rec["mend_tool_called"] = json.loads(meta.read_text()).get("mend_tool_called")
        except json.JSONDecodeError:
            pass
    (raw / "score_output.txt").write_text(res.output_tail, encoding="utf-8")
    if not args.keep_workdirs:
        shutil.rmtree(wd, ignore_errors=True)
    else:
        rec["workdir"] = str(work)
    return rec


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
