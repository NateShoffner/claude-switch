# claude-switch

Multi-account Claude Code launcher. Switch between personal, work, or any number of Anthropic accounts, each with its own isolated config directory, history, and auth. Shows live session and weekly token usage in the selector.

## Installation

Install with [pipx](https://pipx.pypa.io/) from GitHub:

```bash
pipx install git+https://github.com/nateshoffner/claude-switch.git
```

Or from a wheel on the [latest release](https://github.com/nateshoffner/claude-switch/releases/latest):

```bash
pipx install claude_switch-0.3.0-py3-none-any.whl
```

To make plain `claude` open the selector, run `claude-switch --install`. It writes a shim onto your PATH. Undo with `claude-switch --uninstall`.

## Usage

```bash
claude-switch                             # interactive selector
claude-switch --profile work              # launch a profile directly
claude-switch -d                          # launch the built-in default profile (~/.claude)
claude-default                            # same, as a standalone command
claude-switch --list                      # show all profiles and usage stats
claude-switch --add                       # add a profile interactively
claude-switch --edit work                 # edit a profile
claude-switch --remove work               # remove a profile (with confirmation)
claude-switch --sync-plan personal        # fetch and save token limits for a profile
claude-switch --set-key personal          # store an admin API key in the OS keychain
claude-switch --remove-key personal       # remove a stored admin API key
claude-switch --config ~/other.json       # use an alternate config file
claude-switch --install / --uninstall     # manage the 'claude' shim
claude-switch --warm                      # start the 5-hour window for every profile
claude-switch --install-warm              # run --warm on a schedule (every 30 min)
```

## Config

The config file lives at `~/claude-switch.json` and is created with defaults on first run:

```json
{
  "profiles": {
    "personal": {
      "name": "Personal",
      "config_dir": "~/.claude-personal",
      "description": "Personal Anthropic account"
    },
    "work": {
      "name": "Work",
      "config_dir": "~/.claude-work",
      "description": "Work Anthropic account"
    }
  },
  "settings": {
    "default_profile": null,
    "claude_binary": null,
    "show_profile_info": true
  }
}
```

New entries are picked up immediately. For a dedicated `claude-acme` command, add a line to `pyproject.toml` and reinstall. The command name sets the profile key:

```toml
[project.scripts]
claude-acme = "claude_switch.cli:profile"
```

### Profile fields

| Field                 | Required | Description                                             |
|-----------------------|----------|---------------------------------------------------------|
| `name`                | yes      | Display name shown in the selector                      |
| `config_dir`          | yes      | Path to this profile's Claude config dir (`~` expands)  |
| `description`         | no       | Subtitle shown in the selector                          |
| `working_paths`       | no       | Glob patterns that pre-select this profile by cwd       |
| `weekly_token_limit`  | no       | Weekly token budget for usage % display                 |
| `session_token_limit` | no       | 5-hour session token budget for usage % display         |
| `admin_api_key`       | no       | Anthropic org admin key (see [Admin API](#admin-api))   |
| `admin_api_key_env`   | no       | Env var name to read the admin key from                 |

### Settings fields

| Field               | Default | Description                                                 |
|---------------------|---------|-------------------------------------------------------------|
| `default_profile`   | `null`  | Skip the selector and always launch this profile            |
| `claude_binary`     | `null`  | Explicit path to the Claude binary (found via PATH if null) |
| `show_profile_info` | `true`  | Log account and path info before launching                  |

### The `default` profile

`default` is a reserved, built-in profile that always appears first. It launches Claude with `CLAUDE_CONFIG_DIR` unset, so it uses the stock `~/.claude` shared with the Claude desktop app. It can't be defined in the config file, and the per-profile commands (`--edit`, `--remove`, `--set-key`, `--remove-key`, `--usage`, `--sync-plan`) don't apply to it.

### working_paths

When the current directory matches a profile's `working_paths`, the selector opens with that profile pre-selected. Patterns are globs: `~` expands to home and `**` matches any depth. The most specific match wins, and ties go to the first match.

```json
"working_paths": ["~/work/**", "C:/Work/**", "~/work/client-*"]
```

## Usage display

The selector and `--list` show live session and weekly usage per profile:

```
❯ ● Personal  -  Personal Anthropic account  [personal]
    S ██████──────────── 36%   W ██──────────────── 14%   resets 7:49pm (UTC-4)
```

Token counts come from Claude Code's local files. Utilisation and reset times come from Anthropic's rate-limit headers, using the OAuth token already stored in each profile's config dir. Results are cached for 5 minutes.

### Syncing token limits

Percentages need your plan's token budget. Run `--sync-plan` once after setup and whenever your plan changes. It makes a minimal API call, back-calculates the limits from the response headers, and saves them to your config:

```bash
claude-switch --sync-plan personal
```

### Keeping the 5-hour window warm

The 5-hour session window starts at your first message. `claude-switch --warm` makes sure each profile has one running: if a window is already active it does nothing, otherwise it sends a single 1-token Haiku request. Use `--warm --profile work` to limit it to one profile.

`--install-warm` schedules this every 30 minutes (Task Scheduler on Windows, cron elsewhere) and `--uninstall-warm` removes it. Since an active window makes each run a free no-op, the interval only bounds how late a new window starts after the last one ends.

If a profile's OAuth token has expired, `--warm` falls back to a short `claude -p` call, which also refreshes the token but costs more. A profile with no credentials is reported as `failed`; launch it and log in.

## Admin API

`admin_api_key` accepts an Anthropic organization admin key (`sk-ant-admin...`) for profiles that use the [Anthropic API](https://platform.claude.com/docs/en/manage-claude/usage-cost-api) rather than a Claude.ai subscription. Claude.ai subscribers don't need one.

Keys are resolved in this order:

1. **OS keychain**: Windows Credential Manager, macOS Keychain, or Linux Secret Service. Store with `claude-switch --set-key work`.
2. **Environment variable**: set `admin_api_key_env` in the profile.
3. **Config file**: `admin_api_key` in `~/claude-switch.json`, in plaintext.

Keychain support needs the optional `keyring` package:

```bash
pipx inject claude-switch keyring
```

## Disclaimer

This project is not affiliated with, endorsed by, or supported by Anthropic. Use at your own risk. No warranties of any kind are given, and no responsibility is accepted for any issues arising from its use.
