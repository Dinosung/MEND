"""Source-only scoring against the hidden test.

1. Sanitize: copy the agent's workdir, dropping tests, pytest config, conftest.py,
   sitecustomize/usercustomize, .pth files, tool dirs, and top-level modules that would
   shadow pytest or a pinned dependency. Modified/added test files are recorded.
2. Copy the fixture's check/ (never in the workdir during the agent run) to a fresh dir.
3. Run it with PYTHONPATH=<sanitized source>:
     uv:    uv run --isolated --no-project --python <repro.python> --with <deps> --with pytest pytest ...
     local: <python> -I bench/localcheck.py <src> <check>   (offline smoke tests; pins NOT enforced)
4. Classify with bench v1's rules (pass / known-failure / other-failure / infra-error).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from bench.common import deps_of
from bench.score import _PYTEST_TALLY, INFRA, LOCALCHECK, _run, classify, uv_command
from bench.v2.taskgen import TaskSpec, dep_name, import_name, sha256

SKIP_DIRS = {".venv", "venv", ".git", "__pycache__", ".pytest_cache", ".claude"}
DROP_DIRS = {"tests", "test", "pytest", "_pytest"}
DROP_FILES = {"conftest.py", "pytest.ini", "tox.ini", "setup.cfg", "sitecustomize.py",
              "usercustomize.py", "pytest.py", "py.py"}


def _dropped(rel: Path, shadow: set[str]) -> bool:
    return (any(part in DROP_DIRS for part in rel.parts[:-1]) or rel.name in DROP_FILES
            or rel.suffix == ".pth" or rel.name.startswith("test_") or rel.name.endswith("_test.py")
            or Path(rel.parts[0]).stem in shadow)


def sanitize(workdir: Path, dest: Path, spec: TaskSpec) -> dict[str, list[str]]:
    """Copy scorable source from `workdir` to `dest`. Returns the dropped files and the
    test/config files the agent added, changed or deleted ("tampered")."""
    shadow = {import_name(dep_name(d)) for d in spec.deps}
    manifest = spec.manifest()
    dropped, tampered = [], []
    for p in sorted(Path(workdir).rglob("*")):
        rel = p.relative_to(workdir)
        if p.is_dir() or SKIP_DIRS.intersection(rel.parts):
            continue
        if _dropped(rel, shadow):
            dropped.append(str(rel))
            if manifest.get(str(rel)) != sha256(p.read_bytes()):
                tampered.append(str(rel))
            continue
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, dest / rel)
    tampered += [r for r in manifest if _dropped(Path(r), shadow) and not (Path(workdir) / r).exists()]
    return {"dropped": dropped, "tampered": sorted(tampered)}


def run_hidden_check(fx: Any, src: Path, scorer: str, python: str, timeout: float) -> tuple[int, str, bool]:
    with tempfile.TemporaryDirectory(prefix="mend-v2-check-") as tmp:
        check = Path(tmp) / "check"
        shutil.copytree(Path(fx.path) / "check", check, ignore=shutil.ignore_patterns("__pycache__"))
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTEST_ADDOPTS")}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        if scorer == "uv":
            env["PYTHONPATH"] = str(src)
            cmd = uv_command(fx, check)
        else:
            cmd = [python, "-I", str(LOCALCHECK), str(src), str(check)]
        code, out, timed_out = _run(cmd, env, Path(tmp), timeout)
        ran = not timed_out and code in (0, 1, 2, 5) and bool(_PYTEST_TALLY.search(out))
        return code, out, ran


def local_missing_deps(fx: Any, python: str) -> list[str]:
    """Pinned deps the local interpreter cannot import at all (-> infra-error)."""
    names = [dep_name(d) for d in deps_of(fx)]
    code = ("import importlib.metadata as m, sys\n"
            "for n in sys.argv[1:]:\n"
            "    try: m.version(n)\n"
            "    except m.PackageNotFoundError: print(n)\n")
    r = subprocess.run([python, "-I", "-c", code, *names], capture_output=True, text=True)
    return r.stdout.split()


_BAD_SIGS: dict[tuple[str, str], set] = {}


def bad_signatures(fx: Any, scorer: str, python: str, timeout: float) -> set:
    from bench.score import failure_signatures

    key = (str(fx.path), scorer)
    if key not in _BAD_SIGS:
        code, out, ran = run_hidden_check(fx, Path(fx.path) / "bad", scorer, python, timeout)
        _BAD_SIGS[key] = failure_signatures(out) if ran and code != 0 else set()
    return _BAD_SIGS[key]


def score_trial(fx: Any, spec: TaskSpec, workdir: Path, scorer: str = "uv",
                python: str = "python3", timeout: float = 300) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="mend-v2-src-") as tmp:
        src = Path(tmp) / "src"
        src.mkdir()
        info = sanitize(workdir, src, spec)
        rec: dict[str, Any] = {"discarded": info["dropped"], "tampered_tests": info["tampered"]}
        if not (src / "target.py").is_file():
            return {**rec, "outcome": INFRA, "detail": "no target.py"}
        if scorer == "local":
            missing = local_missing_deps(fx, python)
            if missing:
                return {**rec, "outcome": INFRA, "detail": f"local scorer: missing {missing}"}
        code, out, ran = run_hidden_check(fx, src, scorer, python, timeout)
        outcome, match, _ = classify(fx, code, out, ran, bad_signatures(fx, scorer, python, timeout))
        tail = "\n".join(out.strip().splitlines()[-40:])
        return {**rec, "outcome": outcome, "match": match, "exit_code": code, "output_tail": tail}
