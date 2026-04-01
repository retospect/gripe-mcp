"""gripe-mcp — agent complaint box.

One tool: report_issue(). Postgres if GRIPE_DB_URL is set, else .gripe-mcp/ JSONL.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from mcp.server.fastmcp import FastMCP

from gripe.storage import get_backend

mcp = FastMCP("gripe")

# Server-side identity — never ask the agent for these.
_AGENT_ID = os.environ.get("GRIPE_AGENT_ID", "unknown")
_TASK_ID = os.environ.get("GRIPE_TASK_ID", "")

_MODES = {
    "ambiguous_instruction",
    "missing_tool",
    "bad_tool_doc",
    "hallucination_risk",
    "wrong_scope",
    "memory_miss",
    "other",
}

_SEVS = {"low", "medium", "high"}

_backend = None


def _get_backend():
    global _backend
    if _backend is None:
        _backend = get_backend()
    return _backend


@mcp.tool()
def report_issue(
    description: str,
    severity: str = "low",
    section: str = "",
    mode: str = "other",
) -> str:
    """Report a bug, confusion, bad documentation, or improvement idea.

    Call this when you:
    - had to guess or weren't confident in your output
    - hit a missing tool or capability
    - found unclear, wrong, or incomplete tool documentation
    - encountered ambiguous instructions
    - want to suggest a new tool, workflow step, or prompt fix

    Non-blocking — log and continue your task. No response expected.
    There is no penalty for logging; silence is the failure mode.

    description: what went wrong or what you'd like improved (max 200 chars)
    severity: low (friction) | medium (had to guess/workaround) | high (abandoned/wrong output)
    section: which instruction or tool caused the issue (max 80 chars)
    mode: ambiguous_instruction | missing_tool | bad_tool_doc | hallucination_risk | wrong_scope | memory_miss | other
    """
    description = description[:200]
    section = section[:80]
    if severity not in _SEVS:
        severity = "low"
    if mode not in _MODES:
        mode = "other"

    entry = {
        "ts": datetime.now(UTC).isoformat(),
        "agent_id": _AGENT_ID,
        "task_id": _TASK_ID,
        "severity": severity,
        "section": section,
        "mode": mode,
        "description": description,
    }

    try:
        _get_backend().write(entry)
    except Exception as exc:
        return f"gripe: failed to log — {exc}"

    return "logged"


def main():
    """Run the MCP server."""
    mcp.run()
