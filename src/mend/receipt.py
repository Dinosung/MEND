"""`mend receipt`: do the original tests pass with only the agent's source changes?

1. Collect the change set vs the base commit (committed + uncommitted + untracked).
2. Split it: protected files (tests, conftest.py, pytest/coverage config, CI workflows) vs source.
3. Check out the base into a temporary git worktree, apply only the source changes (and
   test files the agent *added*, except conftest.py), keep the base's protected files.
4. Run the test command there (and in the agent's own tree when they differ); compare with
   the agent's claim. Only a failing re-run gives a blocking verdict (exit 1).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_TEST_CMD = "python -m pytest -q"
TIMEOUT = 900
BLOCKING = {"NOT PROVEN", "CLAIM MISMATCH"}
TEST_CONFIG = {"pytest.ini", "tox.ini"}
SECTIONED = {"pyproject.toml", "setup.cfg"}  # only their pytest/coverage sections are protected
PROTECTED_SECTION = re.compile(r"\[\s*(tool\.pytest|tool\.coverage|tool:pytest|coverage:)")
_TALLY = re.compile(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed)\b")
_TEST_DEF = re.compile(r"^\s*(?:async\s+)?def (test\w*)", re.MULTILINE)
_SKIP = re.compile(r"pytest\.mark\.skip|pytest\.skip\(|unittest\.skip|\.skipTest\(")
_XFAIL = re.compile(r"xfail")
_CLAIM_PASS = re.compile(
    r"\ball (?:of )?(?:the )?(?:\d+ )?tests? (?:now )?(?:pass|passed|are passing|succeed)"
    r"|\btests? (?:now )?(?:all )?(?:pass|passes|passed|are passing)\b|\b\d+ passed\b|\ball green\b", re.IGNORECASE)
_CLAIM_FAIL = re.compile(r"\b[1-9]\d* (?:tests? )?(?:failed|failing|failures?|errors?)\b"
                         r"|\btests? (?:still )?fail|\bnot all (?:the )?tests", re.IGNORECASE)


def _git(repo: Path | str, *args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout if r.returncode == 0 else ""


def kind(path: str) -> str:
    """'ci', 'config', 'test' (protected) or 'source'."""
    p = Path(path)
    if p.parts[:2] == (".github", "workflows"):
        return "ci"
    if p.name in TEST_CONFIG:
        return "config"
    if (p.name == "conftest.py" or any(d in ("tests", "test") for d in p.parts[:-1])
            or (p.suffix == ".py" and (p.name.startswith("test_") or p.stem.endswith("_test")))):
        return "test"
    return "source"


def default_base(root: Path) -> str:
    """Merge-base with the default branch, else HEAD (uncommitted work)."""
    for ref in ("origin/HEAD", "origin/main", "origin/master", "main", "master"):
        sha = _git(root, "merge-base", "HEAD", ref, check=False).strip()
        if sha:
            return sha
    return _git(root, "rev-parse", "HEAD").strip()


def changed_files(root: Path, base: str) -> list[str]:
    tracked = _git(root, "diff", "--name-only", "--no-renames", "-z", base).split("\0")
    untracked = _git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0")
    return sorted({p for p in tracked + untracked if p})


def _sections(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = [("", "")]
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("["):
            out.append((line.strip(), ""))
        out[-1] = (out[-1][0], out[-1][1] + line)
    return out


def protect_sections(agent: str, base: str) -> tuple[str, bool]:
    """The agent's file with the base's pytest/coverage sections. Returns (text, changed)."""
    a_prot, b_prot = ([t for h, t in _sections(x) if PROTECTED_SECTION.match(h)] for x in (agent, base))
    if a_prot == b_prot:
        return agent, False
    keep = [t for h, t in _sections(agent) if not PROTECTED_SECTION.match(h)] + b_prot
    return "".join(t if t.endswith("\n") else t + "\n" for t in keep if t), True


def build_clean_tree(root: Path, base: str, changed: list[str], dest: Path) -> dict[str, list[str]]:
    _git(root, "worktree", "add", "--detach", "--quiet", str(dest), base)
    tree: dict[str, list[str]] = {"applied": [], "protected": [], "added_tests": []}
    for rel in changed:
        src, dst = root / rel, dest / rel
        if src.is_dir() or dst.is_dir():  # submodules, nested repos
            continue
        at_base = dst.exists() or dst.is_symlink()
        k = kind(rel)
        if k == "test" and not at_base and Path(rel).name != "conftest.py" and src.is_file():
            tree["added_tests"].append(rel)
        elif k != "source":
            tree["protected"].append(rel)
            continue
        elif Path(rel).name in SECTIONED and src.is_file():
            text, touched = protect_sections(src.read_text(), dst.read_text() if at_base else "")
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(text)
            tree["applied"].append(rel)
            if touched:
                tree["protected"].append(f"{rel} (pytest/coverage sections)")
            continue
        else:
            tree["applied"].append(rel)
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
        elif at_base:
            dst.unlink()
    return tree


def run_tests(cmd: str, cwd: Path) -> dict:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    env["PYTEST_ADDOPTS"] = (env.get("PYTEST_ADDOPTS", "") + " -p no:cacheprovider").strip()
    try:
        r = subprocess.run(cmd, shell=True, cwd=cwd, env=env, capture_output=True, text=True,
                           timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return {"exit": None, "counts": {}, "summary": f"timed out after {TIMEOUT}s", "failures": []}
    out = r.stdout + r.stderr
    lines = [ln for ln in out.splitlines() if _TALLY.search(ln) or "no tests ran" in ln]
    summary = lines[-1].strip(" =") if lines else ""
    counts = {("errors" if w.startswith("error") else w): int(n) for n, w in _TALLY.findall(summary)}
    if r.returncode == 5 or "no tests ran" in summary:
        counts["no_tests"] = 1
    failures = [ln for ln in out.splitlines() if ln.startswith(("FAILED ", "ERROR "))]
    return {"exit": r.returncode, "counts": counts, "failures": failures[:10],
            "failed_ids": sorted({ln.split()[1] for ln in failures if len(ln.split()) > 1}),
            "summary": summary or f"exit code {r.returncode}"}


def count_test_changes(root: Path, base: str, paths: list[str]) -> dict:
    removed, skip, xfail = [], 0, 0
    for rel in paths:
        if not rel.endswith(".py"):
            continue
        old = _git(root, "show", f"{base}:{rel}", check=False)
        new = (root / rel).read_text(errors="replace") if (root / rel).is_file() else ""
        removed += [f"{rel}::{n}" for n in sorted(set(_TEST_DEF.findall(old)) - set(_TEST_DEF.findall(new)))]
        skip += len(_SKIP.findall(new)) - len(_SKIP.findall(old))
        xfail += len(_XFAIL.findall(new)) - len(_XFAIL.findall(old))
    return {"removed_tests": removed, "skip_added": skip, "xfail_added": xfail}


def parse_claim(text: str | None) -> dict | None:
    if not text or not text.strip():
        return None
    m = _CLAIM_PASS.search(text)
    n = re.search(r"\b(\d+) (?:tests? )?passed\b", text, re.IGNORECASE)
    return {"claims_pass": bool(m) and not _CLAIM_FAIL.search(text),
            "passed": int(n.group(1)) if n else None, "quote": m.group(0) if m else ""}


def verdict(clean: dict, claim: dict | None, protected: list[str]) -> str:
    if clean["exit"] != 0 or clean["counts"].get("no_tests"):
        return "CLAIM MISMATCH" if claim and claim["claims_pass"] else "NOT PROVEN"
    return "NEEDS REVIEW" if protected else "PROVEN"


def receipt(repo: str | Path = ".", base: str | None = None, test_cmd: str = DEFAULT_TEST_CMD,
            claim_text: str | None = None) -> dict:
    root = Path(_git(repo, "rev-parse", "--show-toplevel").strip())
    base = _git(root, "rev-parse", "--verify", f"{base}^{{commit}}").strip() if base else default_base(root)
    changed = changed_files(root, base)
    with tempfile.TemporaryDirectory(prefix="mend-receipt-") as tmp:
        dest, at_base = Path(tmp) / "clean", Path(tmp) / "base"
        try:
            tree = build_clean_tree(root, base, changed, dest)
            clean = run_tests(test_cmd, dest)
            # Failures that already happen at the base commit are not the agent's doing.
            pre_existing = False
            if clean["failed_ids"]:
                _git(root, "worktree", "add", "--detach", "--quiet", str(at_base), base)
                before = run_tests(test_cmd, at_base)
                pre_existing = set(clean["failed_ids"]) <= set(before["failed_ids"])
        finally:
            for d in (dest, at_base):
                _git(root, "worktree", "remove", "--force", str(d), check=False)
            _git(root, "worktree", "prune", check=False)
    same = not tree["protected"] and not tree["added_tests"]
    agent = clean if same else run_tests(test_cmd, root)
    claim = parse_claim(claim_text)
    tests = [p for p in changed if kind(p) == "test"]
    return {"verdict": verdict(clean, claim, tree["protected"]), "base": base, "test_cmd": test_cmd,
            "clean": clean, "agent": agent, "agent_same_tree": same, "claim": claim,
            "pre_existing": pre_existing, **tree,
            **count_test_changes(root, base, tests)}


_SENTENCE = {
    "PROVEN": "The original tests pass with only the agent's source changes applied.",
    "NOT PROVEN": "The original tests do not pass with only the agent's source changes applied.",
    "CLAIM MISMATCH": "The agent's message claims passing tests; the original tests do not pass "
                      "with only its source changes applied.",
    "NEEDS REVIEW": "The original tests pass with only the agent's source changes applied; "
                    "the agent also edited protected files (listed below).",
}


def _short(paths: list[str]) -> str:
    return ", ".join(paths[:8]) + (f" (+{len(paths) - 8} more)" if len(paths) > 8 else "")


def render(r: dict) -> str:
    claim = r["claim"]
    said = "none given" if not claim else (
        f"claims passing (\"{claim['quote']}\")" if claim["claims_pass"] else "no passing-tests claim found")
    agent = "same tree (no protected files changed)" if r["agent_same_tree"] else r["agent"]["summary"]
    lines = [f"## MEND receipt: {r['verdict']}", "", _SENTENCE[r["verdict"]], "",
             "| Run | Result |", "|---|---|",
             f"| Original tests + agent's source changes | {r['clean']['summary']} |",
             f"| Agent's own tree (with its test edits) | {agent} |",
             f"| Agent's claim | {said} |", "",
             f"- Base commit: `{r['base'][:12]}`", f"- Test command: `{r['test_cmd']}`",
             f"- Source files applied ({len(r['applied'])}): {_short(r['applied']) or 'none'}"]
    if r["protected"]:
        lines.append(f"- Protected files edited, base version used ({len(r['protected'])}): "
                     f"{_short(r['protected'])}")
    if r["added_tests"]:
        lines.append(f"- Test files added by the agent, run with the originals: {_short(r['added_tests'])}")
    if r["removed_tests"] or r["skip_added"] or r["xfail_added"]:
        lines.append(f"- Test-file changes: {len(r['removed_tests'])} test(s) removed"
                     f"{' (' + _short(r['removed_tests']) + ')' if r['removed_tests'] else ''}, "
                     f"skip markers {r['skip_added']:+d}, xfail markers {r['xfail_added']:+d}")
    if r["pre_existing"]:
        lines.append("- All of these failures also happen at the base commit (pre-existing).")
    lines += [f"- {f}" for f in r["clean"]["failures"]]
    return "\n".join(lines)


def _last_assistant_text(data: dict) -> str:
    if data.get("last_assistant_message"):
        return str(data["last_assistant_message"])
    try:
        rows = Path(data["transcript_path"]).read_text().splitlines()
    except (KeyError, TypeError, OSError):
        return ""
    for row in reversed(rows):
        try:
            obj = json.loads(row)
        except ValueError:
            continue
        if obj.get("type") != "assistant":
            continue
        content = (obj.get("message") or {}).get("content")
        text = content if isinstance(content, str) else "\n".join(
            b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text")
        if text.strip():
            return text
    return ""


def hook_stop(raw: str, test_cmd: str) -> int:
    """Claude Code Stop hook: exit 2 with the receipt on stderr only when the re-run fails."""
    try:
        data = json.loads(raw or "{}")
        root = Path(_git(data.get("cwd") or ".", "rev-parse", "--show-toplevel").strip())
        if not changed_files(root, default_base(root)):
            return 0
        r = receipt(root, None, test_cmd, _last_assistant_text(data))
    except Exception:  # a hook must never break the session
        return 0
    counts = r["clean"]["counts"]
    # Block on a false "tests pass" claim, or on failures the agent introduced. Failures that
    # already happen at the base, with no claim that they were fixed, are not worth blocking.
    claim_mismatch = r["verdict"] == "CLAIM MISMATCH" and counts
    new_failures = (r["verdict"] == "NOT PROVEN" and not r["pre_existing"]
                    and counts.get("failed", 0) + counts.get("errors", 0))
    if not (claim_mismatch or new_failures):
        return 0
    text = "MEND receipt (re-run of the original tests with only the source changes applied):\n\n" + render(r)
    if data.get("stop_hook_active"):  # loop guard: already continued once, so report to the user
        print(json.dumps({"systemMessage": text}))
        return 0
    print(text, file=sys.stderr)
    return 2


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="mend receipt", description=__doc__.splitlines()[0])
    ap.add_argument("repo", nargs="?", default=".", help="git repository (default: cwd)")
    ap.add_argument("--base", help="commit the agent started from (default: merge-base with main)")
    ap.add_argument("--test-cmd", default=os.environ.get("MEND_TEST_CMD", DEFAULT_TEST_CMD))
    ap.add_argument("--claim", help="the agent's final message")
    ap.add_argument("--claim-file", help="file holding the agent's final message")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--hook", choices=["stop"], help="run as a Claude Code Stop hook (JSON on stdin)")
    args = ap.parse_args(argv)
    if args.hook:
        return hook_stop(sys.stdin.read(), args.test_cmd)
    claim = Path(args.claim_file).read_text() if args.claim_file else args.claim
    try:
        r = receipt(args.repo, args.base, args.test_cmd, claim)
    except RuntimeError as e:
        print(f"mend receipt: {e}", file=sys.stderr)
        return 2
    print(json.dumps(r, indent=2) if args.json else render(r))
    return 1 if r["verdict"] in BLOCKING else 0
