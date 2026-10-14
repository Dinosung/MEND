"""summary.json + report.md for a v2 pilot run.  `python -m bench.v2.report <out-dir>`"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from bench.v2 import stats


def load_records(out: Path) -> list[dict[str, Any]]:
    path = out / "results.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def summarize(records: list[dict[str, Any]], meta: dict[str, Any]) -> dict[str, Any]:
    arms = [a for a in meta.get("arms", []) if any(r["arm"] == a for r in records)]
    pairs = [(a, b) for a, b in (("A0", "A1"), ("A0", "A4"), ("A1", "A4")) if a in arms and b in arms]
    return {
        "run": meta,
        "trials": len(records),
        "spend_usd": round(sum(r.get("cost_usd") or 0.0 for r in records), 4),
        "arms": [stats.arm_summary(records, a) for a in arms],
        "paired": [stats.paired(records, a, b) for a, b in pairs],
        "hooks": stats.hook_rates(records),
        "tampered_trials": sum(bool(r.get("tampered_tests")) for r in records),
        "peeked_trials": sum(bool(r.get("peeked")) for r in records),
        "per_task": {a: stats.task_rates(records, a) for a in arms},
    }


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.0f}%"


def render(s: dict[str, Any]) -> str:
    run = s["run"]
    lines = [f"# MEND-Bench v2 pilot: {run.get('run_id', '')}", "",
             f"agent `{run.get('agent')}`, model `{run.get('model')}`, scorer `{run.get('scorer')}`, "
             f"k={run.get('trials')}, max_turns={run.get('max_turns')}, {len(run.get('fixtures', []))} fixtures. "
             f"Spend this run: **${s['spend_usd']:.2f}** (cap ${run.get('cap_usd', 0):.2f}).", ""]
    if run.get("stopped_for_budget"):
        lines += [f"**Stopped early for budget**: {run['stopped_for_budget']} trial(s) not run.", ""]
    lines += ["## Repeat-failure rate (known-failure / scored trials)", "",
              "| arm | scored | failures | rate | Wilson 95% | other-failure | pass | infra |",
              "|---|---|---|---|---|---|---|---|"]
    for a in s["arms"]:
        lo, hi = a["wilson95"]
        lines.append(f"| {a['arm']} | {a['scored']} | {a['failures']} | {_pct(a['failure_rate'])} | "
                     f"{_pct(lo)}–{_pct(hi)} | {a['other_failures']} | {a['passes']} | {a['infra']} |")
    lines += ["", "## Paired differences (per-task failure rate, B − A; negative = B fails less)", "",
              "| A → B | tasks | mean diff | bootstrap 95% | McNemar (A-only / B-only fails) | p |",
              "|---|---|---|---|---|---|"]
    for p in s["paired"]:
        lo, hi = p["bootstrap95"]
        m = p["mcnemar"]
        md = "n/a" if p["mean_diff"] is None else f"{100 * p['mean_diff']:+.1f} pts"
        lines.append(f"| {p['a']} → {p['b']} | {p['tasks']} | {md} | "
                     f"{100 * lo:+.1f} to {100 * hi:+.1f} | {m['a_fail_only']} / {m['b_fail_only']} | {m['p']:.3f} |"
                     if p["tasks"] else f"| {p['a']} → {p['b']} | 0 | n/a | n/a | n/a | n/a |")
    h = s["hooks"]
    if h.get("trials"):
        lines += ["", "## A4 hook activity", "",
                  f"- SessionStart context injected: {_pct(h['session_start_injected'])} of {h['trials']} trials",
                  f"- PostToolUse ran: {_pct(h['post_tool_use_fired'])}; blocked (exit 2) at least once: "
                  f"{_pct(h['blocked'])}; total blocks {h['total_blocks']}; hook errors {h['hook_errors']}"]
    lines += ["", "## Validity", "",
              f"- Trials with test/config tampering (discarded before scoring): {s['tampered_trials']}",
              f"- Trials whose tool calls referenced the hidden check or catalog path: {s['peeked_trials']}",
              "", "## Per-task failure rate", "",
              "| fixture | " + " | ".join(a["arm"] for a in s["arms"]) + " |",
              "|---|" + "---|" * len(s["arms"])]
    tasks = sorted({t for rates in s["per_task"].values() for t in rates})
    for t in tasks:
        lines.append(f"| {t} | " + " | ".join(_pct(s["per_task"][a["arm"]].get(t)) for a in s["arms"]) + " |")
    return "\n".join(lines) + "\n"


def write_report(out: Path) -> Path:
    meta = json.loads((out / "run.json").read_text(encoding="utf-8"))
    summary = summarize(load_records(out), meta)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out / "report.md").write_text(render(summary), encoding="utf-8")
    return out / "report.md"


if __name__ == "__main__":
    print(write_report(Path(sys.argv[1])))
