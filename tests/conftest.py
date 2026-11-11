"""How many processes a bare ``pytest`` uses — ``-n auto`` is in addopts.

Measured on 2026-11-03, fast suite, 14 cores: 10–13 min on one process,
3 min 21 s on 8, 5 min on 14 — past 8 the workers fight for the disk and
the imports, and every one re-pays the session fixtures (the playground's
pages, the source sweeps). Hence a ceiling, not the core count.

The heavy suites stay on ONE process unless asked (``-m audit -n 4``):
each test boots a server or a browser, and under load the probes fail
with « the server did not start within 30 seconds » — a symptom of the
machine, not of the code.
"""

from __future__ import annotations

import os

import pytest

#: Past this, the run gets slower (measured above).
_CEILING = 8

_HEAVY = ("e2e", "browser", "audit", "probes")


def pytest_xdist_auto_num_workers(config) -> int:
    markexpr = config.getoption("markexpr", "") or ""
    if any(marker in markexpr for marker in _HEAVY) and "not " not in markexpr:
        return 0
    return min(_CEILING, os.cpu_count() or 1)


@pytest.fixture(autouse=True)
def _bretzel_mode_is_put_back():
    """``BRETZEL_MODE`` as the test found it.

    ``bretzel dev`` (``cli/commands/project.run_project``) sets it to
    ``dev`` for the process, as it should for a real run. Called by a
    test, it stayed set for every test the same worker ran next: an app
    built without ``mode=`` became a dev app, and since dev mode answers
    only local names (``middleware/host.py``), a test reaching it by
    ``app.example.com`` got a 400 — red or green by test order
    (2026-11-07)."""
    before = os.environ.get("BRETZEL_MODE")
    yield
    if before is None:
        os.environ.pop("BRETZEL_MODE", None)
    else:
        os.environ["BRETZEL_MODE"] = before
