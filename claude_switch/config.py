"""Config loading, models, and path resolution."""

from __future__ import annotations

import fnmatch
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
    working_paths: list[str] = []

    @field_validator("config_dir")
    @classmethod
    def expand_config_dir(cls, v: str) -> str:
        return str(Path(v).expanduser().resolve())

    def best_cwd_match(self, cwd: Path) -> int | None:
        """Return the specificity score of the best matching path pattern, or None if no match."""
        cwd_str = str(cwd)
        best: int | None = None
        for pattern in self.working_paths:
            expanded = str(Path(pattern).expanduser())
            if fnmatch.fnmatch(cwd_str, expanded) or cwd_str.startswith(
                expanded.rstrip("*").rstrip("/").rstrip("\\")
            ):
                score = _pattern_specificity(expanded)
                if best is None or score > best:
                    best = score
        return best


def _pattern_specificity(pattern: str) -> int:
    idx = pattern.find("*")
    return idx if idx >= 0 else len(pattern)


def find_profile_for_cwd(profiles: dict[str, Profile]) -> tuple[str | None, bool]:
    """Match cwd against all profile path patterns.

    Returns (key, ambiguous):
      - (key, False)  → one clear winner, auto-launch it
      - (key, True)   → best guess but tie exists, pre-select in selector
      - (None, False) → no patterns matched, show selector normally
    """
    cwd = Path.cwd()
    scores: dict[str, int] = {}
    for key, profile in profiles.items():
        score = profile.best_cwd_match(cwd)
        if score is not None:
            scores[key] = score

    if not scores:
        return None, False

    best_score = max(scores.values())
    winners = [k for k, s in scores.items() if s == best_score]

    if len(winners) == 1:
        return winners[0], False
    else:
        return winners[0], True


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
            **({"working_paths": p.working_paths} if p.working_paths else {}),
        }
        for key, p in config.profiles.items()
    }
    raw["settings"] = config.settings.model_dump()
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
