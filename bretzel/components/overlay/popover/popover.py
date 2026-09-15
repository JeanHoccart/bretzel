"""``Popover`` — anchored floating panel.

Composition pattern : pass the trigger as ``trigger=`` (any
component, typically a button or an icon button), put the panel
content as children inside the ``with`` block ::

    with ui.popover(trigger=ui.icon_button("info"), position="bottom"):
        ui.text("Some helpful explanation here.", size="sm")

Open / close — the framework's universal contract :

  ``open=`` accepts the same three shapes every reactive prop does :
  literal bool (auto-suffisant via local ``bz-data``), server-resolved
  value, or a :class:`ClientBinding` (live two-way reactive — the
  panel reads the binding path, the trigger and dismiss paths write
  to it via standard ``binding.set(value)`` / ``binding.toggle()``).
  No popover-specific helpers ; same primitive as every other
  reactive prop in the framework.

Wiring (shared ``base/_wiring.py``) :

- positioning is owned by ``$bz.helpers.floating`` — the panel's
  ``bz-effect`` attaches it on open (4 sides × 3 alignments, main-axis
  flip + cross-axis clamp), no static positioning classes needed.
- click-outside + Escape dismiss are registered once at mount via
  ``$bz.helpers.clickOutside`` / ``escapeKey`` (``bz-init``).

The panel has no arrow — an anchored card reads fine without one, and
the floating helper already offsets it 6px off the trigger.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import install_open_close_toggle
from bretzel.components.overlay._anchored import render_anchored_overlay
from bretzel.components.overlay.popover.theme import POPOVER_THEME
from bretzel.core.tree import Element


class Popover(Component):
    """Anchored floating panel toggled by a trigger element."""

    THEME: ClassVar[dict[str, Any]] = POPOVER_THEME
    THEME_KEY: ClassVar[str] = "popover"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("open",)
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("open", "close", "toggle")
    EVENTS: ClassVar[tuple[str, ...]] = ("open", "close")
    # ``open`` AND ``close`` both fire on the root, so a single popover can
    # wire on_open + on_close to the server (the second rides a hidden
    # carrier — cf. ``Component.ALLOW_MULTI_SERVER_EVENTS``).
    ALLOW_MULTI_SERVER_EVENTS: ClassVar[bool] = True

    open: Any = reactive_prop(default=False, emit_attr=False, writes=True)
    # ``auto`` = best-fit (``$bz.helpers.floating`` picks the roomiest
    # side that fits) ; pin a side per-popover to override.
    position: str = reactive_prop(default="auto", emit_attr=False)
    align: str = reactive_prop(default="center", emit_attr=False)
    dismissible: bool = reactive_prop(default=True, emit_attr=False)

    def __init__(
        self,
        *,
        trigger: Component | None = None,
        open: Any = None,
        position: str | None = None,
        align: str | None = None,
        dismissible: bool | None = None,
        on_open: Callable[..., Any] | str | None = None,
        on_close: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Forward direct : le socle drope les kwargs reactive None (garde le defaut).
        super().__init__(
            open=open,
            position=position,
            align=align,
            dismissible=dismissible,
            on_open=on_open,
            on_close=on_close,
            **kwargs,
        )
        # Detach the trigger from the active parent stack so it
        # doesn't auto-register as an unrelated sibling — same pattern
        # as IconButton's icon slot.
        self._trigger: Component | None = Component.adopt_slot(trigger)
        # API impérative write-only ``.open()`` / ``.close()`` /
        # ``.toggle()`` — installée en attributs d'instance (shadow le
        # descripteur ``open``) par le helper base, identique sur les 4
        # overlays open-driven. Cf. `imperative-api.md`.
        install_open_close_toggle(self)


    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        return render_anchored_overlay(
            self,
            slots=self._resolved_theme().get("slots", {}),
            role="dialog",
            haspopup="dialog",
            default_align="center",
        )
