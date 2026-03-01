# Test Fixture: Way-of-Scarcity/papers

**Source**: https://github.com/Way-of-Scarcity/papers
**Snapshot date**: 2026-02-28
**Snapshot commit**: main (HEAD at snapshot time)

## Purpose

This is a minimal snapshot of a real GitHub repository used for integration
testing of `ghtraf init`. Only the README.md is included — the original repo
contains ~13 MB of PDFs that are irrelevant to template deployment testing.

## What this tests

- `ghtraf init` correctly creates `.github/workflows/` and `docs/stats/` in a
  repo that doesn't have them
- Original repo files (README.md) are untouched after init
- Template files have real content after deployment
- Overwrite flags (--force, --skip-existing) work against a real repo layout

## Updating this fixture

To refresh from upstream:

```bash
# Clone fresh and copy just the README
git clone --depth 1 https://github.com/Way-of-Scarcity/papers.git /tmp/papers-update
cp /tmp/papers-update/README.md tests/test-data/repos/papers/README.md
rm -rf /tmp/papers-update
```

## Full integration testing

For live clone tests (network required), use:

```bash
pytest -m integration
```

These tests clone the real repo and run the full init pipeline against it.
They are not run by default.

## Future: deploy testing

End-to-end tests that push to a private GitHub repo and verify the workflow
runs are planned but not yet implemented. These would use:

```bash
pytest -m deploy
```
