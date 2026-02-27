# Platform Support

GitHub Traffic Tracker has two components with different platform considerations: the **GitHub Actions workflow** (runs in the cloud) and the **CLI tools** (`ghtraf`, `setup-gists.py`) that run on your local machine.

## Workflow (GitHub Actions)

The workflow runs on `ubuntu-latest` in GitHub's cloud infrastructure. It requires no local platform support — once configured, it works identically regardless of your development machine.

## CLI Tools

The `ghtraf` CLI and `setup-gists.py` setup script run locally and depend on:

- **Python 3.10+**
- **[gh CLI](https://cli.github.com)** (GitHub's official CLI, authenticated)

| Platform | Status | Notes |
|----------|--------|-------|
| **Windows** | Tested | Primary development platform. Works with both CMD and PowerShell. WSL also supported. |
| **macOS** | Expected to work | Python and gh CLI available via Homebrew. Not yet tested — feedback welcome. |
| **Linux** | Expected to work | Python and gh CLI available via package managers. Not yet tested — feedback welcome. |

## Dashboard

The static HTML dashboard (`docs/stats/index.html`) is pure client-side JavaScript that runs in any modern browser. It reads data from GitHub's Gist CDN, which has permissive CORS headers. No platform-specific considerations.

## Known Issues

### Windows: UTF-8 encoding

The `gh` CLI outputs UTF-8, but Python's `subprocess.run(text=True)` on Windows defaults to the system code page (typically cp1252). The `ghtraf` CLI handles this by explicitly passing `encoding="utf-8"` to all subprocess calls. If you're writing custom scripts that call `gh`, be aware of this — you may see mojibake (e.g., `✓` displayed as `âœ"`) without explicit UTF-8 encoding.

### gh CLI installation

The `gh` CLI is required for all API operations. Installation varies by platform:

| Platform | Install command |
|----------|----------------|
| **Windows** | `winget install GitHub.cli` |
| **macOS** | `brew install gh` |
| **Linux (Debian/Ubuntu)** | See [gh CLI Linux install guide](https://github.com/cli/cli/blob/trunk/docs/install_linux.md) |

After installation, authenticate with `gh auth login`.

## Feedback

If you encounter platform-specific issues, please [open an issue](https://github.com/djdarcy/github-traffic-tracker/issues) with your OS version, Python version, and gh CLI version (`gh --version`).
