"""Paired statistics for the pilot.

A trial "fails" when its outcome is known-failure (the fixture's failure was repeated).
Infra errors are excluded. Per task and arm, the failure rate is fails / scored trials.

* arm failure rate over trials, with a Wilson 95% interval (trials of one task are not
  independent, so treat it as descriptive);
* paired difference B - A: mean over tasks scored in both arms of the per-task failure-rate
  difference, with a percentile bootstrap 95% CI that resamples tasks;
* exact McNemar test on the per-task majority outcome (failure if rate >= 0.5).
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Any

FAIL = "known-failure"
INFRA = "infra-error"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, mid - half), min(1.0, mid + half))


def task_rates(records: list[dict[str, Any]], arm: str) -> dict[str, float]:
    fails: dict[str, int] = defaultdict(int)
    n: dict[str, int] = defaultdict(int)
    for r in records:
        if r["arm"] == arm and r["outcome"] != INFRA:
            n[r["fixture"]] += 1
            fails[r["fixture"]] += r["outcome"] == FAIL
    return {t: fails[t] / n[t] for t in n}


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value from discordant counts b and c."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def bootstrap_ci(values: list[float], iters: int = 10000, seed: int = 0) -> tuple[float, float]:
    if not values:
        return (math.nan, math.nan)
    rng = random.Random(seed)
    means = sorted(sum(rng.choices(values, k=len(values))) / len(values) for _ in range(iters))
    return (means[int(0.025 * iters)], means[int(0.975 * iters) - 1])


def arm_summary(records: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    rs = [r for r in records if r["arm"] == arm]
    scored = [r for r in rs if r["outcome"] != INFRA]
    k = sum(r["outcome"] == FAIL for r in scored)
    lo, hi = wilson(k, len(scored))
    return {"arm": arm, "trials": len(rs), "scored": len(scored), "infra": len(rs) - len(scored),
            "failures": k, "other_failures": sum(r["outcome"] == "other-failure" for r in scored),
            "passes": sum(r["outcome"] == "pass" for r in scored),
            "failure_rate": k / len(scored) if scored else None, "wilson95": [lo, hi]}


def paired(records: list[dict[str, Any]], a: str, b: str) -> dict[str, Any]:
    """Effect of arm b relative to arm a (negative = b fails less)."""
    ra, rb = task_rates(records, a), task_rates(records, b)
    tasks = sorted(set(ra) & set(rb))
    diffs = [rb[t] - ra[t] for t in tasks]
    fa = {t: ra[t] >= 0.5 for t in tasks}
    fb = {t: rb[t] >= 0.5 for t in tasks}
    only_a = sum(fa[t] and not fb[t] for t in tasks)  # b rescued
    only_b = sum(fb[t] and not fa[t] for t in tasks)  # b broke
    return {"a": a, "b": b, "tasks": len(tasks),
            "mean_diff": sum(diffs) / len(diffs) if diffs else None,
            "bootstrap95": list(bootstrap_ci(diffs)),
            "mcnemar": {"a_fail_only": only_a, "b_fail_only": only_b,
                        "p": mcnemar_exact(only_a, only_b)}}


def hook_rates(records: list[dict[str, Any]], arm: str = "A4") -> dict[str, Any]:
    rs = [r for r in records if r["arm"] == arm and r.get("hooks")]
    n = len(rs)
    if not n:
        return {"trials": 0}
    return {"trials": n,
            "session_start_injected": sum(r["hooks"]["session_start_injected"] for r in rs) / n,
            "post_tool_use_fired": sum(r["hooks"]["post_tool_use_calls"] > 0 for r in rs) / n,
            "blocked": sum(r["hooks"]["post_tool_use_blocks"] > 0 for r in rs) / n,
            "total_blocks": sum(r["hooks"]["post_tool_use_blocks"] for r in rs),
            "hook_errors": sum(r["hooks"]["hook_errors"] for r in rs)}
