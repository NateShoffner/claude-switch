"""
Entry points registered in pyproject.toml.

    claude-switch        → main()         interactive selector
    claude-<key>         → profile()      direct launch, key derived from argv[0]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(format="  %(levelname)s: %(message)s", level=logging.WARNING)

from .binary import find_claude_binary
from .config import Config, die, find_config, find_profile_for_cwd, load_config
from .launcher import launch
from .shim import install_shim, uninstall_shim
from .ui import add_profile, show_first_run, show_list, show_selector


def _base_parser(prog: str, description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=prog, description=description)
    p.add_argument(
        "--config",
        "-c",
        metavar="FILE",
        help="Path to a JSON config file (overrides default locations).",
    )
    return p


def _load(config_override: str | None) -> tuple[Config, str, Path, bool]:
    config_path, is_new = find_config(config_override)
    config = load_config(config_path)
    binary = find_claude_binary(config.settings)
    return config, binary, config_path, is_new


def _launch_by_key(
    key: str, config: Config, binary: str, forward_args: list[str]
) -> None:
    if key not in config.profiles:
        available = ", ".join(config.profiles.keys())
        die(f"Unknown profile '{key}'. Available: {available}")
    launch(
        key,
        config.profiles[key],
        binary,
        forward_args,
        config.settings.show_profile_info,
    )


# ---------------------------------------------------------------------------
# claude-switch
# ---------------------------------------------------------------------------


def main() -> None:
    parser = _base_parser(
        "claude-switch", "Launch Claude Code — prompts for account if no profile given."
    )
    parser.add_argument(
        "--profile",
        "-p",
        metavar="NAME",
        help="Launch a specific profile directly, skipping the selector.",
    )
    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="List all configured profiles and exit.",
    )
    parser.add_argument(
        "--add", action="store_true", help="Add a new profile interactively."
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Install a 'claude' shim so you can type claude instead of claude-switch.",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove the 'claude' shim installed by --install.",
    )

    our_args, forward_args = parser.parse_known_args()

    if our_args.install:
        install_shim()
        sys.exit(0)

    if our_args.uninstall:
        uninstall_shim()
        sys.exit(0)

    config, binary, config_path, is_new = _load(our_args.config)

    if is_new:
        show_first_run(config_path)
        sys.exit(0)

    if our_args.add:
        add_profile(config, config_path)
        sys.exit(0)

    if our_args.list:
        show_list(config.profiles, config_path)
        sys.exit(0)

    if our_args.profile:
        _launch_by_key(our_args.profile, config, binary, forward_args)
        return

    if config.settings.default_profile:
        _launch_by_key(config.settings.default_profile, config, binary, forward_args)
        return

    cwd_key, _ = find_profile_for_cwd(config.profiles)

    show_selector(
        config.profiles,
        binary,
        forward_args,
        config.settings.show_profile_info,
        config_path,
        default_key=cwd_key,
    )


# ---------------------------------------------------------------------------
# claude-<key>  (generic direct-launch entry point)
# ---------------------------------------------------------------------------


def profile() -> None:
    """Generic entry point — derives the profile key from the command name (argv[0]).

    Register any claude-<key> command in pyproject.toml pointing here:
        claude-work     = "claude_switch.cli:profile"
        claude-personal = "claude_switch.cli:profile"
        claude-acme     = "claude_switch.cli:profile"
    """
    prog = Path(sys.argv[0]).stem  # e.g. "claude-work.exe" → "claude-work"
    prefix = "claude-"
    key = prog[len(prefix) :] if prog.startswith(prefix) else prog

    parser = _base_parser(prog, f"Launch Claude Code with the '{key}' profile.")
    our_args, forward_args = parser.parse_known_args()
    config, binary, config_path, is_new = _load(our_args.config)

    if is_new:
        show_first_run(config_path)
        sys.exit(0)

    _launch_by_key(key, config, binary, forward_args)
