"""Keep each profile's 5-hour usage window started."""

from __future__ import annotations

import logging
import platform
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .config import Profile
from .launcher import profile_env
from .state import State
from .usage import fetch_rate_limits, load_rate_cache

log = logging.getLogger(__name__)

_WINDOW_SECONDS = 5 * 3600
_TASK_NAME = "claude-switch-warm"
_CRON_MARKER = f"# {_TASK_NAME}"
_DEFAULT_INTERVAL_MINUTES = 30

ACTIVE = "active"
STARTED = "started"
FAILED = "failed"


@dataclass
class WarmResult:
    status: str
    reset_at: float | None = None  # unix time the window ends


def _known_window_end(key: str, profile: Profile, state: State) -> float:
    """Latest window end we know of, from our own record or the selector's cache."""
    end = state.warmed_until.get(key, 0.0)
    cached = load_rate_cache(profile.config_dir, max_age=None)
    if cached:
        end = max(end, cached.session_reset_at.timestamp())
    return end


def _warm_via_claude(key: str, profile: Profile, binary: str) -> bool:
    """Fallback for a missing or expired token; costlier, but claude refreshes the token."""
    try:
        result = subprocess.run(
            [binary, "-p", "hi", "--model", "haiku", "--no-session-persistence"],
            env=profile_env(key, profile),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        log.debug("claude warm-up failed: %s", e)
        return False
    return result.returncode == 0


def warm_profile(key: str, profile: Profile, binary: str | None, state: State) -> WarmResult:
    """Start the profile's window if none is running; records the end in `state`."""
    now = time.time()
    end = _known_window_end(key, profile, state)
    if end > now:
        return WarmResult(ACTIVE, end)

    info = fetch_rate_limits(profile.config_dir, force=True)
    if info is None:
        if not binary or not _warm_via_claude(key, profile, binary):
            return WarmResult(FAILED)
        info = fetch_rate_limits(profile.config_dir, force=True)

    end = info.session_reset_at.timestamp() if info else now + _WINDOW_SECONDS
    state.warmed_until[key] = end
    return WarmResult(STARTED, end)


# ---------------------------------------------------------------------------
# Scheduling: run `claude-switch --warm` periodically
# ---------------------------------------------------------------------------

def _scheduled_command() -> list[str]:
    exe = Path(sys.executable)
    if platform.system() == "Windows":
        # pythonw avoids flashing a console window on every run.
        exe = exe.with_name("pythonw.exe") if exe.with_name("pythonw.exe").exists() else exe
    return [str(exe), "-m", "claude_switch", "--warm"]


def install_schedule(interval_minutes: int = _DEFAULT_INTERVAL_MINUTES) -> None:
    cmd = _scheduled_command()

    if platform.system() == "Windows":
        result = subprocess.run(
            [
                "schtasks", "/Create", "/F",
                "/TN", _TASK_NAME,
                "/SC", "MINUTE", "/MO", str(interval_minutes),
                "/TR", subprocess.list2cmdline(cmd),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"\n  Could not create the scheduled task:\n  {result.stderr.strip()}\n")
            sys.exit(1)
        print(f"\n  Scheduled task '{_TASK_NAME}' created (every {interval_minutes} min).")
    else:
        line = f'*/{interval_minutes} * * * * {" ".join(shlex.quote(c) for c in cmd)} {_CRON_MARKER}'
        _write_crontab([*(ln for ln in _read_crontab() if _CRON_MARKER not in ln), line])
        print(f"\n  Cron entry added (every {interval_minutes} min).")

    print("  Run 'claude-switch --uninstall-warm' to remove it.\n")


def uninstall_schedule() -> None:
    if platform.system() == "Windows":
        result = subprocess.run(
            ["schtasks", "/Delete", "/F", "/TN", _TASK_NAME], capture_output=True, text=True
        )
        removed = result.returncode == 0
    else:
        lines = _read_crontab()
        kept = [ln for ln in lines if _CRON_MARKER not in ln]
        removed = len(kept) != len(lines)
        if removed:
            _write_crontab(kept)

    print("\n  Warm-up schedule removed.\n" if removed else "\n  No warm-up schedule found.\n")


def _read_crontab() -> list[str]:
    if not shutil.which("crontab"):
        print("\n  'crontab' not found; schedule 'claude-switch --warm' with your own scheduler.\n")
        sys.exit(1)
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    return result.stdout.splitlines() if result.returncode == 0 else []


def _write_crontab(lines: list[str]) -> None:
    subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True, check=True)
