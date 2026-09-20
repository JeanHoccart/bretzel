"""``Drawer`` — side-anchored sliding panel.

Same architecture as :class:`Dialog` — backdrop + escape + body
scroll lock + ``open=`` accepting the universal three shapes
(literal bool / server-resolved / ClientBinding) — but the panel
slides in from one of the four screen edges instead of centring.

Usage ::

    # Imperative — purely-visual overlay, no ClientState needed.
    with ui.drawer(title="Menu", side="left") as drw:
        ui.text("Sidebar content goes here.")
    ui.button("Open menu", on_click=drw.open())

    # Bound — when another component must read or react to the state.
    class UI(ClientState, persist="memory"):
        nav_open: bool = field(default=False)

    ui_state = UI()
    with ui.drawer(open=ui_state.nav_open, side="left", title="Menu"):
        ui.text("Sidebar content goes here.")

The implementation reuses the Dialog approach via the shared overlay
wiring (``base/_wiring.py``) : backdrop click to dismiss, escape
key, focus trap, scroll lock, imperative receivers are identical —
only the per-side layout (container alignment, panel border) differs.

The element stays MOUNTED: ``show_attrs`` sets ``data-open`` +
  ``data-bz-overlay``, and the anti-flash comes from the shell's
  ``[data-bz-overlay][data-open="false"]`` selector — not from a
  ``display:none`` prestamp;
slide-in animations are CSS-only — the theme owns them.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import install_open_close_toggle
from bretzel.components.overlay._modal import render_modal_overlay
from bretzel.components.overlay.drawer.theme import DRAWER_THEME
from bretzel.core.tree import Element


class Drawer(Component):
    """Side-anchored sliding panel."""

    THEME: ClassVar[dict[str, Any]] = DRAWER_THEME
    THEME_KEY: ClassVar[str] = "drawer"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("open",)
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("open", "close", "toggle")
    EVENTS: ClassVar[tuple[str, ...]] = ("open", "close")
    # ``open`` AND ``close`` both fire on the root, so a single drawer can
    # wire on_open + on_close to the server (the second rides a hidden
    # carrier — cf. ``Component.ALLOW_MULTI_SERVER_EVENTS``).
    ALLOW_MULTI_SERVER_EVENTS: ClassVar[bool] = True

    open: Any = reactive_prop(default=False, emit_attr=False, writes=True)
    title: str | None = reactive_prop(default=None, emit_attr=False)
    side: str = reactive_prop(default="right", emit_attr=False)
    # ``width`` clamps the panel's dimension perpendicular to its
    # anchor edge — width for ``left``/``right`` drawers, height for
    # ``top``/``bottom``. Naming aligned with Container / Dialog /
    # Popover for API consistency across overlays.
    width: str = reactive_prop(default="md", emit_attr=False)
    dismissible: bool = reactive_prop(default=True, emit_attr=False)
    persistent: bool = reactive_prop(default=False, emit_attr=False)

    def __init__(
        self,
        *,
        open: Any = None,
        title: str | None = None,
        side: str | None = None,
        width: str | None = None,
        dismissible: bool | None = None,
        persistent: bool | None = None,
        on_open: Callable[..., Any] | str | None = None,
        on_close: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            open=open,
            title=title,
            side=side,
            width=width,
            dismissible=dismissible,
            persistent=persistent,
            on_open=on_open,
            on_close=on_close,
            **kwargs,
        )
        # Write-only imperative API ``.open()`` / ``.close()`` /
        # ``.toggle()`` — installed as instance attributes (shadowing the
        # ``open`` descriptor) by the base helper, identical on the 4
        # open-driven overlays. Cf. `imperative-api.md`.
        install_open_close_toggle(self)


    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme = self._resolved_theme()
        sides = theme.get("sides", {})
        widths = theme.get("widths", {})

        side = self._reactive_values.get("side") or "right"
        width = self._reactive_values.get("width") or "md"
        side_cfg = sides.get(side, sides.get("right", {}))

        # ``width`` bounds the dimension PERPENDICULAR to the side: the
        # horizontal table for a left/right drawer (bounds the width),
        # the vertical one for top/bottom (bounds the height).
        width_axis = "horizontal" if side in ("left", "right") else "vertical"

        return render_modal_overlay(
            self,
            slots=theme.get("slots", {}),

            # ``closed`` slides the panel off its edge when it is
            # closed; open = no translation. It is the CSS that animates
            # the ``translate`` property (cf. the theme), the runtime
            # only toggles ``data-open``. The class is ALREADY complete
            # in the theme (``data-[open=false]:…``) — it cannot be
            # assembled here.
            panel_extra=(
                side_cfg.get("panel", ""),
                widths.get(width_axis, {}).get(width, ""),
                side_cfg.get("closed", ""),
            ),
            container_extra=(side_cfg.get("container", ""),),
        )
