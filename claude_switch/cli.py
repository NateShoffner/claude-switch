"""
Entry points registered in pyproject.toml.

    claude-switch        ->main()         interactive selector
    claude-<key>         ->profile()      direct launch, key derived from argv[0]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(format="  %(levelname)s: %(message)s", level=logging.WARNING)

from .binary import find_claude_binary
from .config import Config, die, find_config, find_profile_for_cwd, load_config
from .keystore import get_admin_key
from .launcher import launch
from .shim import install_shim, uninstall_shim
from .state import load_state
from .ui import add_profile, edit_profile, remove_key, remove_profile, set_key, show_first_run, show_list, show_selector
from .usage import fetch_local_usage, fetch_rate_limits, fetch_session_usage, fetch_weekly_usage, fmt_tokens


def _show_usage_diagnostic(key: str, config: Config) -> None:
    import json
    import urllib.error
    import urllib.request

    from .usage import _API_BASE, _API_VERSION, _TIMEOUT

    if key not in config.profiles:
        available = ", ".join(config.profiles.keys())
        die(f"Unknown profile '{key}'. Available: {available}")

    profile = config.profiles[key]
    api_key = get_admin_key(key, profile)

    print(f"\nProfile : {profile.name}  [{key}]")

    if not api_key:
        print("Key     : not set\n")
        return

    masked = api_key[:12] + "..." + api_key[-4:]
    source = (
        "keychain" if not profile.admin_api_key and not profile.admin_api_key_env
        else ("env:" + profile.admin_api_key_env if profile.admin_api_key_env else "config (plaintext)")
    )
    print(f"Key     : {masked}  ({source})")

    from datetime import datetime, timedelta, timezone
    end = datetime.now(tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=7)
    import urllib.parse
    params = urllib.parse.urlencode({
        "starting_at": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ending_at": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bucket_width": "1d",
    })
    url = f"{_API_BASE}/v1/organizations/usage_report/messages?{params}"
    print(f"URL     : {url}\n")

    req = urllib.request.Request(
        url,
        headers={"x-api-key": api_key, "anthropic-version": _API_VERSION},
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            body = resp.read().decode()
            print(f"Status  : {resp.status}")
            try:
                print("Response:", json.dumps(json.loads(body), indent=2))
            except Exception:
                print("Response:", body)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"HTTP {e.code}: {e.reason}")
        try:
            print(json.dumps(json.loads(body), indent=2))
        except Exception:
            print(body)
    except Exception as e:
        print(f"Error: {e}")
    print()


def _sync_plan(key: str, config: Config, config_path) -> None:
    from .config import save_config

    if key not in config.profiles:
        die(f"Unknown profile '{key}'. Available: {', '.join(config.profiles.keys())}")

    profile = config.profiles[key]
    print(f"\nSyncing plan limits for '{key}' ({profile.name})...\n")

    rl = fetch_rate_limits(profile.config_dir, force=True)
    if not rl:
        print("  Could not fetch rate limits — OAuth token missing or expired.")
        print("  Launch the profile and run /usage inside Claude Code to re-authenticate.\n")
        return

    session = fetch_session_usage(profile.config_dir)
    weekly = fetch_local_usage(profile.config_dir)

    rows = []

    if session and rl.session_pct > 0:
        session_limit = round(session.tokens / (rl.session_pct / 100))
        rows.append(("session", session.tokens, rl.session_pct, session_limit))
    else:
        rows.append(("session", session.tokens if session else 0, rl.session_pct, None))

    if weekly and rl.week_pct > 0:
        week_limit = round(weekly.tokens / (rl.week_pct / 100))
        rows.append(("week", weekly.tokens, rl.week_pct, week_limit))
    else:
        rows.append(("week", weekly.tokens if weekly else 0, rl.week_pct, None))

    print(f"  {'Window':<10}  {'Tokens used':>12}  {'Utilisation':>12}  {'Limit':>12}")
    print(f"  {'-'*10}  {'-'*12}  {'-'*12}  {'-'*12}")
    for label, tokens, pct, limit in rows:
        limit_str = fmt_tokens(limit) if limit else "unknown"
        print(f"  {label:<10}  {fmt_tokens(tokens):>12}  {pct:>11.1f}%  {limit_str:>12}")

    # Save back-calculated limits to profile config
    session_limit = next((r[3] for r in rows if r[0] == "session" and r[3]), None)
    week_limit = next((r[3] for r in rows if r[0] == "week" and r[3]), None)

    if session_limit or week_limit:
        print()
        updates = {}
        if session_limit:
            updates["session_token_limit"] = session_limit
            print(f"  session_token_limit ->{fmt_tokens(session_limit)}")
        if week_limit:
            updates["weekly_token_limit"] = week_limit
            print(f"  weekly_token_limit  ->{fmt_tokens(week_limit)}")

        config.profiles[key] = profile.model_copy(update=updates)
        save_config(config, config_path)
        print(f"\n  Saved to {config_path}\n")
    else:
        print("\n  Utilisation is 0% — no limits could be back-calculated.")
        print("  Use the profile first, then run --sync-plan again.\n")


def _base_parser(prog: str, description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=prog, description=description)
    p.add_argument(
        "--config",
        "-c",
        metavar="FILE",
        help="Path to a JSON config file (overrides default locations).",
    )
    return p


def _load(config_override: str | None) -> tuple[Config, Path, bool]:
    config_path, is_new = find_config(config_override)
    config = load_config(config_path)
    return config, config_path, is_new


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
        "--edit", metavar="KEY", help="Edit an existing profile interactively."
    )
    parser.add_argument(
        "--remove", metavar="KEY", help="Remove a profile (with confirmation)."
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
    parser.add_argument(
        "--set-key",
        metavar="KEY",
        help="Store an admin API key for a profile in the OS keychain.",
    )
    parser.add_argument(
        "--remove-key",
        metavar="KEY",
        help="Remove the admin API key for a profile from the keychain and config.",
    )
    parser.add_argument(
        "--usage",
        metavar="KEY",
        help="Show raw usage API response for a profile (diagnostic).",
    )
    parser.add_argument(
        "--sync-plan",
        metavar="KEY",
        help="Fetch current rate limits for a profile and save to config.",
    )

    our_args, forward_args = parser.parse_known_args()

    if our_args.install:
        install_shim()
        sys.exit(0)

    if our_args.uninstall:
        uninstall_shim()
        sys.exit(0)

    config, config_path, is_new = _load(our_args.config)

    if is_new:
        show_first_run(config_path)
        sys.exit(0)

    if our_args.set_key:
        set_key(config, config_path, our_args.set_key)
        sys.exit(0)

    if our_args.remove_key:
        remove_key(config, config_path, our_args.remove_key)
        sys.exit(0)

    if our_args.usage:
        _show_usage_diagnostic(our_args.usage, config)
        sys.exit(0)

    if our_args.sync_plan:
        _sync_plan(our_args.sync_plan, config, config_path)
        sys.exit(0)

    if our_args.add:
        add_profile(config, config_path)
        sys.exit(0)

    if our_args.remove:
        remove_profile(config, config_path, our_args.remove)
        sys.exit(0)

    if our_args.edit:
        edit_profile(config, config_path, our_args.edit)
        sys.exit(0)

    if our_args.list:
        show_list(config.profiles, config_path)
        sys.exit(0)

    binary = find_claude_binary(config.settings)

    if our_args.profile:
        _launch_by_key(our_args.profile, config, binary, forward_args)
        return

    if config.settings.default_profile:
        _launch_by_key(config.settings.default_profile, config, binary, forward_args)
        return

    cwd_key, _ = find_profile_for_cwd(config.profiles)

    last_key = load_state().last_profile
    if last_key not in config.profiles:
        last_key = None

    show_selector(
        config.profiles,
        binary,
        forward_args,
        config.settings.show_profile_info,
        config_path,
        default_key=cwd_key or last_key,
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
    prog = Path(sys.argv[0]).stem  # e.g. "claude-work.exe" ->"claude-work"
    prefix = "claude-"
    key = prog[len(prefix) :] if prog.startswith(prefix) else prog

    parser = _base_parser(prog, f"Launch Claude Code with the '{key}' profile.")
    our_args, forward_args = parser.parse_known_args()
    config, config_path, is_new = _load(our_args.config)

    if is_new:
        show_first_run(config_path)
        sys.exit(0)

    binary = find_claude_binary(config.settings)
    _launch_by_key(key, config, binary, forward_args)
