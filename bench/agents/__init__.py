"""Agent adapters for MEND-Bench.

Contract: `Agent.solve(task, workdir, mend_context) -> None` must leave `workdir/target.py`.
`mend_context` is None for the baseline arm. For the with-MEND arm it is the rendered
MEND data block (what `mend lookup` returns for this project); adapters that can talk to
MCP (claude_code) may instead expose `mend serve` and ignore the pre-rendered block.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Protocol


class Agent(Protocol):
    name: str

    def solve(self, task: str, workdir: Path, mend_context: str | None) -> None: ...


class AgentError(RuntimeError):
    """The agent could not produce a solution for infrastructure reasons."""


def add_agent_args(ap: argparse.ArgumentParser) -> None:
    g = ap.add_argument_group("agent options")
    g.add_argument("--model", default=None, help="model id for claude_code / anthropic_api")
    g.add_argument("--replay-source", default="fixed",
                   help="replay agent: 'bad', 'fixed', or a path to a file/dir (dir: <dir>/<fixture-id>.py)")
    g.add_argument("--mend-mode", choices=["mcp", "context"], default="mcp",
                   help="claude_code with-MEND arm: expose `mend serve` over MCP (default) or inject context")
    g.add_argument("--agent-timeout", type=float, default=600)
    g.add_argument("--max-turns", type=int, default=30)


def make_agent(name: str, args: Any) -> Agent:
    if name == "replay":
        from bench.agents.replay import ReplayAgent
        return ReplayAgent(args.replay_source)
    if name == "anthropic_api":
        from bench.agents.anthropic_api import AnthropicAPIAgent
        return AnthropicAPIAgent(model=args.model, timeout=args.agent_timeout)
    if name == "claude_code":
        from bench.agents.claude_code import ClaudeCodeAgent
        return ClaudeCodeAgent(model=args.model, mend_mode=args.mend_mode,
                               timeout=args.agent_timeout, max_turns=args.max_turns,
                               fixtures_root=getattr(args, "root", "fixtures"))
    raise SystemExit(f"unknown agent {name!r}; expected replay, anthropic_api, claude_code")
