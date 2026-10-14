#!/usr/bin/env python3
"""Which fixtures' bad patterns do existing linters already flag?

For each fixture, run ruff's library rule families, pyupgrade and bump-pydantic on
bad/ and fixed/. A tool "covers" a fixture if it flags bad/ but not fixed/;
"partially" if it flags both. Reviewed verdicts in manual_review.json override the
automatic one.

Usage: python scripts/overlap/run_overlap.py [fixtures_dir] > overlap.md
Prints a markdown table and writes overlap.json to the current directory.
Requires ruff, pyupgrade and bump-pydantic on PATH (missing tools are reported, not fatal).
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


def rewrites(d: Path, cmd: list[str]) -> bool:
    """True if `cmd` rewrites any file. Runs on a temp copy (as ./src), never in place."""
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "src"
        shutil.copytree(d, work)
        before = {p: p.read_text() for p in work.rglob("*.py")}
        # Relative paths: bump-pydantic calls Path.relative_to(".") on its inputs.
        args = [str(p.relative_to(tmp)) for p in before] if cmd[0] == "pyupgrade" else ["src"]
        subprocess.run(cmd + args, capture_output=True, text=True, check=False, cwd=tmp)
        return any(p.read_text() != text for p, text in before.items())


def verdict(bad: bool, fixed: bool) -> str:
    return "partially covered" if bad and fixed else "covered" if bad else "MEND-only"


def main(argv: list[str]) -> int:
    root = Path(argv[0] if argv else "fixtures")
    review = json.loads(REVIEW.read_text()) if REVIEW.is_file() else {}
    tools = {
        "pyupgrade": ["pyupgrade", "--py313-plus"],
        "bump-pydantic": ["bump-pydantic", "--log-file", "bump.log"],
    }
    have_ruff = shutil.which("ruff")
    rows, counts, results = [], {}, []
    for fx in sorted(p.parent for p in root.glob("*/*/fixture.yaml")):
        result = {"id": fx.name}
        cells, auto = [], "MEND-only"
        if have_ruff:
            codes_bad, codes_fixed = ruff_codes(fx / "bad"), ruff_codes(fx / "fixed")
            result["ruff"] = {"bad": sorted(codes_bad), "fixed": sorted(codes_fixed)}
            cells.append(", ".join(sorted(codes_bad)) or "-")
            if codes_bad:
                auto = verdict(True, bool(codes_bad & codes_fixed))
        else:
            cells.append("not installed")
        for name, cmd in tools.items():
            if not shutil.which(cmd[0]):
                cells.append("not installed")
                continue
            bad, fixed = rewrites(fx / "bad", cmd), rewrites(fx / "fixed", cmd)
            result[name] = {"bad": bad, "fixed": fixed}
            cells.append("rewrites" + (" (also fixed)" if fixed else "") if bad else "-")
            # A rewrite that also touches fixed/ is modernisation, not this migration.
            if bad and not fixed and auto == "MEND-only" and name == "bump-pydantic":
                auto = "covered"
        reviewed = review.get(fx.name, {}).get("verdict", "")
        result.update(auto=auto, reviewed=reviewed)
        results.append(result)
        final = reviewed or auto
        counts[final] = counts.get(final, 0) + 1
        flag = " **(differs)**" if reviewed and reviewed != auto else ""
        rows.append(f"| {fx.name} | {' | '.join(cells)} | {auto} | {reviewed}{flag} |")

    Path("overlap.json").write_text(json.dumps(results, indent=2) + "\n")
    print("| fixture | ruff (" + RUFF_RULES + ") | pyupgrade | bump-pydantic | auto | reviewed |")
    print("|---|---|---|---|---|---|")
    print("\n".join(rows))
    print("\nCounts: " + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
