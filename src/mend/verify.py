"""Verify fixtures: `check/` must fail against `bad/` and pass against `fixed/`.

Each side runs in a fresh, isolated environment containing exactly `repro.deps`
plus pytest (see "Verification contract" in docs/FIXTURE_SPEC.md):

* ``uv`` backend: ``uv run --isolated --no-project --python <X> --with <dep>...
  --with pytest pytest -q -p no:cacheprovider <fixture>/check``
* ``docker`` backend: ``python:<X>-slim`` with the fixture mounted read-only,
  ``pip install <deps> pytest`` then the same pytest invocation.

pytest is asked to write a JUnit XML report into a scratch directory. If no
report appears, pytest never ran (resolver/network/interpreter failure) and the
result is an *infrastructure error*, not a verdict on the fixture.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from mend.fixture import Fixture, FixtureError, load_all, resolve_root

Backend = Literal["uv", "docker"]
Side = Literal["bad", "fixed"]
BACKENDS: tuple[str, ...] = ("uv", "docker")
PYTEST_REQUIREMENT = "pytest"
PYTEST_ARGS = ["-q", "-p", "no:cacheprovider"]
REPORT_NAME = "report.xml"
LOG_TAIL_LINES = 40

# pytest exit codes: https://docs.pytest.org/en/stable/reference/exit-codes.html
EXIT_OK, EXIT_TESTS_FAILED, EXIT_INTERRUPTED = 0, 1, 2
EXIT_INTERNAL, EXIT_USAGE, EXIT_NO_TESTS = 3, 4, 5
TIMEOUT_EXIT = -1


@dataclass
class RunResult:
    """One pytest run (bad or fixed side)."""

    exit_code: int
    duration: float
    output: str
    pytest_ran: bool
    timed_out: bool = False


@dataclass
class VerifyResult:
    fixture_id: str
    ok: bool
    bad_failed: bool
    fixed_passed: bool
    reason: str
    #: True when the outcome says nothing about the fixture (tooling/network/timeout).
    infra_error: bool = False
    bad_exit: int | None = None
    fixed_exit: int | None = None
    durations: dict[str, float] = field(default_factory=dict)
    logs: dict[str, str] = field(default_factory=dict)
    path: str = ""

    @property
    def outcome(self) -> str:
        return "ok" if self.ok else ("error" if self.infra_error else "fail")

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["outcome"] = self.outcome
        return data


def _tail(text: str, lines: int = LOG_TAIL_LINES) -> str:
    return "\n".join(text.rstrip().splitlines()[-lines:])


# --------------------------------------------------------------------------- commands


def uv_command(fixture: Fixture, pytest_extra: Sequence[str] = ()) -> list[str]:
    """The reference command from the spec (PYTHONPATH is set via the environment).

    `pytest_extra` is inserted before the check dir; `run_side` uses it only to add
    `--junitxml`, which lets us tell "pytest ran" apart from "uv failed".
    """
    cmd = ["uv", "run", "--isolated", "--no-project", "--python", fixture.repro.python]
    for dep in [*fixture.repro.deps, PYTEST_REQUIREMENT]:
        cmd += ["--with", dep]
    return [*cmd, "pytest", *PYTEST_ARGS, *pytest_extra, str(fixture.check_dir)]


def docker_image(fixture: Fixture) -> str:
    return f"python:{fixture.repro.python}-slim"


def docker_command(fixture: Fixture, side: Side, out_dir: Path, name: str) -> list[str]:
    deps = [*fixture.repro.deps, PYTEST_REQUIREMENT]
    script = (
        "pip install --quiet --disable-pip-version-check --no-cache-dir --root-user-action=ignore "
        f"{shlex.join(deps)} && exec python -m pytest {shlex.join(PYTEST_ARGS)} "
        f"--junitxml=/out/{REPORT_NAME} /fixture/check"
    )
    return [
        "docker", "run", "--rm", "--name", name,
        "-v", f"{fixture.path}:/fixture:ro",
        "-v", f"{out_dir}:/out",
        "-e", f"PYTHONPATH=/fixture/{side}",
        "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-w", "/tmp",
        docker_image(fixture),
        "sh", "-c", script,
    ]  # fmt: skip


# --------------------------------------------------------------------------- running


def _run(cmd: list[str], env: dict[str, str], cwd: Path, timeout: float) -> tuple[int, str, bool]:
    """Run `cmd`, returning (exit code, combined output, timed_out). Kills the whole group on timeout."""
    proc = subprocess.Popen(
        cmd,
        env=env,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        errors="replace",
        start_new_session=(os.name == "posix"),
    )
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
        return TIMEOUT_EXIT, out or "", True


def run_side(fixture: Fixture, side: Side, backend: Backend = "uv", timeout: float = 300) -> RunResult:
    """Run `check/` against `bad/` or `fixed/` in a fresh environment."""
    with tempfile.TemporaryDirectory(prefix=f"mend-{side}-") as tmp:
        out_dir = Path(tmp)
        report = out_dir / REPORT_NAME
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        container: str | None = None
        if backend == "uv":
            cmd = uv_command(fixture, [f"--junitxml={report}"])
            env["PYTHONPATH"] = str(fixture.path / side)
        elif backend == "docker":
            os.chmod(out_dir, 0o777)  # container may run as a different uid
            container = f"mend-verify-{uuid.uuid4().hex[:12]}"
            cmd = docker_command(fixture, side, out_dir, container)
        else:
            raise ValueError(f"unknown backend {backend!r}; expected one of {BACKENDS}")

        start = time.monotonic()
        try:
            code, output, timed_out = _run(cmd, env, fixture.path, timeout)
        except OSError as exc:  # e.g. executable missing
            code, output, timed_out = 127, f"{cmd[0]}: {exc}", False
        duration = time.monotonic() - start
        if timed_out and container:
            subprocess.run(["docker", "rm", "-f", container], capture_output=True, check=False)
        return RunResult(
            exit_code=code,
            duration=round(duration, 2),
            output=output,
            pytest_ran=report.is_file(),
            timed_out=timed_out,
        )


def _check_backend(backend: str) -> str | None:
    if backend not in BACKENDS:
        return f"unknown backend {backend!r}; expected one of {', '.join(BACKENDS)}"
    if shutil.which(backend) is None:
        return f"{backend} executable not found on PATH"
    return None


def evaluate(fixture_id: str, fixed: RunResult, bad: RunResult | None) -> VerifyResult:
    """Turn the two runs into a verdict. Pure logic; unit-testable without subprocesses."""
    res = VerifyResult(fixture_id=fixture_id, ok=False, bad_failed=False, fixed_passed=False, reason="")
    res.fixed_exit = fixed.exit_code
    res.durations["fixed"] = fixed.duration
    res.logs["fixed"] = _tail(fixed.output)
    res.fixed_passed = fixed.pytest_ran and fixed.exit_code == EXIT_OK

    if fixed.timed_out:
        res.infra_error, res.reason = True, "fixed run timed out"
        return res
    if not fixed.pytest_ran:
        res.infra_error = True
        res.reason = f"fixed run: environment setup failed before pytest ran (exit {fixed.exit_code})"
        return res
    if fixed.exit_code == EXIT_TESTS_FAILED:
        res.reason = "fixed/ does not pass check/ (tests failed)"
        return res
    if fixed.exit_code == EXIT_NO_TESTS:
        res.reason = "check/ collected no tests"
        return res
    if fixed.exit_code != EXIT_OK:
        res.infra_error = True
        res.reason = f"fixed run: pytest error exit {fixed.exit_code} (collection/usage/internal error)"
        return res

    assert bad is not None, "bad run required once fixed passes"
    res.bad_exit = bad.exit_code
    res.durations["bad"] = bad.duration
    res.logs["bad"] = _tail(bad.output)
    if bad.timed_out:
        res.infra_error, res.reason = True, "bad run timed out"
        return res
    if not bad.pytest_ran:
        res.infra_error = True
        res.reason = f"bad run: environment setup failed before pytest ran (exit {bad.exit_code})"
        return res
    if bad.exit_code == EXIT_OK:
        res.reason = "bad/ passes check/ (failure not reproduced)"
        return res
    if bad.exit_code in (EXIT_TESTS_FAILED, EXIT_INTERRUPTED):
        res.bad_failed = True
        res.ok = True
        res.reason = "verified" if bad.exit_code == EXIT_TESTS_FAILED else "verified (bad fails at collection)"
        return res
    res.infra_error = True
    res.reason = f"bad run: unexpected pytest exit {bad.exit_code}"
    return res


def verify_fixture(fixture: Fixture, backend: Backend = "uv", timeout: float = 300) -> VerifyResult:
    """Verify one fixture. The fixed side runs first: if it can't pass, the bad side is moot."""
    problem = _check_backend(backend)
    if problem:
        return VerifyResult(
            fixture_id=fixture.id, ok=False, bad_failed=False, fixed_passed=False,
            reason=problem, infra_error=True, path=str(fixture.path),
        )  # fmt: skip
    fixed = run_side(fixture, "fixed", backend, timeout)
    bad = run_side(fixture, "bad", backend, timeout) if fixed.pytest_ran and fixed.exit_code == EXIT_OK else None
    result = evaluate(fixture.id, fixed, bad)
    result.path = str(fixture.path)
    return result


# --------------------------------------------------------------------------- selection


def _git(args: list[str], cwd: Path) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def changed_files(ref: str, cwd: Path | None = None) -> set[Path]:
    """Files changed since the merge-base with `ref` (committed, uncommitted and untracked)."""
    cwd = cwd or Path.cwd()
    top = Path(_git(["rev-parse", "--show-toplevel"], cwd).strip())
    base = _git(["merge-base", ref, "HEAD"], cwd).strip()
    names = _git(["diff", "--name-only", base], cwd).splitlines()
    names += _git(["ls-files", "--others", "--exclude-standard"], cwd).splitlines()
    return {(top / n).resolve() for n in names if n}


def filter_changed(fixtures: Sequence[Fixture], changed: set[Path]) -> list[Fixture]:
    return [fx for fx in fixtures if any(p == fx.path or fx.path in p.parents for p in changed)]


def select_fixtures(paths: Sequence[str]) -> list[Fixture]:
    if not paths:
        return load_all(None)
    seen: dict[Path, Fixture] = {}
    for p in paths:
        for fx in load_all(p):
            seen.setdefault(fx.path, fx)
    return list(seen.values())


# --------------------------------------------------------------------------- CLI


def _table(results: Sequence[VerifyResult]) -> str:
    headers = ["ID", "RESULT", "BAD", "FIXED", "TIME", "REASON"]
    rows = [
        [
            r.fixture_id,
            r.outcome.upper(),
            "-" if r.bad_exit is None else str(r.bad_exit),
            "-" if r.fixed_exit is None else str(r.fixed_exit),
            f"{sum(r.durations.values()):.1f}s",
            r.reason,
        ]
        for r in results
    ]
    widths = [max([len(h), *(len(row[i]) for row in rows)]) for i, h in enumerate(headers)]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    lines = [fmt.format(*headers), fmt.format(*("-" * w for w in widths)), *(fmt.format(*r) for r in rows)]
    return "\n".join(line.rstrip() for line in lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mend verify", description="Verify fixtures: check/ must fail on bad/ and pass on fixed/."
    )
    parser.add_argument("paths", nargs="*", help="fixture dirs or catalog roots (default: $MEND_FIXTURES_DIR or ./fixtures)")
    parser.add_argument("--backend", choices=BACKENDS, default="uv")
    parser.add_argument("--json", action="store_true", help="emit a JSON report on stdout")
    parser.add_argument("--changed-since", metavar="REF", help="only fixtures with files changed vs this git ref")
    parser.add_argument("-j", "--jobs", type=int, default=4, help="concurrent verifications (default 4)")
    parser.add_argument("--timeout", type=float, default=300, help="seconds per pytest run (default 300)")
    parser.add_argument("-v", "--verbose", action="store_true", help="print log tails of failing fixtures")
    args = parser.parse_args(argv)

    try:
        fixtures = select_fixtures(args.paths)
    except FixtureError as exc:
        print(f"mend verify: {exc}", file=sys.stderr)
        return 2
    if args.changed_since:
        try:
            fixtures = filter_changed(fixtures, changed_files(args.changed_since))
        except RuntimeError as exc:
            print(f"mend verify: {exc}", file=sys.stderr)
            return 2

    results: list[VerifyResult] = []
    if fixtures:
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            futures = {pool.submit(verify_fixture, fx, args.backend, args.timeout): fx for fx in fixtures}
            for fut in as_completed(futures):
                res = fut.result()
                results.append(res)
                print(f"[{len(results)}/{len(fixtures)}] {res.outcome.upper():<5} {res.fixture_id}", file=sys.stderr)
    results.sort(key=lambda r: r.fixture_id)

    n_ok = sum(r.ok for r in results)
    n_err = sum(r.infra_error for r in results)
    n_fail = len(results) - n_ok - n_err
    if args.json:
        report = {
            "backend": args.backend,
            "root": str(resolve_root(None)) if not args.paths else None,
            "changed_since": args.changed_since,
            "summary": {"total": len(results), "ok": n_ok, "fail": n_fail, "error": n_err},
            "results": [r.to_dict() for r in results],
        }
        print(json.dumps(report, indent=2))
    elif not results:
        print("no fixtures to verify")
    else:
        print(_table(results))
        if args.verbose:
            for r in results:
                if not r.ok:
                    for side, log in r.logs.items():
                        print(f"\n--- {r.fixture_id} [{side}] ---\n{log}")
        print(f"\n{len(results)} fixture(s): {n_ok} ok, {n_fail} failed, {n_err} infrastructure error(s)")
    return 0 if n_ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
