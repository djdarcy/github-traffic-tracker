# Command Line Parameters

Complete reference for all `ghtraf` command line options.

## Quick Reference

```bash
ghtraf [GLOBAL FLAGS] COMMAND [COMMAND OPTIONS]
```

## Global Flags

These flags can appear before or after the subcommand.

| Flag | Description |
|------|-------------|
| `-v`, `--verbose` | Increase verbosity (`-v`, `-vv`, `-vvv`). Stackable. |
| `-Q`, `--quiet` | Decrease verbosity (`-Q`, `-QQ`, `-QQQ`, `-QQQQ`=silent). Stackable. |
| `--show [CHANNEL[:LEVEL]]` | Show a specific output channel. Repeatable. Bare `--show` lists channels. |
| `--no-color` | Disable colored output |
| `--config PATH` | Path to configuration file |
| `-n`, `--non-interactive` | Skip all prompts (use defaults or fail) |
| `--dry-run` | Preview changes without making them |
| `--repo-dir PATH` | Target repository directory (default: current directory) |
| `--owner OWNER` | GitHub owner (username or org) |
| `--repo REPO` | Repository name |

## Verbosity System (THAC0)

`ghtraf` uses a structured verbosity system with a single-axis dial and named output channels.

### How verbosity works

The **effective verbosity** is: `(number of -v flags) − (number of -Q flags)`.

A diagnostic message with level N is shown when `effective verbosity >= N`. Normal output (level 0) is always shown unless suppressed with `-Q`.

| Effective Level | What you see |
|-----------------|--------------|
| -4 | Nothing (silent — errors only) |
| -3 | Errors only |
| -2 | Errors + warnings |
| -1 | Errors + warnings + hints |
| 0 | Normal output (default) |
| +1 | + setup steps, API calls, gist operations |
| +2 | + config resolution, gist IDs, internal detail |
| +3 | + debug tracing |

```bash
ghtraf create ...              # Level 0 — normal output
ghtraf -v create ...           # Level 1 — adds diagnostic messages
ghtraf -vv create ...          # Level 2 — adds config detail
ghtraf -vvv create ...         # Level 3 — debug tracing
ghtraf -Q create ...           # Level -1 — quieter
ghtraf -QQ create ...          # Level -2 — warnings and errors only
ghtraf -QQQQ create ...        # Level -4 — silent
ghtraf -vv -Q create ...       # Net level 1 (composable)
```

### Named channels

Instead of turning up verbosity globally, `--show` reveals output from specific channels without noise from other subsystems.

```bash
ghtraf --show gist:2 create ...          # Gist channel at level 2
ghtraf --show api --show config create ...  # API + config channels
ghtraf --show                            # List all available channels
```

Channel spec syntax: `CHANNEL[:LEVEL]`. When LEVEL is omitted, the channel is shown at all levels.

#### Available channels

| Channel | Description | Opt-in? |
|---------|-------------|---------|
| `api` | GitHub API calls and responses | |
| `config` | Configuration loading and resolution | |
| `gist` | Gist operations (create, read, update) | |
| `setup` | Setup and initialization steps | |
| `general` | General output | |
| `hint` | Contextual tips and suggestions | |
| `error` | Error messages | |
| `trace` | Function call tracing | Yes |

**Opt-in channels** are not shown by `-v` alone — they require explicit `--show trace` to enable.

### How -v and --show interact

| Scenario | What's shown |
|----------|-------------|
| `ghtraf create` | Normal output only |
| `ghtraf -v create` | Normal + all non-opt-in channels at level 1 |
| `ghtraf --show gist create` | Normal + gist channel only (at all levels) |
| `ghtraf --show gist:2 create` | Normal + gist channel at level 2 |
| `ghtraf -v --show trace create` | Normal + level 1 diagnostics + trace channel |
| `ghtraf -QQ create` | Warnings and errors only |

## Commands

### `ghtraf create`

Create gists and configure a repository for traffic tracking.

```bash
ghtraf create --owner YOUR_ORG --repo YOUR_REPO
ghtraf create --owner YOUR_ORG --repo YOUR_REPO --configure
ghtraf create --dry-run
```

#### Create Options

| Flag | Description |
|------|-------------|
| `--created DATE` | Repository creation date (YYYY-MM-DD). Auto-detected if omitted. |
| `--display-name NAME` | Display name for dashboard title/banner |
| `--ci-workflows NAME...` | CI workflow names for `workflow_run` trigger |
| `--configure` | Also update dashboard and workflow files with your values |
| `--skip-variables` | Skip setting repository variables/secrets |
| `--gist-token-name NAME` | Name for the gist token secret (default: `TRAFFIC_GIST_TOKEN`) |

#### Create Examples

```bash
# Interactive setup (prompts for all values)
ghtraf create

# Fully automated
ghtraf create --owner djdarcy --repo my-project --configure --non-interactive

# Preview without making changes
ghtraf create --dry-run --owner djdarcy --repo my-project --non-interactive

# With CI workflow trigger
ghtraf create --owner djdarcy --repo my-project --ci-workflows "CI" "Tests"

# See diagnostic output during setup
ghtraf -v create --owner djdarcy --repo my-project

# Debug gist operations specifically
ghtraf --show gist:2 create --dry-run --owner djdarcy --repo my-project --non-interactive
```
