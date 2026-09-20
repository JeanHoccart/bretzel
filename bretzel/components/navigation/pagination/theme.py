"""Default :class:`Pagination` theme.

The visual language — rounded squares, subtle hover, scale-up on the
active page — is the design-system identity.

Slots :
- ``root``     : the ``<nav>`` flex container, items + ellipsis spaced
- ``item``     : the page-number / prev / next buttons
- ``active``   : extra classes layered on the currently-selected page
- ``ellipsis`` : the "…" pseudo-buttons (non-interactive)
- ``nav``      : the prev / next chevron buttons (extra padding)

Per-size dicts carry one entry per slot that needs its own dimension —
``item`` and ``nav``. **Not** ``ellipsis``: that layer is composed ON TOP
of ``item``, which already carries the size.

⚠️ The ``active`` / ``ellipsis`` layers must NEVER repeat a token of
``item``. They leave as ``bz-class`` on the same ``<button>`` as the
static layer, and the runtime only removes what the expression stops
producing: a shared token is removed from the static ``class=`` at the
same time. ``ellipsis`` re-declared ``flex items-center justify-center``
+ ``w-10 text-sm`` — the button that stopped being an ellipsis collapsed
from 40 px to 8 px, its height intact. The runtime now protects its
baseline (``02_directives.js``), and
``test_bz_class_never_repeats_static_tokens`` keeps the rule on the theme
side.
"""

from __future__ import annotations

from typing import Any

PAGINATION_THEME: dict[str, Any] = {
    "slots": {
        "root": (
            "flex items-center justify-center gap-1.5 select-none"
        ),
        "item": (
            "flex items-center justify-center rounded-field font-medium "
            "transition-all duration-200 ease-out cursor-pointer "
            "not-disabled:hover:bg-text/5 not-disabled:active:scale-95 "
            "focus-visible:ring-2 focus-visible:ring-offset-2 "
            "focus-visible:ring-offset-background "
            "focus-visible:ring-(--bz-focus) "
            "disabled:opacity-50 disabled:cursor-not-allowed"
        ),
        "active": (
            "bg-(--bz-solid) text-(--bz-on-solid) shadow-sm scale-110 z-10 "
            "not-disabled:hover:!bg-(--bz-solid)/80"
        ),
        # Composed on top of ``item``: no flex/centring and no size here.
        "ellipsis": "text-muted pointer-events-none",
        "nav": "text-text/70 not-disabled:hover:text-(--bz-text)",
    },
    "sizes": {
        "xs": {
            "item": "w-7 h-7 text-[10px]",
            "nav": "p-1",
        },
        "sm": {
            "item": "w-8 h-8 text-xs",
            "nav": "p-1.5",
        },
        "md": {
            "item": "w-10 h-10 text-sm",
            "nav": "p-2",
        },
        "lg": {
            "item": "w-12 h-12 text-base",
            "nav": "p-2.5",
        },
        "xl": {
            "item": "w-14 h-14 text-lg",
            "nav": "p-3",
        },
    },
}
