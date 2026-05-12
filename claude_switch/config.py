"""Config loading, models, and path resolution."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from pydantic import BaseModel, field_validator

log = logging.getLogger(__name__)


def _default_config_locations() -> list[Path]:
    return [Path.home() / "claude-switch.json"]


_DEFAULT_CONFIG_LOCATIONS = _default_config_locations()


class Profile(BaseModel):
    name: str
    config_dir: str
    description: str = ""

    @field_validator("config_dir")
    @classmethod
    def expand_config_dir(cls, v: str) -> str:
        return str(Path(v).expanduser().resolve())


class Settings(BaseModel):
    default_profile: str | None = None
    claude_binary: str | None = None
    show_profile_info: bool = True


class Config(BaseModel):
    profiles: dict[str, Profile]
    settings: Settings = Settings()

    @field_validator("profiles")
    @classmethod
    def require_profiles(cls, v: dict) -> dict:
        if not v:
            raise ValueError("at least one profile must be defined")
        return v


_DEFAULT_CONFIG = {
    "profiles": {
        "personal": {
            "name": "Personal",
            "config_dir": "~/.claude-personal",
            "description": "Personal Anthropic account",
        },
        "work": {
            "name": "Work",
            "config_dir": "~/.claude-work",
            "description": "Work Anthropic account",
        },
    },
    "settings": {
        "default_profile": None,
        "claude_binary": None,
        "show_profile_info": True,
    },
}


def die(message: str) -> None:
    log.error(message)
    sys.exit(1)


def find_config(override: str | None) -> tuple[Path, bool]:
    """Return (config_path, is_new). is_new is True when the file was just created."""
    if override:
        p = Path(override).expanduser()
        if not p.exists():
            die(f"Config file not found: {p}")
        return p, False

    for candidate in _DEFAULT_CONFIG_LOCATIONS:
        if candidate.exists():
            return candidate, False

    primary = _DEFAULT_CONFIG_LOCATIONS[0]
    primary.parent.mkdir(parents=True, exist_ok=True)
    primary.write_text(json.dumps(_DEFAULT_CONFIG, indent=2))
    return primary, True


def save_config(config: Config, path: Path) -> None:
    raw = json.loads(path.read_text())
    raw["profiles"] = {
        key: {
            "name": p.name,
            "config_dir": p.config_dir,
            **({"description": p.description} if p.description else {}),
        }
        for key, p in config.profiles.items()
    }
    path.write_text(json.dumps(raw, indent=2))


def load_config(path: Path) -> Config:
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        die(f"Invalid JSON in {path}: {e}")

    try:
        return Config.model_validate(raw)
    except Exception as e:
        die(f"Invalid config in {path}: {e}")
