"""``ColorScheme`` — current color mode as a framework-owned ClientState.

``ColorScheme`` is **internal to Bretzel** : apps don't instantiate it,
they just call the class-level helpers to drive it from whatever UI they
like (a single cycling button, a segmented control, a select, three
icons, …). The framework guarantees the state exists in the browser :

- the FOUC script (``bretzel/render/shell.py``) applies the initial
  ``.dark`` class from localStorage before first paint ;
- the runtime (``bretzel/runtime/_src/00_index.js`` boot) always
  registers the ``local`` persistence adapter, seeds the default, and
  runs the effect that keeps ``<html>.dark`` in sync **live** — on every
  mode change AND on OS-preference change while ``mode == "system"``.

So the app never needs a ``scheme = ColorScheme()`` line ::

    from bretzel.theme import ColorScheme

    def shell() -> None:
        # explicit set — wire onto a select / button group / icons
        ui.icon_button("sun",     on_click=ColorScheme.set("light"))
        ui.icon_button("moon",    on_click=ColorScheme.set("dark"))
        ui.icon_button("monitor", on_click=ColorScheme.set("system"))
        # or a plain 2-state toggle
        ui.icon_button("sun-moon", on_click=ColorScheme.toggle())

Three canonical modes :

===========  ==========================================================
``mode``     effect on the page
===========  ==========================================================
``"light"``  never dark
``"dark"``   always dark
``"system"`` follows the OS ``prefers-color-scheme``, live
===========  ==========================================================
"""

from __future__ import annotations

from bretzel.state import field
from bretzel.state.scopes.client import ClientState


class ColorScheme(ClientState, persist="local"):
    """Framework-owned color mode (singleton via the ``default`` key).

    ``mode`` is a free-form string — ``"light"`` / ``"dark"`` / ``"system"``
    are the canonical values the FOUC script and the runtime effect
    understand. ``"auto"`` is accepted as a legacy alias of ``"system"``.
    Apps can still push a custom value via :meth:`set` and wire their own
    effect if they need more than the built-in three.
    """

    mode: str = field(default='system')

    # ── Mutation helpers — return client source for ``on_click=`` ─────────
    #
    # Class-level on purpose : the coder drives the framework's singleton
    # without ever instantiating it (``ColorScheme.set("dark")``). Under
    # the hood they resolve the ``default`` instance from the active
    # registry and read its ``mode`` binding — so they MUST be called
    # inside a render scope (which every ``on_click=`` value is). Calling
    # them outside a render crashes loudly, by design : they only make
    # sense as the value of a component event prop.

    @classmethod
    def set(cls, value: str) -> str:
        """Set ``mode`` to ``"light"`` / ``"dark"`` / ``"system"`` (or any
        custom string an app effect understands)."""
        return cls().mode.set(value)

    @classmethod
    def toggle(cls) -> str:
        """Flip the page between light and dark — contre CE QU'ON VOIT.

        Le bascule lit l'état RÉSOLU (``$bz._isDark()``, la fonction que
        le runtime utilise lui-même pour peindre ``<html>.dark``) et non
        le jeton stocké. Partir de ``"system"`` mène donc à ``"light"``
        sur un OS sombre, et à ``"dark"`` sur un OS clair : le premier
        clic change toujours quelque chose à l'écran.

        ⚠️ Il a comparé le JETON jusqu'au 2026-09-04
        (``mode === 'dark' ? 'light' : 'dark'``), et ça se défendait par
        écrit — « strictement à deux états ». Mais un utilisateur en
        ``"system"`` sur un OS sombre voyait son premier clic écrire
        ``"dark"``, qui est *déjà* ce qui est peint : le contrôle ne
        faisait rien une fois sur deux. Rapporté comme « le bouton ne
        marche pas ». Mesuré sur les deux apps de démo.

        Il reste à deux états : après un clic, ``mode`` vaut
        ``"light"`` ou ``"dark"``, et on ne revient pas dans
        ``"system"``. Pour offrir les trois, câblez :meth:`set` sur trois
        entrées — ce que font ``examples/playground`` et
        ``examples/docs``.
        """
        path = cls().mode.binding_path()
        return f"{path} = $bz._isDark() ? 'light' : 'dark'"
