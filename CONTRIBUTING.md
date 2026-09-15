# Contributing to Bretzel

Bretzel is in alpha. Small, focused bug fixes and reports backed by a minimal
reproduction are the most useful contributions while the public API settles.

## Development setup

Requires Python 3.12 or 3.13.

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
python -m pytest
```

The default test command excludes the browser, end-to-end, probe and visual
audit suites. Their explicit commands are documented in `README.md` and
`pyproject.toml`.

Before proposing a change, run the smallest relevant test first, then:

```bash
python -m pytest
ruff check bretzel tests
lint-imports
```

## Pull requests

- Keep one behavioral change per pull request.
- Add a regression test for a bug fix.
- Preserve public API compatibility unless the change explicitly discusses an
  alpha-breaking change.
- Explain the user-visible reason for the change, not only its implementation.
- Do not commit generated caches, secrets, recordings, or local environments.

Use GitHub issues for public bugs and feature discussions. Report security
issues privately as described in `SECURITY.md`.
