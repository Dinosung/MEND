"""Replay agent: copies a known file to target.py. Used to test the harness itself.

`--replay-source bad` must score known-failure on every verified fixture, and
`--replay-source fixed` must score pass. Anything else means the harness (or the
fixture) is broken.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from bench.agents import AgentError


class ReplayAgent:
    name = "replay"
    uses_fixture = True  # run.py passes the fixture via `bind()` before solve()

    def __init__(self, source: str = "fixed"):
        self.source = source
        self._fixture = None

    def bind(self, fixture) -> None:
        self._fixture = fixture

    def _src(self) -> Path:
        fx = self._fixture
        if self.source in ("bad", "fixed"):
            if fx is None:
                raise AgentError("replay agent needs a bound fixture for bad/fixed")
            return Path(fx.path) / self.source / "target.py"
        p = Path(self.source)
        if p.is_dir():
            if fx is None:
                raise AgentError("replay agent needs a bound fixture for a directory source")
            return p / f"{fx.id}.py"
        return p

    def solve(self, task: str, workdir: Path, mend_context: str | None) -> None:
        src = self._src()
        if not src.is_file():
            raise AgentError(f"replay source not found: {src}")
        shutil.copyfile(src, Path(workdir) / "target.py")
        (Path(workdir) / "transcript.txt").write_text(f"replayed {src}\n", encoding="utf-8")
