"""``Screen`` — current viewport shape, read server-side from a cookie.

Unlike ``ColorScheme`` / ``LiveConnection`` (framework-owned *ClientStates*, read as
reactive bindings), ``Screen`` is **server-authoritative** : it reads the
``bz_screen`` cookie off the active request and exposes plain Python bools, so
an app branches its layout with a real ``if`` — no ``@refreshable`` needed ::

    from bretzel import Screen, layout, ui

    @layout
    def shell() -> None:
        if Screen().is_mobile:
            with ui.vstack():
                topbar()
                ui.outlet()
        else:
            with ui.hstack():
                ui.sidebar(...)
                ui.outlet()

Why a cookie and not CSS : the branch runs in *Python on the server*, so the
server must know the viewport at render time — the one client→server channel
available then is a cookie, written pre-paint by the boot script
(``render/shell.py``) from ``matchMedia``. This is the escape hatch for a
**structural** nav swap (sidebar ⇆ topbar : two different trees CSS can't
exchange cleanly) ; ordinary responsive spacing / hiding stays in Tailwind
(``md:`` / ``max-md:``), instant and roundtrip-free.

There is deliberately **no resize listener** : the layout never re-arranges
under the user's fingers as the window moves. The correction is load-time —
whenever the cookie disagrees with the viewport (a brand-new visitor, or a
window resized between two loads) the boot script spends one pre-paint reload
and the next render is right.

That correction is available on *every* load, not once per tab : the anti-loop
flag is consumed by the load it guards (cf.
``render/shell.py::_screen_boot_script``). So crossing the breakpoint costs a
single navigation, in both directions, indefinitely.

A **boosted** navigation corrects too : ``hx-boost`` swaps only
``[data-bz-outlet]``, so this ``if`` would otherwise keep painting the previous
shape forever. ``_src/05_bridge.js`` therefore re-syncs before a boosted GET and
hands the navigation back to the browser when the shape changed — a full load
rebuilds the layout. Cf. ``.claude/bretzel/screen-responsive-nav.md``.

Cookie wire format : ``bz_screen = "{mobile},{touch}"`` where each flag is
``"1"`` / ``"0"``, e.g. ``"1,0"`` = mobile, fine-pointer. Missing or malformed
→ desktop / non-touch.
"""

from __future__ import annotations

from bretzel.runtime.protocol import SCREEN_COOKIE


def _parse_cookie(raw: str) -> tuple[bool, bool]:
    """Parse ``"{mobile},{touch}"`` → ``(is_mobile, is_touch)``.

    Anything unexpected (empty, wrong arity, non-``0/1`` tokens) degrades to
    ``(False, False)`` — desktop, non-touch — never raises. ``str.split`` never
    returns an empty list, so ``parts[0]`` is always safe.
    """
    parts = raw.split(",")
    is_mobile = parts[0] == "1"
    is_touch = len(parts) > 1 and parts[1] == "1"
    return is_mobile, is_touch


class Screen:
    """Per-request viewport shape read from the ``bz_screen`` cookie.

    ``is_mobile`` — viewport is at / below the app's ``mobile_breakpoint``.
    ``is_touch``  — the primary pointer is coarse (touch), independent of width.

    Both are plain bools, resolved once at construction. Constructing ``Screen``
    outside a render context (e.g. a background task) yields the desktop,
    non-touch default rather than raising.
    """

    __slots__ = ("is_mobile", "is_touch")

    def __init__(self) -> None:
        # Deferred import : ``render.context`` is same-layer, kept function-
        # local to avoid any import-order coupling.
        from bretzel.render.context import current_context

        raw = ""
        try:
            request = current_context().request
            cookies = getattr(request, "cookies", None) or {}
            raw = cookies.get(SCREEN_COOKIE, "")
        except RuntimeError:
            # No active render context → safe desktop fallback.
            raw = ""
        self.is_mobile, self.is_touch = _parse_cookie(raw)
