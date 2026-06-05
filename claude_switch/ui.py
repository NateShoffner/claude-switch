"""Interactive account selector."""

from __future__ import annotations

import importlib.metadata
import os
import platform
import subprocess
import sys
from pathlib import Path

import questionary
from prompt_toolkit import print_formatted_text as _print
from prompt_toolkit.formatted_text import FormattedText
from questionary import Style

from .config import Profile, die, save_config
from .keystore import get_admin_key, keychain_available, remove_from_keychain, store_in_keychain
from .launcher import launch
from .usage import (
    RateLimitInfo, UsageData,
    fetch_api_usage, fetch_local_usage, fetch_rate_limits, fetch_session_usage,
    fmt_tokens,
)

_VERSION = importlib.metadata.version("claude-switch")

_STYLE = Style(
    [
        ("qmark", "fg:#47b8d4 bold"),
        ("question", "bold"),
        ("answer", "fg:#47b8d4 bold"),
        ("pointer", "fg:#47b8d4 bold"),
        ("highlighted", "fg:#e0e0e0 bold"),
        ("selected", "fg:#47b8d4"),
        ("instruction", "fg:#6a6a6a"),
        ("separator", "fg:#6a6a6a"),
    ]
)

# Palette — muted, easy on dark terminals
_CYAN  = "#47b8d4"
_WHITE = "#e0e0e0"
_DIM   = "#6a6a6a"
_GREEN = "#52b36a"
_AMBER = "#c88c00"
_RED   = "#c04040"


_BAR_WIDTH = 40  # characters


def _usage_color(pct: float | None) -> str:
    if pct is None:
        return _WHITE
    if pct >= 90:
        return _RED
    if pct >= 60:
        return _AMBER
    return _GREEN


def _progress_bar(pct: float | None, width: int = _BAR_WIDTH) -> list[tuple[str, str]]:
    """Render a filled progress bar as FormattedText fragments."""
    filled = round((pct or 0) / 100 * width)
    color = _usage_color(pct)
    return [
        (f"fg:{color} bg:{color}", "█" * filled),
        (f"fg:#3a3a3a bg:#3a3a3a", "█" * (width - filled)),
    ]


def _usage_panel_rows(
    usage: UsageData,
    tz: str = "UTC",
    indent: str = "  ",
) -> list[tuple[str, str]]:
    """Build FormattedText rows for one usage panel (session or week)."""
    pct = usage.pct
    color = _usage_color(pct)
    label = "Current session" if usage.label == "session" else "Current week (all models)"

    token_str = fmt_tokens(usage.tokens)
    pct_str = f"{pct:.0f}% used  ({token_str})" if pct is not None else f"{token_str} tokens"
    reset_str = _format_reset(usage, tz)

    rows: list[tuple[str, str]] = [
        (f"fg:{_WHITE} bold", f"{indent}{label}"),
        ("", "\n"),
    ]
    if reset_str:
        rows += [
            (f"fg:{_DIM}", f"{indent}Resets {reset_str}"),
            ("", "\n"),
        ]
    rows += (
        [("", indent)]
        + _progress_bar(pct)
        + [
            ("", "  "),
            (f"fg:{color}", pct_str),
            ("", "\n"),
        ]
    )
    return rows


def _local_tz_name() -> str:
    """Return an IANA timezone name if possible, else a UTC-offset string."""
    try:
        import tzlocal
        return str(tzlocal.get_localzone())
    except Exception:
        pass
    try:
        from datetime import datetime
        offset = datetime.now().astimezone().utcoffset()
        if offset is not None:
            total = int(offset.total_seconds())
            h, m = divmod(abs(total) // 60, 60)
            sign = "+" if total >= 0 else "-"
            return f"UTC{sign}{h}" if m == 0 else f"UTC{sign}{h}:{m:02d}"
    except Exception:
        pass
    return "UTC"



def _format_reset(usage: UsageData, tz: str) -> str | None:
    from datetime import datetime, timezone as _tz
    if usage.reset_at is None:
        return None

    delta = usage.reset_at - datetime.now(tz=_tz.utc)
    if delta.total_seconds() <= 0:
        return "soon"

    # Convert to local time using system timezone
    try:
        from zoneinfo import ZoneInfo
        local = usage.reset_at.astimezone(ZoneInfo(tz))
    except Exception:
        local = usage.reset_at.astimezone()  # system local

    now_local = datetime.now().astimezone(local.tzinfo)
    h = local.hour
    ampm = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    minute_str = f":{local.minute:02d}" if local.minute else ""
    time_str = f"{h12}{minute_str}{ampm}"

    if local.date() == now_local.date():
        return f"{time_str} ({tz})"
    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    return f"{months[local.month - 1]} {local.day}, {time_str} ({tz})"


def _box(rows: list[list[tuple[str, str]]], width: int = 54) -> list[tuple[str, str]]:
    """Wrap a list of styled rows in a rounded box of fixed inner width."""
    border = f"fg:{_CYAN}"
    pad = width - 2  # inner content width

    fragments: list[tuple[str, str]] = []

    # top edge
    fragments += [
        ("", "  "),
        (border, "╭" + "─" * pad + "╮"),
        ("", "\n"),
    ]

    for row in rows:
        # measure plain length of this row
        plain = "".join(text for _, text in row)
        padding = " " * max(0, pad - 2 - len(plain))
        fragments += [
            ("", "  "),
            (border, "│"),
            ("", " "),
            *row,
            ("", padding),
            ("", " "),
            (border, "│"),
            ("", "\n"),
        ]

    # bottom edge
    fragments += [
        ("", "  "),
        (border, "╰" + "─" * pad + "╯"),
        ("", "\n"),
    ]

    return fragments


def _print_header(profiles: dict[str, Profile], config_path: Path | None) -> None:
    n = len(profiles)
    ver = f"v{_VERSION}"
    cfg_str = str(config_path) if config_path else "unknown"
    n_init = sum(1 for p in profiles.values() if Path(p.config_dir).exists())
    init_str = f"{n_init}/{n} initialised"

    title_row = [
        (f"fg:{_CYAN} bold", "claude-switch"),
        ("", "  "),
        (f"fg:{_DIM}", ver),
    ]
    config_row = [
        (f"fg:{_DIM}", "config    "),
        (f"fg:{_WHITE}", cfg_str),
    ]
    profiles_row = [
        (f"fg:{_DIM}", "profiles  "),
        (f"fg:{_WHITE}", str(n)),
        ("", "  "),
        (f"fg:{_DIM}", init_str),
    ]

    fragments = (
        [("", "\n")] + _box([title_row, [], config_row, profiles_row]) + [("", "\n")]
    )
    _print(FormattedText(fragments))


def show_first_run(config_path: Path) -> None:
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()
    _print(
        FormattedText(
            [
                ("", "\n"),
                ("", "  "),
                (f"fg:{_CYAN} bold", "claude-switch"),
                ("", "\n\n"),
                (
                    f"fg:{_WHITE}",
                    "  No config found. A default one has been created:\n",
                ),
                ("", "\n"),
                (f"fg:{_CYAN}", f"    {config_path}"),
                ("", "\n\n"),
                (
                    f"fg:{_DIM}",
                    "  Edit it to add your accounts, then run claude-switch again.\n",
                ),
                ("", "\n"),
            ]
        )
    )

    answer = questionary.confirm(
        "Open the config file now?",
        default=True,
        style=_STYLE,
    ).ask()

    if answer:
        _open_config(config_path)


def _open_config(config_path: Path) -> None:
    if platform.system() == "Windows":
        os.startfile(str(config_path))
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", str(config_path)])
    else:
        editor = os.environ.get("EDITOR", "xdg-open")
        subprocess.Popen([editor, str(config_path)])


def _fetch_profile_usage(profiles: dict[str, Profile]) -> dict[str, list[UsageData]]:
    result: dict[str, list[UsageData]] = {}
    for key, p in profiles.items():
        # Rate-limit headers give exact utilisation % and reset times
        rl = fetch_rate_limits(p.config_dir)

        session = fetch_session_usage(p.config_dir, p.session_token_limit)
        if session and rl:
            session.direct_pct = rl.session_pct
            session.reset_at = rl.session_reset_at

        weekly = fetch_local_usage(p.config_dir, p.weekly_token_limit)
        if not weekly:
            api_key = get_admin_key(key, p)
            if api_key:
                weekly = fetch_api_usage(api_key, p.weekly_token_limit)
        if weekly and rl:
            weekly.direct_pct = rl.week_pct
            weekly.reset_at = rl.week_reset_at

        entries = [e for e in [session, weekly] if e is not None]
        if entries:
            result[key] = entries
    return result


_COMPACT_BAR_WIDTH = 16


def _compact_usage_line(entries: list[UsageData], tz: str) -> str:
    """One-line usage summary for the selector, e.g.:
    S █████───────── 36%   W ██────────────── 14%   resets 7:49pm (UTC-4)

    Uses █ / ─ so filled vs empty is unambiguous in monochrome separator text.
    """
    parts: list[str] = []
    reset_str: str | None = None

    for u in entries:
        pct = u.pct
        label = "S" if u.label == "session" else "W"
        filled = round((pct or 0) / 100 * _COMPACT_BAR_WIDTH)
        bar = "█" * filled + "─" * (_COMPACT_BAR_WIDTH - filled)
        pct_part = f"{pct:.0f}%" if pct is not None else fmt_tokens(u.tokens)
        parts.append(f"{label} {bar} {pct_part}")
        if reset_str is None:
            reset_str = _format_reset(u, tz)

    line = "   ".join(parts)
    if reset_str:
        line += f"   resets {reset_str}"
    return line


def show_selector(
    profiles: dict[str, Profile],
    binary: str,
    forward_args: list[str],
    show_info: bool,
    config_path: Path | None = None,
    default_key: str | None = None,
) -> None:
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()
    _print_header(profiles, config_path)

    usage_map = _fetch_profile_usage(profiles)
    tz = _local_tz_name()

    choices = []
    items = list(profiles.items())
    for i, (key, p) in enumerate(items):
        initialised = Path(p.config_dir).exists()
        dot = "● " if initialised else "○ "
        title = f"{dot}{p.name}"
        if p.description:
            title += f"  —  {p.description}"
        title += f"  [{key}]"
        choices.append(questionary.Choice(title=title, value=key))

        if key in usage_map:
            line = _compact_usage_line(usage_map[key], tz)
            choices.append(questionary.Separator(f"    {line}"))

        if i < len(items) - 1:
            choices.append(questionary.Separator(""))

    if config_path is not None:
        choices.append(questionary.Separator())
        choices.append(questionary.Choice(title="⚙  Edit config", value="__edit__"))

    default_choice = next((c for c in choices if isinstance(c, questionary.Choice) and c.value == default_key), None)

    answer = questionary.select(
        "Which account?",
        choices=choices,
        default=default_choice,
        style=_STYLE,
        use_shortcuts=False,
        use_jk_keys=False,
        use_search_filter=True,
        instruction="(↑↓ · type to filter · enter)",
    ).ask()

    if not answer:
        sys.exit(0)

    if answer == "__edit__":
        _open_config(config_path)
        sys.exit(0)

    launch(answer, profiles[answer], binary, forward_args, show_info)


def add_profile(config, config_path: Path) -> None:
    """Interactively prompt for a new profile and save it to config."""
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()
    _print_header(config.profiles, config_path)

    existing_keys = set(config.profiles.keys())

    def _validate_key(val: str) -> bool | str:
        val = val.strip()
        if not val:
            return "Key cannot be empty"
        if not val.replace("-", "").replace("_", "").isalnum():
            return "Key can only contain letters, numbers, hyphens, and underscores"
        if val in existing_keys:
            return f"Profile '{val}' already exists"
        return True

    answers = questionary.form(
        key=questionary.text(
            "Profile key:",
            validate=_validate_key,
            instruction="(used in commands like claude-<key>)",
        ),
        name=questionary.text(
            "Display name:",
            validate=lambda v: True if v.strip() else "Name cannot be empty",
        ),
        config_dir=questionary.text(
            "Config directory:",
            default="~/.claude-",
            instruction="(where Claude stores this account's data)",
        ),
        description=questionary.text("Description:", instruction="(optional)"),
    ).ask()

    if answers is None:
        sys.exit(0)

    key = answers["key"].strip()
    name = answers["name"].strip()
    config_dir = answers["config_dir"].strip()
    description = answers["description"].strip()

    config.profiles[key] = Profile(
        name=name, config_dir=config_dir, description=description
    )
    save_config(config, config_path)

    _print(
        FormattedText(
            [
                ("", "\n"),
                (f"fg:{_GREEN} bold", "  ✓ "),
                (f"fg:{_WHITE}", f"Profile '{key}' added."),
                ("", "\n\n"),
                (
                    f"fg:{_DIM}",
                    f"  To add a direct launch command, add this to pyproject.toml:\n",
                ),
                (f"fg:{_CYAN}", f'    claude-{key} = "claude_switch.cli:profile"'),
                ("", "\n\n"),
            ]
        )
    )


def remove_profile(config, config_path: Path, key: str) -> None:
    if key not in config.profiles:
        available = ", ".join(config.profiles.keys())
        die(f"Profile '{key}' not found. Available: {available}")

    if len(config.profiles) == 1:
        die("Cannot remove the last profile.")

    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()
    _print_header(config.profiles, config_path)

    p = config.profiles[key]
    _print(
        FormattedText(
            [
                ("", "  "),
                (f"fg:{_WHITE} bold", p.name),
                ("", "  "),
                (f"fg:{_DIM}", p.config_dir),
                ("", "\n"),
                *([(f"fg:{_DIM}", f"  {p.description}\n")] if p.description else []),
                ("", "\n"),
            ]
        )
    )

    answer = questionary.confirm(
        f"Remove profile '{key}'?", default=False, style=_STYLE
    ).ask()

    if not answer:
        return

    del config.profiles[key]
    if config.settings.default_profile == key:
        config.settings.default_profile = None

    save_config(config, config_path)

    _print(
        FormattedText(
            [
                ("", "\n"),
                (f"fg:{_GREEN} bold", "  ✓ "),
                (f"fg:{_WHITE}", f"Profile '{key}' removed."),
                ("", "\n\n"),
            ]
        )
    )


def edit_profile(config, config_path: Path, key: str) -> None:
    if key not in config.profiles:
        available = ", ".join(config.profiles.keys())
        die(f"Profile '{key}' not found. Available: {available}")

    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()
    _print_header(config.profiles, config_path)

    _print(
        FormattedText(
            [
                ("", "  "),
                (f"fg:{_DIM}", "Editing profile: "),
                (f"fg:{_CYAN}", key),
                ("", "\n\n"),
            ]
        )
    )

    existing = config.profiles[key]

    answers = questionary.form(
        name=questionary.text(
            "Display name:",
            default=existing.name,
            validate=lambda v: True if v.strip() else "Name cannot be empty",
        ),
        config_dir=questionary.text(
            "Config directory:",
            default=existing.config_dir,
            instruction="(where Claude stores this account's data)",
        ),
        description=questionary.text("Description:", default=existing.description, instruction="(optional)"),
    ).ask()

    if answers is None:
        return

    config.profiles[key] = Profile(
        name=answers["name"].strip(),
        config_dir=answers["config_dir"].strip(),
        description=answers["description"].strip(),
        working_paths=existing.working_paths,
    )
    save_config(config, config_path)

    _print(
        FormattedText(
            [
                ("", "\n"),
                (f"fg:{_GREEN} bold", "  ✓ "),
                (f"fg:{_WHITE}", f"Profile '{key}' updated."),
                ("", "\n\n"),
            ]
        )
    )


def set_key(config, config_path: Path, key: str) -> None:
    """Interactively store an admin API key for a profile in the OS keychain."""
    if key not in config.profiles:
        available = ", ".join(config.profiles.keys())
        die(f"Profile '{key}' not found. Available: {available}")

    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()
    _print_header(config.profiles, config_path)

    p = config.profiles[key]
    _print(
        FormattedText(
            [
                ("", "  "),
                (f"fg:{_DIM}", "Setting admin API key for: "),
                (f"fg:{_CYAN}", p.name),
                ("", "\n\n"),
            ]
        )
    )

    if keychain_available():
        storage = "OS keychain (Windows Credential Manager / macOS Keychain)"
    else:
        storage = "config file (keyring not installed — pip install keyring for secure storage)"

    _print(
        FormattedText(
            [
                (f"fg:{_DIM}", f"  Key will be stored in: {storage}"),
                ("", "\n\n"),
            ]
        )
    )

    import getpass

    api_key = getpass.getpass("  Admin API key: ").strip()
    if not api_key:
        _print(FormattedText([(f"fg:{_AMBER}", "  Cancelled.\n")]))
        return

    if keychain_available():
        if store_in_keychain(key, api_key):
            # Remove plaintext key from config if it was there
            if config.profiles[key].admin_api_key:
                config.profiles[key] = config.profiles[key].model_copy(
                    update={"admin_api_key": None}
                )
                save_config(config, config_path)
            _print(
                FormattedText(
                    [
                        ("", "\n"),
                        (f"fg:{_GREEN} bold", "  ✓ "),
                        (f"fg:{_WHITE}", "Key stored in OS keychain."),
                        ("", "\n\n"),
                    ]
                )
            )
        else:
            _print(
                FormattedText(
                    [(f"fg:{_AMBER}", "  Keychain store failed — key was not saved.\n\n")]
                )
            )
    else:
        # Fall back to plaintext config with a warning
        config.profiles[key] = config.profiles[key].model_copy(
            update={"admin_api_key": api_key}
        )
        save_config(config, config_path)
        _print(
            FormattedText(
                [
                    ("", "\n"),
                    (f"fg:{_AMBER} bold", "  ⚠ "),
                    (
                        f"fg:{_WHITE}",
                        "Key saved to config file (plaintext).",
                    ),
                    ("", "\n"),
                    (
                        f"fg:{_DIM}",
                        "    Install keyring for secure storage: pip install keyring\n\n",
                    ),
                ]
            )
        )


def remove_key(config, config_path: Path, key: str) -> None:
    """Remove the admin API key for a profile from the keychain and/or config."""
    if key not in config.profiles:
        available = ", ".join(config.profiles.keys())
        die(f"Profile '{key}' not found. Available: {available}")

    removed_keychain = remove_from_keychain(key)
    p = config.profiles[key]
    removed_config = bool(p.admin_api_key)
    if removed_config:
        config.profiles[key] = p.model_copy(update={"admin_api_key": None})
        save_config(config, config_path)

    if removed_keychain or removed_config:
        sources = []
        if removed_keychain:
            sources.append("keychain")
        if removed_config:
            sources.append("config")
        _print(
            FormattedText(
                [
                    ("", "\n"),
                    (f"fg:{_GREEN} bold", "  ✓ "),
                    (f"fg:{_WHITE}", f"Key removed from {' and '.join(sources)}."),
                    ("", "\n\n"),
                ]
            )
        )
    else:
        _print(
            FormattedText(
                [
                    ("", "\n"),
                    (f"fg:{_AMBER}", "  No key found for this profile.\n\n"),
                ]
            )
        )


def show_list(profiles: dict[str, Profile], config_path) -> None:
    _print_header(profiles, config_path)
    usage_map = _fetch_profile_usage(profiles)
    for key, p in profiles.items():
        config_dir = Path(p.config_dir)
        initialised = config_dir.exists()
        dot_color = f"fg:{_GREEN}" if initialised else f"fg:{_AMBER}"
        dot = "●" if initialised else "○"
        status = "" if initialised else "  not initialised"

        # Profile header line
        _print(
            FormattedText(
                [
                    ("", "  "),
                    (dot_color, dot),
                    ("", "  "),
                    (f"fg:{_WHITE} bold", p.name),
                    (f"fg:{_DIM}", status),
                    ("", "\n"),
                    *(
                        [(f"fg:{_DIM}", f"     {p.description}\n")]
                        if p.description
                        else []
                    ),
                    (f"fg:{_DIM}", f"     {config_dir}"),
                    ("", "\n"),
                ]
            )
        )

        # Usage panels (session + week)
        entries = usage_map.get(key, [])
        if entries:
            tz = _local_tz_name()
            rows: list[tuple[str, str]] = [("", "\n")]
            for u in entries:
                rows += _usage_panel_rows(u, tz=tz, indent="     ")
                rows.append(("", "\n"))
            _print(FormattedText(rows))
        else:
            _print(FormattedText([("", "\n")]))
