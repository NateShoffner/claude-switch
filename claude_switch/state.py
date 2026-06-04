"""Persistent runtime state (last-used profile, etc.)."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

_STATE_PATH = Path.home() / ".claude-switch-state.json"


class State(BaseModel):
    last_profile: str | None = None


def load_state() -> State:
    try:
        return State.model_validate(json.loads(_STATE_PATH.read_text()))
    except Exception:
        return State()


def save_state(state: State) -> None:
    try:
        _STATE_PATH.write_text(json.dumps(state.model_dump(), indent=2))
    except Exception:
        pass
