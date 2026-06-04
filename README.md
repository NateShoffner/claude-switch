# claude-switch

Multi-account Claude Code launcher. Switch between personal, work, or any number of Anthropic accounts - each with its own isolated config directory.

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

| Field           | Required | Description                                             |
|-----------------|----------|---------------------------------------------------------|
| `name`          | yes      | Display name shown in the selector                      |
| `config_dir`    | yes      | Path to this profile's Claude config dir (`~` expands)  |
| `description`   | no       | Subtitle shown in the selector                          |
| `working_paths` | no       | Glob patterns — suggests this profile when cwd matches  |

If `working_paths` is set and the current directory matches a profile, the selector opens with that profile pre-selected as a suggestion. You can confirm or choose a different one.

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

### Settings fields

| Field               | Default | Description                                             |
|---------------------|---------|---------------------------------------------------------|
| `default_profile`   | `null`  | Skip the selector and always launch this profile        |
| `claude_binary`     | `null`  | Explicit path to the Claude binary (found via PATH if null) |
| `show_profile_info` | `true`  | Log account and path info before launching              |

---

## Usage

```bash
claude-switch                             # interactive selector
claude-switch --profile work              # jump directly to a profile
claude-switch --list                      # show all profiles and their status
claude-switch --add                       # add a new profile interactively
claude-switch --edit work                 # edit an existing profile interactively
claude-switch --remove work               # remove a profile (with confirmation)
claude-switch --config ~/other.json       # use an alternate config file
claude-switch --install / --uninstall     # manage the 'claude' shim
```

---

## Adding More Profiles

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
