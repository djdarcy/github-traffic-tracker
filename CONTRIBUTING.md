# Contributing to GitHub Traffic Tracker

Thank you for considering contributing to GitHub Traffic Tracker!

## Code of Conduct

Please note that this project is released with a Contributor Code of Conduct.
By participating in this project you agree to abide by its terms.

## Development Setup

### Prerequisites

- Python 3.10+
- Git
- GitHub CLI (`gh`) for gist operations

### Getting Started

```bash
# Clone the repository
git clone https://github.com/djdarcy/github-traffic-tracker.git
cd github-traffic-tracker

# Install git hooks (recommended)
bash scripts/install-hooks.sh
```

## How to Contribute

### Reporting Bugs

- Check existing issues first
- Include steps to reproduce
- Include expected vs actual behavior

### Suggesting Features

- Open an issue with the `enhancement` label
- Describe the use case and expected behavior

### Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Run tests (`pytest`)
5. Commit with clear messages
6. Push and open a PR

## Project Structure

```
.github/workflows/
  traffic-badges.yml    # GitHub Actions workflow template
docs/stats/
  index.html            # Client-side dashboard template
scripts/
  setup-gists.py        # Onboarding automation
  update-version.sh     # Version management
  install-hooks.sh      # Git hook installer
tests/
  one-offs/             # Diagnostic and one-time scripts
```

## License

By contributing, you agree that your contributions will be licensed under the project's GPL-3.0 License.
