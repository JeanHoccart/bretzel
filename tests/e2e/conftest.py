"""Shared fixtures for e2e tests : uvicorn server + Playwright page.

The server boots in a background thread once per session so the
suite runs in seconds rather than minutes. Each test gets a fresh
browser ``context`` so localStorage / sessionStorage / cookies are
isolated — no cross-test contamination.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest

# We import lazily to keep the rest of the test suite importable
# even when playwright isn't installed (pytest will just skip).
try:
    from playwright.sync_api import (
        Browser,
        BrowserContext,
        Page,
        Playwright,
        sync_playwright,
    )
except ImportError:  # pragma: no cover — handled at collection time
    Browser = BrowserContext = Page = Playwright = None  # type: ignore
    sync_playwright = None  # type: ignore


# Mark every test in this directory as ``e2e`` so the default fast
# suite (``pytest -m "not e2e"``) skips them. Set on collection.
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    e2e_marker = pytest.mark.e2e
    for item in items:
        if "tests/e2e" in str(item.fspath).replace("\\", "/"):
            item.add_marker(e2e_marker)


# ───────────────────────────────────────────────────────────────────────────
# Uvicorn fixtures — each boots a test-owned app from ``apps/`` on a free
# port. None of them boots an ``examples/`` app : a demo must stay free to
# change without breaking the framework's own suite.
# ───────────────────────────────────────────────────────────────────────────


def _free_port() -> int:
    """Pick a random free TCP port for the test server."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(host: str, port: int, timeout: float = 10.0) -> None:
    """Block until the port accepts connections, or raise."""
    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError as exc:
            last_err = exc
            time.sleep(0.05)
    raise TimeoutError(
        f"Server didn't become reachable on {host}:{port} within {timeout}s "
        f"(last error: {last_err!r})"
    )


def _boot_app(app: Any, host: str = "127.0.0.1") -> tuple[str, Any]:
    """Boot a Bretzel app on a free port via uvicorn in a daemon thread.

    Returns ``(base_url, server)`` ; the server has ``should_exit`` you
    can flip in fixture teardown. The loop dies with the test process
    in any case (daemon thread).
    """
    import uvicorn

    port = _free_port()
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
        lifespan="on",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_for_port(host, port, timeout=15.0)
    return f"http://{host}:{port}", server


@pytest.fixture(scope="session")
def server_url() -> Iterator[str]:
    """Dedicated counter fixture app on a free port for the whole session.

    NOT ``examples/counter`` — a demo is documentation and must stay free
    to change ; a framework test that breaks when a demo is improved says
    nothing about the framework. Repointed 2026-08-16, the last of the
    three. ``tests/consistency/test_e2e_owns_its_apps`` keeps it that way.
    """
    from tests.e2e.apps.counter_app import app

    base_url, server = _boot_app(app)
    yield base_url
    server.should_exit = True


@pytest.fixture(scope="session")
def todo_url() -> Iterator[str]:
    """Dedicated TODO fixture app on a free port for the whole session.

    NOT ``examples/todo`` — a stable, test-owned app so a demo-side
    refactor can never silently break the e2e suite again.
    """
    from tests.e2e.apps.todo_app import app

    base_url, server = _boot_app(app)
    yield base_url
    server.should_exit = True


@pytest.fixture(scope="session")
def kanban_url() -> Iterator[str]:
    """Dedicated board fixture app on a free port for the whole session.

    NOT ``examples/kanban`` — same rule as ``server_url`` above. The name
    stays ``kanban_url`` because that is what the test reads ; only the
    app behind it moved.
    """
    from tests.e2e.apps.board_app import app

    base_url, server = _boot_app(app)
    yield base_url
    server.should_exit = True


# ───────────────────────────────────────────────────────────────────────────
# Playwright fixtures — browser per session, context per test
# ───────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def playwright_instance() -> Iterator[Playwright]:
    if sync_playwright is None:
        pytest.skip("playwright is not installed")
    with sync_playwright() as pw:
        yield pw


@pytest.fixture(scope="session")
def browser(playwright_instance: Playwright) -> Iterator[Browser]:
    # Headless by default ; flip to ``headless=False`` for debugging.
    browser = playwright_instance.chromium.launch(headless=True)
    yield browser
    browser.close()


@pytest.fixture
def context(browser: Browser) -> Iterator[BrowserContext]:
    """Fresh browser context per test = isolated cookies + storage."""
    ctx = browser.new_context()
    yield ctx
    ctx.close()


@pytest.fixture
def page(context: BrowserContext) -> Iterator[Page]:
    page = context.new_page()
    yield page
    page.close()


# ───────────────────────────────────────────────────────────────────────────
# Per-test reset of process-wide server state
# ───────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_server_globals() -> None:
    """Module variable + AppState live in process memory ; reset
    between tests so each one starts with a clean 0-counter state."""
    from tests.e2e.apps import counter_app

    counter_app.global_count = 0

    # Reset the in-memory backend's app-scoped row, if present.
    backend = getattr(counter_app.app, "_state_backend", None)
    if backend is not None and hasattr(backend, "_data"):
        for key in list(backend._data.keys()):
            del backend._data[key]
    # Touch the class so any stale module-load instance is purged.
    _ = counter_app.AppCounter
