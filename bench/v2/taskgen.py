"""Turn a fixture into an agentic, implicit-version task.

A task is a small project directory (2-3 source files, a visible unit test, a project
CLAUDE.md, and the dependency pins), plus a prompt that asks for a feature, plus a
hidden test (the fixture's `check/`) that is never in the workdir during the agent run.

The pinned versions live only in the repository (exact pins in pyproject.toml, so
`uv run` in the workdir gets exactly them), never in the prompt. `find_leaks()` enforces that, and the runner refuses to start a
trial whose prompt leaks.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bench.common import check_dir, deps_of, get, normalize, python_of
from bench.tasks import derive_interface, read_override, template_description

# Package -> (project name, one-line project description). Plain, domain-flavoured, and
# deliberately silent about versions or APIs.
FLAVOR: dict[str, tuple[str, str]] = {
    "numpy": ("analytics-toolkit", "Numerical helpers used by our analytics dashboards."),
    "pandas": ("feed-cleaner", "Data-cleaning steps for the product feed pipeline."),
    "pydantic": ("accounts-config", "Typed models and configuration for the accounts service."),
    "fastapi": ("orders-api", "HTTP API for the orders service."),
    "starlette": ("edge-app", "A lightweight ASGI app that sits in front of the edge cache."),
    "sqlalchemy": ("reporting-db", "Database access layer for the nightly reporting jobs."),
}
DEFAULT_FLAVOR = ("internal-tools", "Small internal Python service.")

BASE_CLAUDE_MD = """# Project notes

{desc}

- Source modules live at the repository root; unit tests live in `tests/`.
- `main.py` is the command-line entry point.
"""

HELPERS_PY = '''"""Small stdlib-only helpers shared across the project."""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from typing import TypeVar

T = TypeVar("T")


def chunked(items: Iterable[T], size: int) -> Iterator[list[T]]:
    """Yield lists of at most `size` items."""
    if size <= 0:
        raise ValueError("size must be positive")
    batch: list[T] = []
    for item in items:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def slugify(text: str) -> str:
    """Lower-case, dash-separated identifier for logs and file names."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
'''

MAIN_PY = '''"""Command-line entry point for {name}."""

from __future__ import annotations

import sys

from helpers import slugify


def main(argv: list[str]) -> int:
    print(f"{name}: {{slugify(' '.join(argv) or 'ready')}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
'''

TEST_HELPERS_PY = '''from helpers import chunked, slugify


def test_chunked():
    assert list(chunked(range(5), 2)) == [[0, 1], [2, 3], [4]]


def test_slugify():
    assert slugify("Hello, World!") == "hello-world"
'''

CONFTEST_PY = '''import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
'''

GITIGNORE = ".venv/\n__pycache__/\n*.pyc\n.pytest_cache/\n"

@dataclass
class TaskSpec:
    fixture_id: str
    package: str
    name: str
    prompt: str
    description_source: str  # "override" | "template"
    interface: list[str]
    deps: list[str]
    python: str
    files: dict[str, str] = field(default_factory=dict)  # relpath -> content
    hidden_check: Path | None = None

    def manifest(self) -> dict[str, str]:
        """relpath -> sha256 of every template file (used to detect tampering)."""
        return {p: sha256(c) for p, c in self.files.items()}


def sha256(text: str | bytes) -> str:
    data = text.encode("utf-8") if isinstance(text, str) else text
    return hashlib.sha256(data).hexdigest()


def dep_name(dep: str) -> str:
    m = re.match(r"^\s*([A-Za-z0-9_.\-]+)", dep)
    return m.group(1) if m else dep


def dep_version(dep: str) -> str | None:
    m = re.search(r"==\s*([^\s;,]+)", dep)
    return m.group(1) if m else None


def import_name(dist: str) -> str:
    return normalize(dist).replace("-", "_")


# --------------------------------------------------------------------------- files

def pyproject_toml(name: str, deps: list[str], python: str) -> str:
    dep_lines = "".join(f'    "{d}",\n' for d in deps)
    return (f'[project]\nname = "{name}"\nversion = "0.1.0"\n'
            f'requires-python = ">={python}"\n'
            f"dependencies = [\n{dep_lines}]\n\n"
            "[dependency-groups]\ndev = [\"pytest\"]\n\n"
            "[tool.uv]\npackage = false\n")


def project_files(fx: Any) -> dict[str, str]:
    pkg = normalize(str(fx.package))
    name, desc = FLAVOR.get(pkg, DEFAULT_FLAVOR)
    deps, py = deps_of(fx), python_of(fx)
    files = {
        "README.md": f"# {name}\n\n{desc}\n\nRun the unit tests with `pytest`.\n",
        "CLAUDE.md": BASE_CLAUDE_MD.format(desc=desc),
        "pyproject.toml": pyproject_toml(name, deps, py),
        "helpers.py": HELPERS_PY,
        "main.py": MAIN_PY.format(name=name),
        "tests/__init__.py": "",
        "tests/conftest.py": CONFTEST_PY,
        "tests/test_helpers.py": TEST_HELPERS_PY,
        ".gitignore": GITIGNORE,
    }
    return files


# --------------------------------------------------------------------------- prompt

def build_prompt(name: str, description: str, interface: list[str]) -> str:
    lines = [f"You are working in the `{name}` repository (the current directory).", "",
             description.strip(), "", "Requirements:",
             "- Implement this in a new module `target.py` at the repository root.",
             "- `target.py` must expose:"]
    lines += [f"    {s}" for s in interface] or ["    (see the description above)"]
    lines.append("- Use only the standard library and the project's existing dependencies.")
    return "\n".join(lines) + "\n"


_HINT_WORDS = re.compile(r"deprecat|removed in|migrat|breaking change|upgrad|changelog|release notes",
                         re.IGNORECASE)


def find_leaks(prompt: str, fx: Any) -> list[str]:
    """Reasons this prompt gives away the pinned versions or the fix. Empty = clean."""
    leaks: list[str] = []
    for d in deps_of(fx):
        v = dep_version(d)
        if v and re.search(rf"(?<![\w.]){re.escape(v)}(?![\w])", prompt):
            leaks.append(f"pinned version {v} ({dep_name(d)}) appears in prompt")
        for nm in {dep_name(d), normalize(dep_name(d)), import_name(dep_name(d))}:
            m = re.search(rf"\b{re.escape(nm)}\s*(?:v(?:ersion)?\s*)?\d+(?:\.\d+)*\b", prompt, re.IGNORECASE)
            if m:
                leaks.append(f"version-like mention {m.group(0)!r}")
    if "==" in prompt:
        leaks.append("'==' pin syntax in prompt")
    m = _HINT_WORDS.search(prompt)
    if m:
        leaks.append(f"hint word {m.group(0)!r}")
    for fld in ("fix_pattern", "bad_pattern"):
        pat = str(get(fx, "failure", fld, default="") or "").strip()
        if pat and len(pat) > 6 and pat.lower() in prompt.lower():
            leaks.append(f"prompt quotes failure.{fld}")
    return sorted(set(leaks))


# --------------------------------------------------------------------------- build

def build_task(fx: Any) -> TaskSpec:
    interface = derive_interface(fx)
    desc, source = read_override(str(fx.id)), "override"
    if desc is None:
        desc, source = template_description(fx, interface), "template"
    files = project_files(fx)
    name = FLAVOR.get(normalize(str(fx.package)), DEFAULT_FLAVOR)[0]
    return TaskSpec(fixture_id=str(fx.id), package=str(fx.package), name=name,
                    prompt=build_prompt(name, desc, interface), description_source=source,
                    interface=interface, deps=deps_of(fx), python=python_of(fx),
                    files=files, hidden_check=check_dir(fx))


def materialize(spec: TaskSpec, dest: Path) -> Path:
    """Write the project files into `dest` (created). The hidden check is NOT copied."""
    dest.mkdir(parents=True, exist_ok=True)
    for rel, content in spec.files.items():
        p = dest / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return dest


def hidden_test_present(spec: TaskSpec, workdir: Path) -> list[str]:
    """Files in `workdir` whose content equals a hidden-check file (should be empty)."""
    if spec.hidden_check is None:
        return []
    hidden = {sha256(p.read_bytes()) for p in Path(spec.hidden_check).rglob("*.py")
              if p.stat().st_size > 0}
    hits = []
    for p in Path(workdir).rglob("*"):
        if p.is_file() and ".venv" not in p.parts and 0 < p.stat().st_size < 1_000_000:
            if sha256(p.read_bytes()) in hidden:
                hits.append(str(p.relative_to(workdir)))
    return hits
