"""Summarize a MEND-Bench run: `python -m bench.report bench/results/<run-id>/`.

Headline metric: **repeat-failure rate** = known-failure / scored trials, where scored =
all trials except infra-error. Reported per arm with 95% Wilson score intervals, plus
the absolute and relative reduction (baseline -> mend), a per-package breakdown and a
per-fixture table.
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

OUTCOMES = ("pass", "known-failure", "other-failure", "infra-error")


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def pct(x: float) -> str:
    return "n/a" if x != x else f"{100 * x:.1f}%"


def rate_cell(k: int, n: int) -> str:
    if n == 0:
        return "n/a"
    lo, hi = wilson(k, n)
    return f"{pct(k / n)} [{pct(lo)}, {pct(hi)}] ({k}/{n})"


def load(run_dir: Path) -> tuple[list[dict], dict]:
    recs = [json.loads(l) for l in (run_dir / "results.jsonl").read_text().splitlines() if l.strip()]
    meta_p = run_dir / "run.json"
    meta = json.loads(meta_p.read_text()) if meta_p.is_file() else {}
    return recs, meta


def summarize(recs: list[dict]) -> dict[str, Counter]:
    by_arm: dict[str, Counter] = defaultdict(Counter)
    for r in recs:
        by_arm[r["arm"]][r["outcome"]] += 1
    return by_arm


def _scored(c: Counter) -> int:
    return sum(c[o] for o in OUTCOMES if o != "infra-error")


def render(recs: list[dict], meta: dict) -> str:
    arms = [a for a in ("baseline", "mend") if any(r["arm"] == a for r in recs)] + \
           sorted({r["arm"] for r in recs} - {"baseline", "mend"})
    by_arm = summarize(recs)
    L = [f"# MEND-Bench report: {meta.get('run_id', '?')}", ""]
    L.append(f"agent `{meta.get('agent')}`"
             + (f" model `{meta['model']}`" if meta.get("model") else "")
             + (f" replay `{meta['replay_source']}`" if meta.get("replay_source") else "")
             + f", scorer `{meta.get('scorer')}`, {len(meta.get('fixtures', []))} fixtures x "
             f"{meta.get('trials')} trials, {len(recs)} records.")
    if meta.get("scorer") == "local":
        L.append("")
        L.append("> Scored with `--scorer local` (current interpreter, pins NOT enforced). "
                 "Smoke-test only; not a benchmark result.")
    L += ["", "## Headline: repeat-failure rate", "",
          "Share of scored trials (infra errors excluded) whose solution reproduces the fixture's "
          "known failure. 95% Wilson intervals.", "",
          "| arm | repeat-failure rate | pass rate | other-failure | infra-error |",
          "|---|---|---|---|---|"]
    for a in arms:
        c = by_arm[a]
        n = _scored(c)
        L.append(f"| {a} | {rate_cell(c['known-failure'], n)} | {rate_cell(c['pass'], n)} | "
                 f"{c['other-failure']} | {c['infra-error']} |")
    if "baseline" in by_arm and "mend" in by_arm:
        nb, nm = _scored(by_arm["baseline"]), _scored(by_arm["mend"])
        if nb and nm:
            rb, rm = by_arm["baseline"]["known-failure"] / nb, by_arm["mend"]["known-failure"] / nm
            rel = f"{100 * (rb - rm) / rb:.0f}%" if rb else "n/a"
            L += ["", f"**Baseline -> MEND:** {pct(rb)} -> {pct(rm)} "
                      f"(absolute {100 * (rb - rm):+.1f} pp, relative reduction {rel}).",
                  "Intervals are per-arm; overlapping intervals mean the difference is not established."]
        mend_called = [r.get("mend_tool_called") for r in recs if r["arm"] == "mend"
                       and r.get("mend_tool_called") is not None]
        if mend_called:
            L.append(f"\nMEND MCP tool called in {sum(map(bool, mend_called))}/{len(mend_called)} with-MEND trials.")

    L += ["", "## Outcomes by arm", "", "| arm | " + " | ".join(OUTCOMES) + " | total |",
          "|---" * (len(OUTCOMES) + 2) + "|"]
    for a in arms:
        c = by_arm[a]
        L.append(f"| {a} | " + " | ".join(str(c[o]) for o in OUTCOMES) + f" | {sum(c.values())} |")

    L += ["", "## Per package (repeat-failure rate)", "", "| package | " + " | ".join(arms) + " |",
          "|---" * (len(arms) + 1) + "|"]
    pk: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for r in recs:
        pk[(r["package"], r["arm"])][r["outcome"]] += 1
    for p in sorted({r["package"] for r in recs}):
        cells = []
        for a in arms:
            c = pk[(p, a)]
            cells.append(rate_cell(c["known-failure"], _scored(c)))
        L.append(f"| {p} | " + " | ".join(cells) + " |")

    L += ["", "## Per fixture", "", "| fixture | " + " | ".join(arms) + " |",
          "|---" * (len(arms) + 1) + "|"]
    fx: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for r in recs:
        fx[(r["fixture"], r["arm"])][r["outcome"]] += 1
    abbrev = {"pass": "P", "known-failure": "K", "other-failure": "O", "infra-error": "I"}
    for f in sorted({r["fixture"] for r in recs}):
        cells = [" ".join(f"{abbrev[o]}{fx[(f, a)][o]}" for o in OUTCOMES if fx[(f, a)][o]) or "-"
                 for a in arms]
        L.append(f"| `{f}` | " + " | ".join(cells) + " |")
    L.append("\nP = pass, K = known-failure, O = other-failure, I = infra-error.")

    infra = [r for r in recs if r["outcome"] == "infra-error"]
    if infra:
        L += ["", "## Infra errors", ""]
        for r in infra[:20]:
            L.append(f"- `{r['fixture']}` {r['arm']} t{r['trial']}: {r.get('detail', '')}")
    notes = sorted({n for r in recs for n in r.get("env_notes", [])})
    if notes:
        L += ["", "## Environment notes", ""] + [f"- {n}" for n in notes]
    return "\n".join(L) + "\n"


def write_report(run_dir: Path) -> Path:
    run_dir = Path(run_dir)
    recs, meta = load(run_dir)
    p = run_dir / "report.md"
    p.write_text(render(recs, meta), encoding="utf-8")
    return p


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: python -m bench.report <run-dir>", file=sys.stderr)
        return 2
    p = write_report(Path(argv[0]))
    print(p.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
