"""Install/uninstall a 'claude' shim that delegates to claude-switch."""

from __future__ import annotations

import logging
import platform
import shutil
import stat
import sys
from pathlib import Path

log = logging.getLogger(__name__)

# Marker file written alongside the shim so uninstall knows where to look.
_MARKER_NAME = ".claude-switch-shim"


def _real_claude() -> Path | None:
    """Path to the real claude binary, skipping any shim we already installed."""
    found = shutil.which("claude")
    if not found:
        return None
    p = Path(found)
    # If what's on PATH is already our shim marker directory, skip it and
    # keep searching the rest of PATH.
    if (p.parent / _MARKER_NAME).exists():
        import os

        sep = ";" if platform.system() == "Windows" else ":"
        for entry in os.environ.get("PATH", "").split(sep):
            if not entry:
                continue
            candidate_dir = Path(entry)
            if candidate_dir.resolve() == p.parent.resolve():
                continue
            for name in (
                ["claude.cmd", "claude.exe", "claude"]
                if platform.system() == "Windows"
                else ["claude"]
            ):
                candidate = candidate_dir / name
                if candidate.exists():
                    return candidate
        return None
    return p


def _shim_dir() -> Path:
    """Directory to install the shim into — same dir as the real claude binary."""
    real = _real_claude()
    if real:
        return real.parent
    # Fall back to the claude-switch script dir
    found = shutil.which("claude-switch")
    if found:
        return Path(found).parent
    log.error("Could not locate claude or claude-switch on PATH.")
    sys.exit(1)


def _shim_paths(shim_dir: Path) -> list[Path]:
    if platform.system() == "Windows":
        return [shim_dir / "claude.cmd", shim_dir / "claude.ps1"]
    else:
        return [shim_dir / "claude"]


def _marker(shim_dir: Path) -> Path:
    return shim_dir / _MARKER_NAME


def install_shim() -> None:
    shim_dir = _shim_dir()
    marker = _marker(shim_dir)

    if marker.exists():
        print("\n  Shim is already installed.\n")
        print(f"  Location: {shim_dir}\n")
        return

    if platform.system() == "Windows":
        cmd_shim = shim_dir / "claude.cmd"
        ps1_shim = shim_dir / "claude.ps1"
        cmd_shim.write_text("@echo off\nclaude-switch %*\n")
        ps1_shim.write_text("& claude-switch @args\n")
        marker.write_text("")
        print(f"\n  Installed:\n    {cmd_shim}\n    {ps1_shim}")
    else:
        shim = shim_dir / "claude"
        shim.write_text('#!/bin/sh\nexec claude-switch "$@"\n')
        shim.chmod(shim.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        marker.write_text("")
        print(f"\n  Installed:\n    {shim}")

    print("\n  'claude' will now open the account selector.")
    print("  Run 'claude-switch --uninstall' to remove it.\n")


def uninstall_shim() -> None:
    # Find the marker to locate where we installed
    import os

    sep = ";" if platform.system() == "Windows" else ":"
    shim_dir = None
    for entry in os.environ.get("PATH", "").split(sep):
        if not entry:
            continue
        candidate = Path(entry) / _MARKER_NAME
        if candidate.exists():
            shim_dir = Path(entry)
            break

    if shim_dir is None:
        print("\n  No shim found to remove.\n")
        return

    removed = []
    for p in _shim_paths(shim_dir):
        if p.exists():
            p.unlink()
            removed.append(p)
    _marker(shim_dir).unlink(missing_ok=True)

    if removed:
        print("\n  Removed:\n" + "".join(f"    {p}\n" for p in removed))
    else:
        print("\n  No shim files found to remove.\n")


def shim_installed() -> bool:
    import os

    sep = ";" if platform.system() == "Windows" else ":"
    return any(
        (Path(entry) / _MARKER_NAME).exists()
        for entry in os.environ.get("PATH", "").split(sep)
        if entry
    )
