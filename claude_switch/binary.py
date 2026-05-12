"""Locate the Claude Code binary."""

from __future__ import annotations

import shutil
from pathlib import Path

from .config import Settings, die


def find_claude_binary(settings: Settings) -> str:
    if settings.claude_binary:
        p = Path(settings.claude_binary).expanduser()
        if not p.exists():
            die(f"claude_binary set in config but not found: {p}")
        return str(p)

    found = shutil.which("claude")
    if found:
        return found

    die(
        "Could not find 'claude' on PATH.\n\n"
        "  Set 'claude_binary' in your claude-switch.json to point to it directly."
    )
