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

from .config import Profile, save_config
from .launcher import launch

_VERSION = importlib.metadata.version("claude-switch")

_STYLE = Style(
    [
        ("qmark", "fg:#5fd7ff bold"),
        ("question", "bold"),
        ("answer", "fg:#5fd7ff bold"),
        ("pointer", "fg:#5fd7ff bold"),
        ("highlighted", "fg:#ffffff bold"),
        ("selected", "fg:#5fd7ff"),
        ("instruction", "fg:#555555"),
    ]
)

# Palette
_CYAN = "#5fd7ff"
_WHITE = "#ffffff"
_DIM = "#555555"
_GREEN = "#5fff87"
_AMBER = "#ffaf00"


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


def show_selector(
    profiles: dict[str, Profile],
    binary: str,
    forward_args: list[str],
    show_info: bool,
    config_path: Path | None = None,
) -> None:
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()
    _print_header(profiles, config_path)

    choices = []
    items = list(profiles.items())
    for i, (key, p) in enumerate(items):
        initialised = Path(p.config_dir).exists()
        dot = "● " if initialised else "○ "
        title = f"{dot}{p.name}"
        if p.description:
            title += f"  —  {p.description}"
        choices.append(questionary.Choice(title=title, value=key))
        if i < len(items) - 1:
            choices.append(questionary.Separator(""))

    if config_path is not None:
        choices.append(questionary.Separator())
        choices.append(questionary.Choice(title="⚙  Edit config", value="__edit__"))

    answer = questionary.select(
        "Which account?",
        choices=choices,
        style=_STYLE,
        use_shortcuts=False,
        instruction="(↑↓ · enter)",
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


def show_list(profiles: dict[str, Profile], config_path) -> None:
    _print_header(profiles, config_path)
    for key, p in profiles.items():
        config_dir = Path(p.config_dir)
        initialised = config_dir.exists()
        dot_color = f"fg:{_GREEN}" if initialised else f"fg:{_AMBER}"
        dot = "●" if initialised else "○"
        status = "" if initialised else "  not initialised"

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
                    ("", "\n\n"),
                ]
            )
        )
