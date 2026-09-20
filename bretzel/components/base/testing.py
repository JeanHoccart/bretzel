"""Test-only helpers for component authors.

Phase 1 ships a minimal surface — :func:`render_isolated` builds a
self-contained :class:`RenderContext` so a unit test can construct
components without spinning up the full server stack.

Imported under ``bretzel.components.base.testing`` rather than mixed
into the main API so production code doesn't accidentally depend on
test fixtures.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from bretzel.render.context import RenderContext, use_context


class _StubApp:
    """Fake :class:`bretzel.render.types.BretzelApp` used by tests.

    Provides the structural interface the render layer reads ; every
    field is empty / inert so a test that doesn't exercise persistence,
    routing or theming gets a clean blank slate.
    """

    def __init__(self, *, theme: Any | None = None, debug: bool = True) -> None:
        self._theme = theme
        self._debug = debug
        self._pages: list[Callable[..., Any]] = []
        self._realtime: dict[str, Any] = {}
        self._error_handlers: dict[int, Callable[..., Any]] = {}

    @property
    def theme(self) -> Any:
        return self._theme

    @property
    def state_backend(self) -> Any:
        return None

    @property
    def debug(self) -> bool:
        return self._debug

    @property
    def config(self) -> Any:
        """Enough config for the actions to be SIGNED.

        ``RenderContext._action_key`` reads ``app.config._action_key``;
        without it, ``register_action`` returns an empty signature and
        the ``hx-post`` come out with no ``data-bz-sig``. That was
        inconsequential as long as nobody looked — and it stopped being
        so on 2026-08-27, when the bridge started REFUSING any POST with
        no signature carrier (an action detached by a morph otherwise
        left bare and reloaded the whole page).

        Since then, a browser mount built on ``render_isolated`` produces
        buttons no click can make fire, and its red accuses the
        component. Measured on ``probe_overlay_dual_event``, whose two
        carriers came out with ``data-bz-ts`` and without
        ``data-bz-sig``.

        The key is FIXED and public: this rig protects nothing, it
        reproduces a shape. What :func:`render_isolated`'s docstring
        already promises — "behaves like in production" — and which was
        not true for the actions.
        """
        return _StubConfig()


class _StubConfig:
    """The part of ``BretzelConfig`` the render layer really reads."""

    #: A demonstration key, never a secret: the probes serve their HTML
    #: from a file, there is no server to verify.
    _action_key = b"bretzel-test-rig-action-key"


@contextmanager
def render_isolated(
    *,
    theme: Any | None = None,
    debug: bool = True,
) -> Iterator[RenderContext]:
    """Open an isolated render context for unit tests.

    Usage ::

        with render_isolated() as ctx:
            btn = Button("Save", color="primary")
            assert btn.id.startswith("root_button_")

    The context is bound on the active task via the standard
    :func:`bretzel.render.context.use_context` machinery, so anything
    inside the ``with`` block sees a real :class:`RenderContext` and
    behaves like in production. The yielded ``ctx`` lets the test
    inspect ``parent_stack`` / ``root_children`` / ``action_registry``
    after the fact.
    """
    ctx = RenderContext(app=_StubApp(theme=theme, debug=debug), request=object())
    with use_context(ctx):
        yield ctx


def panel_from_teleport(el: Any) -> Any:
    """Return an anchored overlay's panel from its teleport wrapper.

    Popover / Dropdown / Tooltip / SidebarFooter wrap their panel in a
    ``<template bz-teleport="body">`` (moved under ``<body>`` at runtime
    to clear ancestor clip / stacking traps). Tests that assert on the
    panel need to descend into that template. Falls back to the element's
    last child when no teleport wrapper is present.
    """
    for child in getattr(el, "children", ()):
        if getattr(child, "tag", None) == "template" and "bz-teleport" in (
            getattr(child, "attrs", {}) or {}
        ):
            return child.children[0]
    return el.children[-1]
