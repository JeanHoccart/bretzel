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

Wiring (shared ``base/``) :

- positioning is owned by ``$bz.helpers.floating`` — the panel's
  ``bz-effect`` attaches it on open (4 sides × 3 alignments ; its side,
  the opposite, then the others ; both axes clamped), no static positioning classes needed.
- click-outside + Escape dismiss are registered once at mount via
  ``$bz.helpers.clickOutside`` / ``escapeKey`` (``bz-init``).

The panel has no arrow — an anchored card reads fine without one, and
the floating helper already offsets it 6px off the trigger.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import reactive_prop
from bretzel.components.base.overlay_wiring import FLOATING_ALIGNS
from bretzel.components.overlay._anchored import render_anchored_overlay
from bretzel.components.overlay._base import AnchoredOverlay
from bretzel.components.overlay.popover.theme import POPOVER_THEME
from bretzel.core.tree import Element


class Popover(AnchoredOverlay):
    """Anchored floating panel toggled by a trigger element."""

    THEME: ClassVar[dict[str, Any]] = POPOVER_THEME
    THEME_KEY: ClassVar[str] = "popover"
    align: str = reactive_prop(default="center", emit_attr=False, steps=FLOATING_ALIGNS)

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        return render_anchored_overlay(
            self,
            slots=self._resolved_theme().get("slots", {}),
            role="dialog",
            haspopup="dialog",
            default_align="center",
        )
