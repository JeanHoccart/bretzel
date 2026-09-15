"""Dedicated e2e fixture — the seven storage scopes, side by side.

This is NOT ``examples/counter`` : it is a stable, test-owned app whose
only job is to exercise the contracts ``tests/e2e/test_counter.py``
asserts on. Migrated off the example on 2026-08-16, for the same reason
``todo_app.py`` was on 2026-07-14 — a demo is documentation, it must stay
free to change for demo reasons, and a framework test that breaks when a
demo is improved says nothing about the framework.

The coupling was not theoretical : ``examples/counter/counter.py`` carries
7 commits and was touched the very day of this migration.

Contracts covered, one row each — the point is that all seven behave
DIFFERENTLY, and only a real browser can tell them apart :

- **Module variable** — a plain Python global. Server round-trip, mutated
  by the handler, redrawn by an explicit ``refresh``.
- **AppState** — process-wide, so it is shared across browser CONTEXTS
  (two independent users see the same number).
- **SessionState** — keyed by the ``Bretzel_session`` cookie : survives a
  reload, isolated between contexts.
- **PageState** — bound to one rendered page, so a reload starts over.
- **ClientState** ×3 (``memory`` / ``session`` / ``local``) — mutated by
  the runtime in the browser with **zero POST**, and differing only in
  what survives a reload.

Structural contract with the test helpers — do not reshape casually.
``_row()`` finds a row by its EXACT label text and walks to the parent
node, ``_value_span()`` matches ``span.text-3xl.font-bold`` inside it, and
``_click_button()`` matches buttons by accessible name. So each row must
stay : label · subtitle · value · (−, Reset, +), all under one parent.
"""

from __future__ import annotations

from bretzel import Bretzel, page, refresh, refreshable, ui
from bretzel.state import AppState, ClientState, PageState, SessionState, field

# ───────────────────────────────────────────────────────────────────────────
# Server-side stores (Python authority)
# ───────────────────────────────────────────────────────────────────────────

# Reset between tests by the ``reset_server_globals`` autouse fixture —
# it lives in the process, not in a backend, so nothing else clears it.
global_count: int = 0


class AppCounter(AppState):
    """Process-wide : every visitor and every worker shares this row."""

    count: int = field(default=0, merge="add")


class SessionCounter(SessionState):
    """Scoped to the visitor's cookie."""

    count: int = field(default=0)


class PageCounter(PageState):
    """Scoped to one rendered page — never persisted.

    Consequence the test asserts : the value resets between requests, so a
    click always renders exactly ``1``.
    """

    count: int = field(default=0)


# ───────────────────────────────────────────────────────────────────────────
# Client-side stores (browser authority, zero round-trip)
# ───────────────────────────────────────────────────────────────────────────


class MemoryCounter(ClientState, persist="memory"):
    count: int = field(default=0)


class SessionStoreCounter(ClientState, persist="session"):
    count: int = field(default=0)


class LocalCounter(ClientState, persist="local"):
    count: int = field(default=0)


app = Bretzel(
    secret_key="e2e-counter-fixture-secret",
    title="e2e fixture · counter",
    mode="dev",
)


# ── Refreshable displays for the server-side rows ──────────────────────────


@refreshable
def display_global() -> None:
    ui.text(str(global_count), size="3xl", weight="bold")


@refreshable(deps=[AppCounter])
def display_app() -> None:
    ui.text(str(AppCounter().count), size="3xl", weight="bold")


@refreshable(deps=[SessionCounter])
def display_session() -> None:
    ui.text(str(SessionCounter().count), size="3xl", weight="bold")


@refreshable(deps=[PageCounter])
def display_page() -> None:
    ui.text(str(PageCounter().count), size="3xl", weight="bold")


# ── Handlers ───────────────────────────────────────────────────────────────
#
# The module-variable row is the only one needing an explicit ``refresh``:
# a plain global has no ``deps`` for the framework to track.


def global_inc() -> None:
    global global_count
    global_count += 1
    refresh(display_global)


def global_dec() -> None:
    global global_count
    global_count -= 1
    refresh(display_global)


def global_reset() -> None:
    global global_count
    global_count = 0
    refresh(display_global)


def app_inc() -> None:
    AppCounter().count += 1


def app_dec() -> None:
    AppCounter().count -= 1


def app_reset() -> None:
    AppCounter().count = 0


def session_inc() -> None:
    SessionCounter().count += 1


def session_dec() -> None:
    SessionCounter().count -= 1


def session_reset() -> None:
    SessionCounter().count = 0


def page_inc() -> None:
    PageCounter().count += 1


def page_dec() -> None:
    PageCounter().count -= 1


def page_reset() -> None:
    PageCounter().count = 0


# ── Rows ───────────────────────────────────────────────────────────────────


def server_row(label, subtitle, display_fn, inc, dec, reset) -> None:
    """One server-driven row : click → POST → handler → the display swaps."""
    with ui.vstack(gap="sm", align="center"):
        ui.text(label, size="lg", weight="semibold")
        ui.text(subtitle, size="sm", color="muted")
        display_fn()
        with ui.hstack(gap="sm"):
            ui.button("−", on_click=dec, variant="outline")
            ui.button("Reset", on_click=reset, variant="ghost")
            ui.button("+", on_click=inc)


def client_row(label, subtitle, count_binding) -> None:
    """One client-only row : the binding methods emit inline JS, no POST.

    ``count_binding.increment()`` returns client source that the runtime
    runs on click ; the bound display re-evaluates on its own. The test
    asserts the network stays silent — that is the whole point of this row.
    """
    with ui.vstack(gap="sm", align="center"):
        ui.text(label, size="lg", weight="semibold")
        ui.text(subtitle, size="sm", color="muted")
        ui.text(count_binding, size="3xl", weight="bold")
        with ui.hstack(gap="sm"):
            ui.button("−", on_click=count_binding.decrement(), variant="outline")
            ui.button("Reset", on_click=count_binding.set(0), variant="ghost")
            ui.button("+", on_click=count_binding.increment())


@page("/")
def home() -> None:
    # ``ClientState`` must be constructed inside the render scope so
    # attribute access returns the ``ClientBinding`` the runtime wires.
    mem = MemoryCounter()
    sess = SessionStoreCounter()
    local = LocalCounter()

    with ui.vstack(gap="xl", align="center"):
        ui.text("Counter — every scope", size="2xl", weight="bold")

        server_row(
            "Module variable",
            "Python global ; resets on server restart",
            display_global, global_inc, global_dec, global_reset,
        )
        server_row(
            "AppState",
            "framework-typed process-wide singleton",
            display_app, app_inc, app_dec, app_reset,
        )
        server_row(
            "SessionState",
            "scoped to your Bretzel_session cookie",
            display_session, session_inc, session_dec, session_reset,
        )
        server_row(
            "PageState",
            "scoped to this rendered page ; F5 resets",
            display_page, page_inc, page_dec, page_reset,
        )

        client_row(
            'ClientState (persist="memory")',
            "in RAM ; lost when you close the tab",
            mem.count,
        )
        client_row(
            'ClientState (persist="session")',
            "sessionStorage ; cleared on tab close, kept on reload",
            sess.count,
        )
        client_row(
            'ClientState (persist="local")',
            "localStorage ; survives tab close and a server reset",
            local.count,
        )


app.include(__name__)
