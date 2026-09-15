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
        """Assez de config pour que les actions soient SIGNÉES.

        ``RenderContext._action_key`` lit ``app.config._action_key`` ; sans
        elle, ``register_action`` rend une signature vide et les
        ``hx-post`` sortent sans ``data-bz-sig``. C'était sans conséquence
        tant que personne ne regardait — et ça a cessé de l'être le
        2026-08-27, quand le bridge s'est mis à REFUSER tout POST sans
        porteur de signature (une action détachée par un morph partait
        sinon nue et rechargeait la page entière).

        Depuis, un montage navigateur bâti sur ``render_isolated`` produit
        des boutons qu'aucun clic ne peut faire partir, et son rouge
        accuse le composant. Mesuré sur ``probe_overlay_dual_event``, dont
        les deux porteurs sortaient avec ``data-bz-ts`` et sans
        ``data-bz-sig``.

        La clé est FIXE et publique : ce rig ne protège rien, il reproduit
        une forme. Ce que la docstring de :func:`render_isolated` promet
        déjà — « behaves like in production » — et qui n'était pas vrai
        pour les actions.
        """
        return _StubConfig()


class _StubConfig:
    """La part de ``BretzelConfig`` que la couche rendu lit vraiment."""

    #: Clé de démonstration, jamais un secret : les probes servent leur
    #: HTML depuis un fichier, il n'y a pas de serveur pour vérifier.
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
