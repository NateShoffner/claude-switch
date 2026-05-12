# claude-switch

Multi-account Claude Code launcher. Switch between personal, work, or any number of Anthropic accounts - each with its own isolated config directory.

---

## Installation

### Via pipx (recommended)

[pipx](https://pipx.pypa.io) installs CLI tools into isolated environments and puts them on your PATH automatically.

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

After installing, run:

```bash
claude-switch --install
```

This writes a small shim so that typing `claude` opens the account selector instead of launching Claude Code directly. Undo it with:

```bash
claude-switch --uninstall
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

| Field           | Required | Description                                             |
|-----------------|----------|---------------------------------------------------------|
| `name`          | yes      | Display name shown in the selector                      |
| `config_dir`    | yes      | Path to this profile's Claude config dir (`~` expands)  |
| `description`   | no       | Subtitle shown in the selector                          |
| `working_paths` | no       | Glob patterns — auto-selects this profile when cwd matches |

If `working_paths` is set and the current directory matches a profile, the selector opens with that profile pre-selected as a suggestion. You can confirm or choose a different one.

```json
"work": {
  "name": "Work",
  "config_dir": "~/.claude-work",
  "working_paths": ["~/work/**", "D:/Work/**"]
}
```

### Settings fields

| Field               | Default | Description                                             |
|---------------------|---------|---------------------------------------------------------|
| `default_profile`   | `null`  | Skip the selector and always launch this profile        |
| `claude_binary`     | `null`  | Explicit path to the Claude binary (found via PATH if null) |
| `show_profile_info` | `true`  | Log account and path info before launching              |

---

## Usage

```bash
# Interactive selector:
claude-switch
claude-switch /path/to/project

# Jump directly to a profile:
claude-switch --profile work /path/to/project

# Other flags:
claude-switch --list                          # show all profiles and their status
claude-switch --config ~/other.json           # use an alternate config file
claude-switch --install                       # install the 'claude' shim
claude-switch --uninstall                     # remove the 'claude' shim
```

---

## First-time Login

Each profile is isolated — you'll need to log in once per account:

```bash
claude-switch --profile personal   # launches → /login → sign in with personal account
claude-switch --profile work       # new terminal → /login → sign in with work account
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

This project is an independent, community-built tool and is not affiliated with, endorsed by, or supported by Anthropic. Use at your own risk. The author(s) make no warranties of any kind and accept no responsibility for any issues arising from its use, including but not limited to account problems, data loss, or violations of Anthropic's terms of service.

---

## Project Structure

```
claude-switch/
├── pyproject.toml
├── README.md
└── claude_switch/
    ├── cli.py          ← entry points (claude-switch, claude-<key>)
    ├── config.py       ← Pydantic models + config loading
    ├── binary.py       ← Claude binary resolution
    ├── launcher.py     ← subprocess launch
    ├── shim.py         ← claude shim install/uninstall
    └── ui.py           ← interactive selector UI
```
