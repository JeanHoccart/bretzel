"""Default theme for the ``ui.notification`` toast helper.

Notification is the only feedback component whose visible DOM is
managed by the runtime (``bretzel/runtime/_src/09_notification.js``)
rather than Python — there's no ``Component`` to mount, no render()
to call. Le runtime possède le per-toast chrome.

⚠️ Il y a **SIX** piles, pas quatre — ``top``/``bottom`` × ``left``/
``center``/``right`` (cf. ``positions`` plus bas). Et ce n'est pas le
runtime qui les « possède » : leur squelette HTML est généré en Python
(``notification.py::skeleton_html``) et injecté dans ``<body>`` par le
shell **à chaque rendu de page**, donc présent dès le premier paint. Le
runtime ne fait que pousser des données dans le scope.

To keep the styling source-of-truth in Python (Tailwind JIT scans
``.py`` files for class literals ; the app theme module + per-app
overrides apply uniformly), this theme dict is exposed to the
runtime via :func:`runtime_payload` and injected into the shell as
``window.$bz_theme.notification`` on every full page load. The JS
reads from there instead of carrying its own hardcoded maps.

Four variants — ``info`` / ``success`` / ``warning`` / ``error`` —
mirror the Alert family. The notification's API uses ``variant=``
rather than ``color=`` because the JIT constraint forbids dynamic
``bg-{color}/10`` substitution at runtime ; the four variants are
the pre-compiled set the framework ships. App developers can
override individual entries in the theme to customise the look or
add app-specific variants — Tailwind picks them up at the next
rebuild because the strings still live in ``.py`` files.
"""

from __future__ import annotations

from typing import Any

# ───────────────────────────────────────────────────────────────────
# Theme dict — directly JSON-serialisable for the shell injection.
# ───────────────────────────────────────────────────────────────────

NOTIFICATION_THEME: dict[str, Any] = {
    # Rich-tint chrome — the "colourful tasteful" idiom (Linear /
    # Vercel / Mantine soft). Toasts sit ABOVE existing content for
    # ~4s, so the fill must be OPAQUE, not translucent : ``bg-{c}/20``
    # (opacity) would let the content underneath bleed through the
    # missing 80%. Instead we ``color-mix`` an OPAQUE blend — 20% of
    # the semantic hue into 80% ``--color-surface`` — so the toast
    # reads coloured-at-a-glance yet fully hides whatever is behind
    # it. The blend tracks light/dark automatically (``--color-surface``
    # swaps). Legibility is kept by neutral body text (``text-text``)
    # over the soft wash, with the colour concentrated in the /40
    # tinted border and the icon + title accents.
    "variants": {
        "info":    "bg-[color-mix(in_oklab,var(--color-info)_20%,var(--color-surface)_80%)] border-info/40 text-text",
        "success": "bg-[color-mix(in_oklab,var(--color-success)_20%,var(--color-surface)_80%)] border-success/40 text-text",
        "warning": "bg-[color-mix(in_oklab,var(--color-warning)_20%,var(--color-surface)_80%)] border-warning/40 text-text",
        "error":   "bg-[color-mix(in_oklab,var(--color-error)_20%,var(--color-surface)_80%)] border-error/40 text-text",
    },
    # Icon + title accent classes per variant. The icon and title
    # get this on top of the root chrome so they read distinctly.
    "accents": {
        "info":    "text-info",
        "success": "text-success",
        "warning": "text-warning",
        "error":   "text-error",
    },
    # Iconify glyph names (lucide set) per variant. Used when the
    # caller doesn't pass an explicit ``icon=``.
    "icons": {
        "info":    "info",
        "success": "circle-check",
        "warning": "triangle-alert",
        "error":   "octagon-x",
    },
    # Anchor classes for each toast stack position. Built into the
    # outer ``<div class="fixed z-50 ...">`` of each corner stack.
    "positions": {
        "top-right":     "top-4 right-4",
        "top-center":    "top-4 left-1/2 -translate-x-1/2",
        "top-left":      "top-4 left-4",
        "bottom-right":  "bottom-4 right-4",
        "bottom-center": "bottom-4 left-1/2 -translate-x-1/2",
        "bottom-left":   "bottom-4 left-4",
    },
    # Slot classes that don't depend on variant — toast root chrome
    # (excluding the bg/border/text from variants), icon wrapper,
    # content stack, title, message, dismiss button. Centralising
    # them here makes per-app tweaks possible without touching the
    # runtime JS.
    "slots": {
        # No animation classes here — the enter / leave keyframes live in
        # the shell (``_NOTIFICATION_ANIM_STYLE``) and are applied via
        # ``bz-toast-enter`` / ``bz-toast-leave`` in ``notification.py``.
        # ``border`` gives the 1px stroke on all sides ; its colour comes
        # from the variant string (``border-{c}/40``) merged on top.
        "root": (
            "pointer-events-auto flex items-center gap-3 "
            "rounded-box border-(length:--bz-stroke) px-4 py-3 shadow-lg"
        ),
        "icon": (
            "shrink-0 flex items-center justify-center leading-none"
        ),
        "content": (
            "flex-1 flex flex-col gap-0.5 min-w-0 justify-center"
        ),
        "title": "font-semibold text-sm leading-tight",
        "message": "text-sm leading-snug break-words",
        "dismiss": (
            "shrink-0 inline-flex items-center justify-center "
            "rounded-selector p-1 text-text/60 hover:bg-text/5 "
            "hover:text-text transition-colors"
        ),
        # Outer stack container (the ``fixed`` corner wrapper). The
        # position class is appended at runtime based on the toast's
        # ``position`` field.
        "stack_outer": "fixed z-50 pointer-events-none",
        # Inner column inside the stack — caps width so toasts don't
        # blow past the viewport on mobile.
        "stack_inner": (
            "flex flex-col gap-2 w-80 max-w-[calc(100vw-2rem)]"
        ),
    },
    # Neutral fallback chrome when the runtime is asked for an
    # unknown variant (shouldn't happen with the strict Python API,
    # but defensive against drift between the two sides).
    "neutral": "bg-text/5 border-text/40 text-text",
}


# Canonical list of the variants the public API accepts. Kept in
# sync with ``NOTIFICATION_THEME["variants"]`` keys — the helper
# validates against this so a typo surfaces immediately.
VARIANTS: tuple[str, ...] = tuple(NOTIFICATION_THEME["variants"].keys())


def runtime_payload() -> dict[str, Any]:
    """Return the theme dict in the exact shape the runtime JS expects.

    The shell injects this as ``window.$bz_theme.notification`` on
    every full page load, before ``runtime.js`` defers itself. The
    JS module reads from there and never carries its own copy of
    the class strings.
    """

    return NOTIFICATION_THEME
