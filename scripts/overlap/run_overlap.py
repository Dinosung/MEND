#!/usr/bin/env python3
"""Which fixtures' bad patterns do existing linters already flag?

For each fixture, run ruff's library rule families and bump-pydantic on bad/ and
fixed/. A tool "covers" a fixture if it flags bad/ but not fixed/; "partially" if it
flags both. Reviewed verdicts in manual_review.json override the automatic one.

Usage: python scripts/overlap/run_overlap.py [fixtures_dir] > overlap.md
Requires ruff and bump-pydantic on PATH (missing tools are reported, not fatal).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RUFF_RULES = "NPY,PD,FAST,AIR"
REVIEW = Path(__file__).with_name("manual_review.json")


def ruff_codes(d: Path) -> set[str]:
    out = subprocess.run(
        ["ruff", "check", "--isolated", "--no-cache", "--exit-zero", "--preview",
         "--select", RUFF_RULES, "--output-format", "json", str(d)],
        capture_output=True, text=True, check=False).stdout
    return {f["code"] for f in json.loads(out or "[]")}


def bump_pydantic_changes(d: Path) -> bool:
    """True if bump-pydantic rewrites anything (run on a temp copy, never in place)."""
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "src"
        shutil.copytree(d, work)
        before = {p: p.read_text() for p in work.rglob("*.py")}
        subprocess.run(["bump-pydantic", "--log-file", str(Path(tmp) / "log"), str(work)],
                       capture_output=True, text=True, check=False, cwd=tmp)
        return any(p.read_text() != text for p, text in before.items())


def verdict(bad: bool, fixed: bool) -> str:
    return "partially covered" if bad and fixed else "covered" if bad else "MEND-only"


def main(argv: list[str]) -> int:
    root = Path(argv[0] if argv else "fixtures")
    review = json.loads(REVIEW.read_text()) if REVIEW.is_file() else {}
    have_ruff, have_bump = shutil.which("ruff"), shutil.which("bump-pydantic")
    rows, counts = [], {}
    for fx in sorted(p.parent for p in root.glob("*/*/fixture.yaml")):
        cells, auto = [], "MEND-only"
        if have_ruff:
            codes_bad, codes_fixed = ruff_codes(fx / "bad"), ruff_codes(fx / "fixed")
            hits = sorted(codes_bad)
            cells.append(", ".join(hits) or "-")
            if hits:
                auto = verdict(True, bool(codes_bad & codes_fixed))
        else:
            cells.append("not installed")
        if have_bump and fx.parent.name == "pydantic":
            bad, fixed = bump_pydantic_changes(fx / "bad"), bump_pydantic_changes(fx / "fixed")
            cells.append("rewrites" + (" (also fixed)" if fixed else "") if bad else "-")
            if bad and auto == "MEND-only":
                auto = verdict(bad, fixed)
        else:
            cells.append("not installed" if fx.parent.name == "pydantic" else "n/a")
        reviewed = review.get(fx.name, {}).get("verdict", "")
        final = reviewed or auto
        counts[final] = counts.get(final, 0) + 1
        flag = " **(differs)**" if reviewed and reviewed != auto else ""
        rows.append(f"| {fx.name} | {' | '.join(cells)} | {auto} | {reviewed}{flag} |")

    print("| fixture | ruff (" + RUFF_RULES + ") | bump-pydantic | auto | reviewed |")
    print("|---|---|---|---|---|")
    print("\n".join(rows))
    print("\nCounts: " + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
