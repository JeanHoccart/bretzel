"""Default :class:`Icon` theme.

``inline-flex shrink-0 align-middle``, and NO transition of its own: the
icon's colour is inherited (``currentColor``), so it follows the animation
of the component around it at that component's pace — 150 ms in a
button, 200 ms in a step chip. A transition here made it lag on its own
clock (150 ms inside a 200 ms state change, measured).
Sizing is via ``font-size`` because ``<iconify-icon>`` sizes itself in ``1em``.
Default colour ``current`` → the ``bz-c-current`` bridge, whose
``--bz-text`` is ``currentColor`` : the icon inherits its parent's text
colour unless ``color=`` overrides.

⚠️ The slot writes a STEP (``text-(--bz-text)``), set by the bridge class
the base layer stamps on the root (cf. :mod:`bretzel.theme.bridges`). The
difference is not cosmetic — a half-class assembled at render time is one
the Tailwind compiler never sees, so it has to be closed colour by
colour, whereas a step is a complete and literal class.
"""

from __future__ import annotations

from typing import Any

ICON_THEME: dict[str, Any] = {
    "slots": {
        "root": (
            "inline-flex shrink-0 justify-center items-center align-middle "
            "text-(--bz-text)"
        ),
    },
    "sizes": {
        "xs": "text-xs",
        "sm": "text-sm",
        "md": "text-lg",  # default — slightly bigger than text for readability
        "lg": "text-2xl",
        "xl": "text-4xl",
        "2xl": "text-6xl",
    },
    # Default Iconify set + style. Apps override at theme registration
    # time to swap the icon library globally.
    "set": "lucide",
    "style": None,  # Phosphor / Tabler can pass "bold" / "filled" etc.
}
