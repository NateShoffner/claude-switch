# claude-switch

Multi-account Claude Code launcher. Runs Claude Code with `CLAUDE_CONFIG_DIR` set to a per-profile directory so each account has isolated config, history, and auth.

## Architecture

```
claude_switch/
  cli.py       — argparse entry points; main() and profile()
  config.py    — pydantic models (Config, Profile, Settings), load/save/find logic
  launcher.py  — sets CLAUDE_CONFIG_DIR and exec()s the Claude binary
  binary.py    — locates the claude binary (PATH or settings.claude_binary)
  shim.py      — installs/uninstalls a 'claude' shim that delegates to claude-switch
  state.py     — persists last-used profile to ~/.claude-switch-state.json
  ui.py        — questionary-based TUI: selector, list, add/edit/remove profile flows
```

## Entry points

`pyproject.toml` registers one main entry point:

- `claude-switch` → `cli:main` — interactive selector + all flags

Any number of direct-launch commands can be added:

```toml
claude-work     = "claude_switch.cli:profile"
claude-personal = "claude_switch.cli:profile"
```

`cli:profile` derives the profile key from `argv[0]` by stripping the `claude-` prefix.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"     # or: poetry install
```

Run directly without installing:

```bash
python -m claude_switch.cli
```

## Key conventions

- Config lives at `~/claude-switch.json`. On first run the default is written and the user is prompted to open it.
- All pydantic models use `model_validate` / `model_dump` (pydantic v2).
- `config_dir` paths are always expanded and resolved at validation time (`field_validator`).
- `working_paths` glob matching uses `fnmatch`; specificity is the index of the first `*` (longer literal prefix = more specific).
- The shim installs a `.claude-switch-shim` marker file alongside the shim scripts so `--uninstall` can find them by scanning PATH.
- The UI clears the screen before rendering the selector (`\033[2J\033[H`).
- `launcher.py` always calls `sys.exit(result.returncode)` so the exit code from Claude propagates.
