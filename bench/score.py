"""Score an agent's target.py with the fixture's own check.

Scorers
-------
* ``uv`` (default, the real benchmark): the same clean-env command `mend verify` uses,
  ``PYTHONPATH=<solution> uv run --isolated --no-project --python <repro.python>
  --with <deps...> --with pytest pytest -q -rfE -p no:cacheprovider <check>``.
* ``local`` (offline smoke runs): the check runs in a subprocess of the *current*
  interpreter via `bench/localcheck.py` (pytest if importable, else a minimal runner).
  Whatever packages that interpreter has are used, so pinned versions are NOT enforced;
  each record notes missing deps / version mismatches. Missing deps -> infra-error.

The check directory is copied into a fresh scoring directory so agents never see or
modify it and repo-level pytest config cannot interfere.

Classification (documented in bench/README.md)
-----------------------------------------------
* ``pass``           check exits 0.
* ``infra-error``    agent crashed / produced no target.py, scorer could not run pytest
                     (uv resolution failure, timeout), or a pinned dep is missing (local).
* ``known-failure``  check fails AND the failure matches the fixture's known failure:
                       (a) a failure signature (test id, exception class name) also occurs
                           when the check is run against the fixture's own bad/target.py
                           under the same scorer (the "bad reference"), or
                       (b) the fixture's `failure.symptom` text (after the exception type)
                           appears in the check output.
* ``other-failure``  check fails any other way (wrong behavior, typo, unrelated error).

Signature (a) is deliberately coarse. For behavior-changed fixtures the bad reference
usually fails with AssertionError in a specific test, so "same test, same exception
class" is the best cheap proxy; it can overcount when a different bug trips the same
assertion. Treat known-failure as an upper bound and inspect raw/ transcripts.
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Any

from bench.common import check_dir, deps_of, get, python_of

LOCALCHECK = Path(__file__).resolve().parent / "localcheck.py"
PYTEST_ARGS = ["-q", "-rfE", "-p", "no:cacheprovider"]

PASS, KNOWN, OTHER, INFRA = "pass", "known-failure", "other-failure", "infra-error"

_E_LINE = re.compile(r"^E\s+([A-Za-z_][\w.]*)(?::|$)", re.M)
_SUMMARY = re.compile(r"^(FAILED|ERROR)\s+(\S+?)(?:\s+-\s+([A-Za-z_][\w.]*)(?::|\s|$).*)?$", re.M)
# pytest's final tally line ("1 failed, 2 passed in 0.1s", "1 error in", "no tests ran"),
# which uv's own resolution errors never produce. Tells "pytest ran" from "env failed".
_PYTEST_TALLY = re.compile(r"\b\d+ (?:passed|failed|errors?)\b|\bno tests ran\b")
_SYMPTOM = re.compile(r"^\s*([A-Za-z_][\w.]*(?:Error|Exception|Warning|Exit|Failure))\s*:\s*(.*)$", re.S)


@dataclass
class ScoreResult:
    outcome: str
    exit_code: int | None = None
    signatures: list[list[str]] = field(default_factory=list)
    match: str | None = None  # why it is known-failure: "bad-signature" | "symptom"
    detail: str = ""
    duration: float = 0.0
    output_tail: str = ""
    env_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- parsing

def short(exc: str) -> str:
    return exc.rsplit(".", 1)[-1]


def _test_id(raw: str) -> str:
    # normalize "check/test_check.py::test_x" / ".../check/test_check.py::test_x"
    parts = raw.split("::")
    parts[0] = Path(parts[0]).name
    return "::".join(parts)


def failure_signatures(output: str) -> set[tuple[str, str]]:
    """(test id, short exception class) for every failed/errored test in pytest output."""
    sigs: set[tuple[str, str]] = set()
    for kind, tid, exc in _SUMMARY.findall(output):
        sigs.add((_test_id(tid), short(exc) if exc else "?"))
    if not sigs:  # no summary (e.g. -q without -r): fall back to E lines
        sigs = {("*", short(e)) for e in _E_LINE.findall(output)}
    return sigs


def symptom_parts(fx: Any) -> tuple[str | None, str | None]:
    s = str(get(fx, "failure", "symptom", default="") or "")
    m = _SYMPTOM.match(s)
    if not m:
        return None, (s.strip() or None)
    return short(m.group(1)), (m.group(2).strip() or None)


def _norm(s: str) -> str:
    return re.sub(r"[\s`'\"]+", " ", s).strip().lower()


def symptom_in_output(fx: Any, output: str) -> bool:
    _, msg = symptom_parts(fx)
    if not msg:
        return False
    needle = _norm(msg)[:60]
    return len(needle) >= 12 and needle in _norm(output)


# --------------------------------------------------------------------------- running

def _run(cmd: list[str], env: dict[str, str], cwd: Path, timeout: float) -> tuple[int, str, bool]:
    proc = subprocess.Popen(cmd, env=env, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, text=True, errors="replace",
                            start_new_session=(os.name == "posix"))
    try:
        out, _ = proc.communicate(timeout=timeout)
        return proc.returncode, out or "", False
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            proc.kill()
        out, _ = proc.communicate()
        return 124, out or "", True


def uv_command(fx: Any, check: Path, offline: bool = False) -> list[str]:
    cmd = ["uv", "run", "--isolated", "--no-project", "--python", python_of(fx)]
    if offline:
        cmd.append("--offline")
    for dep in [*deps_of(fx), "pytest"]:
        cmd += ["--with", dep]
    return [*cmd, "pytest", *PYTEST_ARGS, str(check)]


def local_env_notes(fx: Any) -> tuple[list[str], bool]:
    """(notes, all_deps_present) for the current interpreter vs repro.deps."""
    from packaging.requirements import Requirement

    notes, ok = [f"local scorer: python {sys.version.split()[0]} (pinned {python_of(fx)})"], True
    for d in deps_of(fx):
        try:
            req = Requirement(d)
        except Exception:
            continue
        try:
            have = metadata.version(req.name)
        except metadata.PackageNotFoundError:
            notes.append(f"missing dep {req.name} (pinned {req.specifier})")
            ok = False
            continue
        if req.specifier and not req.specifier.contains(have, prereleases=True):
            notes.append(f"{req.name} {have} != pinned {req.specifier}")
    return notes, ok


def run_check(fx: Any, solution_dir: Path, scorer: str = "uv", timeout: float = 300,
              uv_offline: bool = False) -> tuple[int, str, bool, list[str]]:
    """Run the fixture's check against `solution_dir`. Returns (code, output, ran, notes)."""
    notes: list[str] = []
    with tempfile.TemporaryDirectory(prefix="mend-score-") as tmp:
        tmpd = Path(tmp)
        check = tmpd / "check"
        shutil.copytree(check_dir(fx), check, ignore=shutil.ignore_patterns("__pycache__"))
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.pop("PYTEST_ADDOPTS", None)
        if scorer == "uv":
            if shutil.which("uv") is None:
                return 127, "uv not found on PATH", False, notes
            env["PYTHONPATH"] = str(Path(solution_dir).resolve())
            cmd = uv_command(fx, check, uv_offline)
        elif scorer == "local":
            notes, ok = local_env_notes(fx)
            if not ok:
                return 127, "local scorer: pinned dependency missing in this interpreter", False, notes
            env.pop("PYTHONPATH", None)
            cmd = [sys.executable, "-I", str(LOCALCHECK), str(Path(solution_dir).resolve()), str(check)]
        else:
            raise ValueError(f"unknown scorer {scorer!r}")
        code, out, timed_out = _run(cmd, env, tmpd, timeout)
        # pytest exit codes: 0 ok, 1 tests failed, 2 interrupted/collection error, 5 no tests
        ran = not timed_out and code in (0, 1, 2, 5) and bool(_PYTEST_TALLY.search(out))
        if timed_out:
            notes.append(f"scorer timed out after {timeout}s")
        return code, out, ran, notes


_BAD_CACHE: dict[tuple[str, str], tuple[set[tuple[str, str]], int, list[str]]] = {}


def bad_reference(fx: Any, scorer: str, timeout: float = 300, uv_offline: bool = False):
    """Failure signatures of the fixture's own bad/target.py (cached per fixture+scorer)."""
    key = (str(fx.path), scorer)
    if key not in _BAD_CACHE:
        code, out, ran, notes = run_check(fx, Path(fx.path) / "bad", scorer, timeout, uv_offline)
        sigs = failure_signatures(out) if ran and code != 0 else set()
        _BAD_CACHE[key] = (sigs, code, notes)
    return _BAD_CACHE[key]


def classify(fx: Any, code: int, out: str, ran: bool, bad_sigs: set[tuple[str, str]]) -> tuple[str, str | None, set]:
    if not ran:
        return INFRA, None, set()
    if code == 0:
        return PASS, None, set()
    if code == 5:
        return OTHER, None, set()
    sigs = failure_signatures(out)
    if any(s in bad_sigs or (s[0] == "*" and any(b[1] == s[1] for b in bad_sigs)) for s in sigs):
        return KNOWN, "bad-signature", sigs
    if symptom_in_output(fx, out):
        return KNOWN, "symptom", sigs
    return OTHER, None, sigs


def score(fx: Any, solution_dir: Path, scorer: str = "uv", timeout: float = 300,
          uv_offline: bool = False) -> ScoreResult:
    t0 = time.monotonic()
    if not (Path(solution_dir) / "target.py").is_file():
        return ScoreResult(INFRA, detail="agent produced no target.py")
    bad_sigs, bad_code, _ = bad_reference(fx, scorer, timeout, uv_offline)
    code, out, ran, notes = run_check(fx, solution_dir, scorer, timeout, uv_offline)
    outcome, match, sigs = classify(fx, code, out, ran, bad_sigs)
    detail = ""
    if not ran:
        detail = (out.strip().splitlines() or ["scorer did not run pytest"])[-1][:300]
    elif not bad_sigs:
        detail = f"warning: bad reference did not fail (exit {bad_code}); only symptom matching used"
    tail = "\n".join(out.strip().splitlines()[-40:])
    return ScoreResult(outcome, code, sorted([list(s) for s in sigs]), match, detail,
                       round(time.monotonic() - t0, 2), tail, notes)
