"""Default :class:`Banner` theme.

Full-width status strip — visually distinct from :class:`Alert`
(which is inline, rounded, padded). Banner spans edge-to-edge of
its parent so it reads as a page-level chrome announcement
(trial expiring, maintenance window, new feature toast).

Slots :
- ``root``      : the full-width strip
- ``icon`` : the leading icon wrapper
- ``content``   : the flex-1 column holding title + message
- ``title``     : optional bold headline
- ``message``   : the body text
- ``actions``   : the right-aligned action slot (button(s))
- ``close``     : the dismiss × button
"""

from __future__ import annotations

from typing import Any

BANNER_THEME: dict[str, Any] = {
    "slots": {
        # Full-width row — no border-radius, edge-to-edge by default
        # so the Banner looks anchored to its container. Apps that
        # want a rounded Banner inside a Card can override via
        # ``classes="rounded-box"``.
        "root": (
            "relative flex items-center gap-3 w-full "
            "px-4 py-3 "
            "border-l-(length:--bz-stroke-accent)"
        ),
        "icon": "shrink-0 self-start mt-0.5",
        "content": "flex-1 min-w-0 flex flex-col gap-0.5",
        "title": "font-semibold leading-tight",
        "message": "leading-relaxed",
        "actions": "shrink-0 inline-flex items-center gap-2 ms-auto",
        "close": (
            "shrink-0 inline-flex items-center justify-center "
            "rounded-selector p-1 cursor-pointer "
            "outline-none focus-visible:ring-2 "
            "focus-visible:ring-(--bz-focus) "
            # ``/80`` at rest, full colour on hover — the same
            # pair Badge writes on its three close buttons. A
            # dismiss affordance is muted, never invisible.
            "text-(--bz-text-muted) hover:text-(--bz-text) "
            "hover:bg-(--bz-bg) "
            "transition-colors duration-100"
        ),
    },
    # Color-flavoured backgrounds — softer than Alert's so the banner
    # doesn't overwhelm the page chrome above it. A ``/8`` wash for
    # the wash and a coloured left bar for the semantic accent.
    "variants": {
        "info":    {"root": "bg-info/8 border-info text-info"},
        "success": {"root": "bg-success/8 border-success text-success"},
        "warning": {"root": "bg-warning/8 border-warning text-warning"},
        "error":   {"root": "bg-error/8 border-error text-error"},
        # Neutral / muted variants for generic info that doesn't need
        # a semantic flag.
        "muted":   {"root": "bg-text/5 border-text/30 text-text"},
        "primary": {"root": "bg-primary/8 border-primary text-primary"},
    },
    "sizes": {
        "sm": {"root": "py-2 text-xs", "title": "text-sm"},
        "md": {"root": "py-3 text-sm", "title": "text-base"},
        "lg": {"root": "py-4 text-base", "title": "text-lg"},
    },
    # Auto-icon par couleur sémantique (comme Alert's ``color_icons``) —
    # dans le thème pour être overridable via ``Theme(components=…)``, pas
    # une constante module figée. ``muted`` / ``primary`` n'ont pas d'icône.
    "color_icons": {
        "info":    "info",
        "success": "check-circle-2",
        "warning": "alert-triangle",
        "error":   "octagon-alert",
    },
}
