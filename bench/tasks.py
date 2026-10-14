"""Generate one natural-language coding task per fixture.

A task is what a developer would plausibly ask an agent to do. It must lead toward the
API involved *without* hinting at the pitfall or the fix. Each task has two parts:

1. **Description**: hand-written override in `bench/tasks/<fixture-id>.md` if present,
   else LLM-written (`--llm`, cached to that file with `--write`), else a generic template.
2. **Contract footer** (always appended by the harness): the module/function interface
   the fixture's check imports, and the pinned dependencies. Derived from
   `check/test_check.py` (which names are used on `target`) and `fixed/target.py`
   (their signatures). Only names/signatures are taken from fixed/, never bodies.

Usage:
    python -m bench.tasks [--fixtures GLOB] [--root fixtures] [--llm [--write]] [--model M]
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bench.common import check_dir, deps_of, load_fixtures, select_fixtures

TASKS_DIR = Path(__file__).resolve().parent / "tasks"
DEFAULT_MODEL = os.environ.get("MEND_BENCH_TASK_MODEL", "claude-sonnet-4-5")


@dataclass
class Task:
    fixture_id: str
    package: str
    description: str
    interface: list[str]
    deps: list[str]
    source: str  # "override" | "llm" | "template"

    @property
    def text(self) -> str:
        return self.description.strip() + "\n\n" + contract_footer(self.interface, self.deps)


# --------------------------------------------------------------------------- interface

def used_target_names(check_source: str) -> list[str]:
    """Names the check accesses on `target` (`target.x`, `from target import x`)."""
    tree = ast.parse(check_source)
    names: list[str] = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id == "target"):
            names.append(node.attr)
        elif isinstance(node, ast.ImportFrom) and node.module == "target":
            names += [a.name for a in node.names]
    return list(dict.fromkeys(names))


def _signature(node: ast.AST) -> str:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
        return f"{prefix} {node.name}({ast.unparse(node.args)}){ret}"
    if isinstance(node, ast.ClassDef):
        return f"class {node.name}"
    return ""


def derive_interface(fx: Any) -> list[str]:
    """Signatures (from fixed/target.py) of every name the check uses."""
    cdir = check_dir(fx)
    names: list[str] = []
    for f in sorted(cdir.glob("test_*.py")):
        names += used_target_names(f.read_text(encoding="utf-8"))
    names = list(dict.fromkeys(names))
    fixed = Path(fx.path) / "fixed" / "target.py"
    sigs: dict[str, str] = {}
    if fixed.is_file():
        for node in ast.parse(fixed.read_text(encoding="utf-8")).body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                sigs[node.name] = _signature(node)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    if isinstance(t, ast.Name):
                        sigs[t.id] = f"{t.id} (module-level value)"
    return [sigs.get(n, f"{n}") for n in names]


def contract_footer(interface: list[str], deps: list[str]) -> str:
    lines = ["Requirements:",
             "- Put your solution in a single file `target.py` in the current directory.",
             "- It must expose:"]
    lines += [f"    {s}" for s in interface] or ["    (see description)"]
    if any("==" in d for d in deps):
        lines.append("- Pinned dependencies (already in requirements.txt): " + ", ".join(deps))
    else:
        lines.append("- Dependencies (already installed): " + ", ".join(deps))
    lines.append("- Standard library plus those dependencies only. No network access at runtime.")
    return "\n".join(lines)


# --------------------------------------------------------------------------- descriptions

def template_description(fx: Any, interface: list[str]) -> str:
    """Generic fallback. Deliberately uses only package + interface names: never the
    title/summary/failure fields, which describe the pitfall."""
    import re

    names = ", ".join(m.group(1) for s in interface
                      if (m := re.match(r"^(?:async def |def |class )?([A-Za-z_]\w*)", s))) \
        or "the required functions"
    return (f"I'm working on a small Python project that uses {fx.package}. "
            f"Please write a module `target.py` that implements {names} using {fx.package}.")


def override_path(fixture_id: str) -> Path:
    return TASKS_DIR / f"{fixture_id}.md"


def read_override(fixture_id: str) -> str | None:
    p = override_path(fixture_id)
    if not p.is_file():
        return None
    text = p.read_text(encoding="utf-8")
    # Allow an HTML comment header (provenance notes) that is not sent to agents.
    while text.lstrip().startswith("<!--"):
        text = text.split("-->", 1)[1] if "-->" in text else ""
    return text.strip() or None


LLM_WRITER_SYSTEM = """You write realistic coding requests that a developer would give an AI coding assistant.
You will receive: a Python package name, pinned dependencies, the public interface a module must expose,
and an automated acceptance test. Write a 2-5 sentence request in the developer's voice asking for that
module. Rules:
- Describe the goal and behavior naturally (what the code is for, what inputs/outputs look like).
- Mention the main library by name so the assistant uses it.
- Do NOT mention versions, migrations, deprecations, upgrades, breaking changes, common mistakes,
  specific import paths, or which API/decorator/keyword to use. Do not give implementation hints.
- Do not restate the interface or dependency list verbatim; they are appended separately.
Output only the request text."""


def llm_description(fx: Any, interface: list[str], model: str = DEFAULT_MODEL) -> str:
    """Ask an LLM to write the task. The writer sees only package, deps, interface and the
    check, never bad/fixed code or the fixture's title/summary/failure (the fix)."""
    import requests  # optional; only needed here

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    checks = "\n\n".join(f.read_text(encoding="utf-8") for f in sorted(check_dir(fx).glob("test_*.py")))
    user = (f"Package: {fx.package}\nPinned dependencies: {', '.join(deps_of(fx))}\n"
            f"Interface:\n" + "\n".join(f"  {s}" for s in interface) +
            f"\n\nAcceptance test (module is imported as `target`):\n```python\n{checks}\n```")
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": model, "max_tokens": 600, "system": LLM_WRITER_SYSTEM,
              "messages": [{"role": "user", "content": user}]},
        timeout=120,
    )
    r.raise_for_status()
    text = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
    return leak_guard(fx, text.strip())


def leak_guard(fx: Any, text: str) -> str:
    """Reject generated text that quotes the fix/bad pattern (best-effort)."""
    from bench.common import get

    for field in ("fix_pattern", "bad_pattern"):
        pat = str(get(fx, "failure", field, default="") or "").strip()
        if pat and len(pat) > 6 and pat.lower() in text.lower():
            raise ValueError(f"generated task for {fx.id} quotes failure.{field}; refusing")
    return text


def build_task(fx: Any, use_llm: bool = False, model: str = DEFAULT_MODEL) -> Task:
    interface = derive_interface(fx)
    desc, source = read_override(fx.id), "override"
    if desc is None and use_llm:
        desc, source = llm_description(fx, interface, model), "llm"
    if desc is None:
        desc, source = template_description(fx, interface), "template"
    return Task(fx.id, str(fx.package), desc, interface, deps_of(fx), source)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m bench.tasks", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default="fixtures")
    ap.add_argument("--fixtures", default=None, help="comma-separated id/path globs")
    ap.add_argument("--llm", action="store_true", help="write missing descriptions with the Anthropic API")
    ap.add_argument("--write", action="store_true", help="with --llm: save to bench/tasks/<id>.md")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    fixtures = select_fixtures(load_fixtures(args.root), args.fixtures)
    out = []
    for fx in fixtures:
        t = build_task(fx, args.llm, args.model)
        if args.write and t.source == "llm":
            override_path(fx.id).write_text(
                f"<!-- generated by bench.tasks --llm ({args.model}); review before committing -->\n"
                f"{t.description}\n", encoding="utf-8")
        out.append(t)
    if args.json:
        print(json.dumps([{**t.__dict__, "text": t.text} for t in out], indent=2))
    else:
        for t in out:
            print(f"### {t.fixture_id}  [{t.source}]\n{t.text}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
