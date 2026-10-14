"""Run a fixture's check/ against a solution directory with the *current* interpreter.

Used by `--scorer local` (offline smoke runs, no uv). Invoked as a subprocess:

    python bench/localcheck.py <solution_dir> <check_dir>

If pytest is importable it is used directly (`pytest -q -rfE <check_dir>`). Otherwise a
minimal pytest-compatible runner executes `test_*` functions, supporting the fixtures
fixtures actually use (`monkeypatch`, `tmp_path`) and a shim `pytest` module
(`raises`, `skip`, `fail`, `mark.*`, `approx`). Output mimics pytest's
`E   Type: msg` / `FAILED file::test - Type: msg` lines so one parser handles both.

Exit codes follow pytest: 0 all passed, 1 test failures, 2 collection error, 5 no tests.
"""

from __future__ import annotations

import importlib.util
import inspect
import os
import sys
import tempfile
import traceback
import types
from pathlib import Path


def _exc_name(e: BaseException) -> str:
    t = type(e)
    mod = t.__module__
    return t.__qualname__ if mod in ("builtins", "__main__") else f"{mod}.{t.__qualname__}"


class _Failed(AssertionError):
    pass


class _Skipped(Exception):
    pass


class _Raises:
    def __init__(self, exc, match=None):
        self.exc, self.match = exc, match
        self.value = None

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        if et is None:
            raise _Failed(f"DID NOT RAISE {self.exc}")
        if not issubclass(et, self.exc):
            return False
        if self.match is not None:
            import re

            if not re.search(self.match, str(ev)):
                raise _Failed(f"Regex {self.match!r} does not match {str(ev)!r}")
        self.value = ev
        return True


def _make_pytest_shim() -> types.ModuleType:
    m = types.ModuleType("pytest")

    def raises(exc, *args, match=None, **kw):
        if args:
            with _Raises(exc, match):
                args[0](*args[1:], **kw)
            return None
        return _Raises(exc, match)

    def skip(reason=""):
        raise _Skipped(reason)

    def fail(reason=""):
        raise _Failed(reason)

    class _Mark:
        def __getattr__(self, name):
            def deco(*a, **k):
                if len(a) == 1 and callable(a[0]) and not k:
                    return a[0]
                return lambda f: f
            return deco

    def approx(expected, rel=1e-6, abs_tol=1e-12, **kw):
        tol_abs = kw.get("abs", abs_tol)

        class _A:
            def __eq__(self, other):
                return abs(other - expected) <= max(rel * abs(expected), tol_abs)

            def __repr__(self):
                return f"approx({expected!r})"
        return _A()

    m.raises, m.skip, m.fail, m.mark, m.approx = raises, skip, fail, _Mark(), approx
    m.__dict__["__mend_shim__"] = True
    return m


class _MonkeyPatch:
    _MISSING = object()

    def __init__(self):
        self._env: list[tuple[str, object]] = []
        self._attrs: list[tuple[object, str, object]] = []
        self._cwd: str | None = None
        self._syspath: list[str] | None = None

    def setenv(self, name, value, prepend=None):
        self._env.append((name, os.environ.get(name, self._MISSING)))
        value = str(value)
        if prepend and name in os.environ:
            value = value + prepend + os.environ[name]
        os.environ[name] = value

    def delenv(self, name, raising=True):
        if name not in os.environ:
            if raising:
                raise KeyError(name)
            return
        self._env.append((name, os.environ[name]))
        del os.environ[name]

    def setattr(self, target, name, value=_MISSING, raising=True):
        if value is self._MISSING:  # "module.attr" form
            modpath, attr = target.rsplit(".", 1)
            target, name, value = importlib.import_module(modpath), attr, name
        self._attrs.append((target, name, getattr(target, name, self._MISSING)))
        setattr(target, name, value)

    def delattr(self, target, name, raising=True):
        if not hasattr(target, name):
            if raising:
                raise AttributeError(name)
            return
        self._attrs.append((target, name, getattr(target, name)))
        delattr(target, name)

    def chdir(self, path):
        if self._cwd is None:
            self._cwd = os.getcwd()
        os.chdir(path)

    def syspath_prepend(self, path):
        if self._syspath is None:
            self._syspath = list(sys.path)
        sys.path.insert(0, str(path))

    def undo(self):
        for obj, name, old in reversed(self._attrs):
            if old is self._MISSING:
                try:
                    delattr(obj, name)
                except AttributeError:
                    pass
            else:
                setattr(obj, name, old)
        for name, old in reversed(self._env):
            if old is self._MISSING:
                os.environ.pop(name, None)
            else:
                os.environ[name] = old  # type: ignore[assignment]
        if self._cwd:
            os.chdir(self._cwd)
        if self._syspath is not None:
            sys.path[:] = self._syspath
        self._attrs, self._env, self._cwd, self._syspath = [], [], None, None


def _print_exc(e: BaseException) -> str:
    tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
    for line in tb.rstrip().splitlines():
        print(f"    {line}")
    first = (str(e).splitlines() or [""])[0]
    summary = f"{_exc_name(e)}: {first}" if first else _exc_name(e)
    print(f"E   {summary}")
    return summary


def mini_run(check_dir: Path) -> int:
    sys.modules["pytest"] = _make_pytest_shim()
    files = sorted(check_dir.glob("test_*.py"))
    if not files:
        print("no tests ran")
        return 5
    passed = failed = errors = 0
    summary: list[str] = []
    for f in files:
        rel = f"{check_dir.name}/{f.name}"
        spec = importlib.util.spec_from_file_location(f"_mend_check_{f.stem}", f)
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        try:
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
        except BaseException as e:  # collection error
            print(f"ERROR collecting {rel}")
            s = _print_exc(e)
            summary.append(f"ERROR {rel} - {s}")
            errors += 1
            continue
        for name, fn in sorted(vars(mod).items()):
            if not (name.startswith("test") and inspect.isfunction(fn)):
                continue
            mp = _MonkeyPatch()
            tmp = tempfile.TemporaryDirectory(prefix="mend-tmp-")
            provided = {"monkeypatch": mp, "tmp_path": Path(tmp.name)}
            params = list(inspect.signature(fn).parameters)
            try:
                missing = [p for p in params if p not in provided]
                if missing:
                    raise RuntimeError(f"localcheck: unsupported pytest fixture(s) {missing}; use --scorer uv")
                fn(**{p: provided[p] for p in params})
                passed += 1
            except _Skipped:
                pass
            except BaseException as e:
                print(f"___ {name} ___")
                s = _print_exc(e)
                summary.append(f"FAILED {rel}::{name} - {s}")
                failed += 1
            finally:
                mp.undo()
                tmp.cleanup()
    if summary:
        print("=== short test summary info ===")
        for s in summary:
            print(s)
    print(f"{failed} failed, {passed} passed, {errors} errors (mend localcheck)")
    if errors and not (passed or failed):
        return 2
    return 1 if (failed or errors) else (0 if passed else 5)


def main(argv: list[str]) -> int:
    solution_dir, check_dir = Path(argv[0]).resolve(), Path(argv[1]).resolve()
    sys.path.insert(0, str(solution_dir))
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    try:
        import pytest  # noqa: F401
    except ImportError:
        return mini_run(check_dir)
    return int(pytest.main(["-q", "-rfE", "-p", "no:cacheprovider", str(check_dir)]))


if __name__ == "__main__":
    # The script's own directory (bench/) must not shadow anything.
    sys.path = [p for p in sys.path if Path(p or ".").resolve() != Path(__file__).resolve().parent]
    raise SystemExit(main(sys.argv[1:]))
