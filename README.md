# claude-switch

Multi-account Claude Code launcher. Switch between personal, work, or any number of Anthropic accounts — each with its own isolated config directory, history, and auth. Shows live session and weekly token usage in the selector.

---

## Installation

### Via pipx (recommended)

```bash
# macOS
brew install pipx && pipx ensurepath

# Windows
scoop install pipx        # or: pip install --user pipx
pipx ensurepath

# Ubuntu/Debian
sudo apt install pipx && pipx ensurepath
```

Install from a local clone:

```bash
git clone https://github.com/nateshoffner/claude-switch.git
pipx install ./claude-switch
```

Or directly from GitHub:

```bash
pipx install git+https://github.com/nateshoffner/claude-switch.git
```

### Optional: use `claude` instead of `claude-switch`

```bash
claude-switch --install
```

This writes a shim so that typing `claude` opens the account selector. Undo it with `claude-switch --uninstall`.

---

## Usage

```bash
claude-switch                             # interactive selector
claude-switch --profile work              # jump directly to a profile
claude-switch --list                      # show all profiles and usage stats
claude-switch --add                       # add a new profile interactively
claude-switch --edit work                 # edit an existing profile
claude-switch --remove work               # remove a profile (with confirmation)
claude-switch --sync-plan personal        # fetch and save token limits for a profile
claude-switch --set-key personal          # store an admin API key in the OS keychain
claude-switch --remove-key personal       # remove a stored admin API key
claude-switch --config ~/other.json       # use an alternate config file
claude-switch --install / --uninstall     # manage the 'claude' shim
```

---

## Config

The config file lives at `~/claude-switch.json`. It's created with defaults on first run — edit it to match your accounts:

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

### Profile fields

| Field                 | Required | Description                                             |
|-----------------------|----------|---------------------------------------------------------|
| `name`                | yes      | Display name shown in the selector                      |
| `config_dir`          | yes      | Path to this profile's Claude config dir (`~` expands)  |
| `description`         | no       | Subtitle shown in the selector                          |
| `working_paths`       | no       | Glob patterns — suggests this profile when cwd matches  |
| `weekly_token_limit`  | no       | Weekly token budget for usage % display                 |
| `session_token_limit` | no       | 5-hour session token budget for usage % display         |
| `admin_api_key`       | no       | Anthropic org admin key (see [Admin API](#admin-api))   |
| `admin_api_key_env`   | no       | Env var name to read the admin key from                 |

### Settings fields

| Field               | Default | Description                                             |
|---------------------|---------|---------------------------------------------------------|
| `default_profile`   | `null`  | Skip the selector and always launch this profile        |
| `claude_binary`     | `null`  | Explicit path to the Claude binary (found via PATH if null) |
| `show_profile_info` | `true`  | Log account and path info before launching              |

---

## Usage display

The selector and `--list` view show live session and weekly token usage for each profile:

```
❯ ● Personal  —  Personal Anthropic account  [personal]
    S ██████──────────── 36%   W ██──────────────── 14%   resets 7:49pm (UTC-4)
```

Token counts are read from Claude Code's local files. Utilisation percentages and exact reset times are fetched from Anthropic's rate-limit headers using the OAuth token already stored in each profile's config dir — no extra setup required.

Results are cached for 5 minutes so the selector stays fast.

### Syncing token limits

To show percentages, claude-switch needs to know your plan's token budget. Run `--sync-plan` once after setup and whenever your plan changes:

```bash
claude-switch --sync-plan personal
```

This makes a minimal API call, reads the current utilisation from the response headers, back-calculates the limits, and saves them to your config:

```
  Window       Tokens used   Utilisation         Limit
  ----------  ------------  ------------  ------------
  session             283k         36.0%          786k
  week                699k         14.0%          5.0M

  session_token_limit -> 786k
  weekly_token_limit  -> 5.0M
```

---

## working_paths

If `working_paths` is set, the selector opens with that profile pre-selected when the current directory matches. You can confirm or choose a different one.

Patterns are glob-matched against the current working directory. `~` expands to the home directory, and `**` matches any subdirectory depth.

```json
"work": {
  "name": "Work",
  "config_dir": "~/.claude-work",
  "working_paths": [
    "~/work/**",
    "C:/Work/**",
    "~/work/client-*"
  ]
}
```

| Pattern               | Matches                                                  |
|-----------------------|----------------------------------------------------------|
| `~/projects/**`       | Anything under `~/projects/`, at any depth               |
| `C:/Work/**`          | Anything under `C:\Work\` (Windows)                      |
| `~/work/client-*`     | Direct children of `~/work/` starting with `client-`    |
| `/home/user/work/acme`| That exact directory only                                |

If multiple profiles match, the one with the most specific pattern wins. On a tie, the selector opens with the first match pre-selected.

---

## Admin API

`admin_api_key` accepts an Anthropic organization admin key (`sk-ant-admin...`) for profiles that use the [Anthropic API](https://platform.claude.com/docs/en/manage-claude/usage-cost-api) rather than a Claude.ai subscription. For Claude.ai subscribers, usage data is read locally and no admin key is needed.

### Secure key storage

Keys are resolved in this order, highest security first:

1. **OS keychain** — Windows Credential Manager / macOS Keychain / Linux Secret Service
2. **Environment variable** — set `admin_api_key_env: "MY_VAR"` in the profile
3. **Config file** — `admin_api_key` stored in `~/claude-switch.json` (plaintext, least secure)

To store a key in the keychain:

```bash
claude-switch --set-key work
```

Keychain support requires the optional `keyring` package:

```bash
pip install keyring
# or
pipx inject claude-switch keyring
```

---

## Adding more profiles

Add entries to `~/claude-switch.json` — the selector picks them up immediately:

```json
"client-acme": {
  "name": "Acme Corp",
  "config_dir": "~/.claude-acme",
  "description": "Acme contract work"
}
```

To get a dedicated `claude-acme` command, add one line to `pyproject.toml` and reinstall:

```toml
[project.scripts]
claude-acme = "claude_switch.cli:profile"
```

The command name determines the profile key — `claude-acme` launches the `acme` profile automatically.

---

## Disclaimer

This project is not affiliated with, endorsed by, or supported by Anthropic. Use at your own risk. The author(s) make no warranties of any kind and accept no responsibility for any issues arising from its use.
