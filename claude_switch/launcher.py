"""Launch Claude Code under a given profile."""

import logging
import os
import subprocess
import sys
from pathlib import Path

from .config import Profile

log = logging.getLogger(__name__)


def launch(
    profile_key: str,
    profile: Profile,
    binary: str,
    forward_args: list[str],
    show_info: bool,
) -> None:
    config_dir = Path(profile.config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)

    if show_info:
        log.info("")
        log.info("  Account  : %s", profile.name)
        if profile.description:
            log.info("  Info     : %s", profile.description)
        log.info("  Profile  : %s", config_dir)
        log.info("  Binary   : %s", binary)
        log.info("")

    env = os.environ.copy()
    env["CLAUDE_CONFIG_DIR"] = str(config_dir)

    try:
        result = subprocess.run([binary, *forward_args], env=env)
        sys.exit(result.returncode)
    except FileNotFoundError:
        log.error("Binary not found or not executable: %s", binary)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(0)
