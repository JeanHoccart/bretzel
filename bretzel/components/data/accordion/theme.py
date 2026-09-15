"""Default :class:`Accordion` / :class:`AccordionItem` theme.

One opinionated structure : a wrapping border around the whole stack
with a thin divider between each item. No ``variant`` prop — callers who
need the gapped-card or borderless look override the ``root`` / ``item``
slots.

The active state is driven by a ``data-open`` attribute on the header
button, rendered statically server-side for initially-expanded items
and kept reactive via ``bz-attr:data-open``. Same SSR-first idiom Tabs
uses for ``data-selected`` — avoids the flash before the runtime hydrates.
"""

from __future__ import annotations

from typing import Any

ACCORDION_THEME: dict[str, Any] = {
    "slots": {
        # Root wrapper — flex column + the one opinionated frame : outer
        # border, rounded corners, ``overflow-hidden`` so the first / last
        # item's corners clip to the rounding. (Anchored overlay panels are
        # ``position: fixed`` at open time, never clipped by it.)
        "root": (
            "flex flex-col w-full "
            "border-(length:--bz-stroke) border-text/10 rounded-box overflow-hidden"
        ),
        # Per-item wrapper — a thin internal divider ; the last item
        # drops its bottom rule so it sits flush against the frame.
        "item": "border-b-(length:--bz-stroke) border-text/10 last:border-b-0",
        # Header button — common base : full-width clickable row,
        # left-aligned label + right-aligned chevron. Chevron rotates
        # 180° when the item is open via ``data-[open=true]:rotate-180``.
        "header": (
            "group flex w-full items-center justify-between gap-3 "
            "font-medium text-start "
            "transition-[color,background-color,border-color] "
            "duration-200 ease-out cursor-pointer outline-none "
            "focus-visible:ring-2 focus-visible:ring-offset-2 "
            "focus-visible:ring-offset-background "
            "focus-visible:ring-(--bz-focus) "
            "disabled:opacity-50 disabled:cursor-not-allowed "
            # ``not-disabled:hover:`` (not bare ``hover:``) scopes the hover to
            # elements WITHOUT the ``disabled`` attribute — else disabled
            # items still colour on hover and look interactive. Cf.
            # ``traps.md`` § "hover on disabled controls".
            "not-disabled:hover:text-(--bz-text) "
            "data-[open=true]:text-(--bz-text)"
        ),
        # Label slot — flex-1 so the chevron stays right-aligned.
        "label": "flex-1 truncate",
        # Optional leading icon — sits before the label.
        "icon": "shrink-0",
        # Chevron — rotates 180° when the parent header carries
        # ``data-open=true`` ; slightly longer easing than the body so it
        # feels less mechanical.
        "chevron": (
            "shrink-0 transition-transform duration-300 ease-out "
            "group-data-[open=true]:rotate-180"
        ),
        # Body wrapper — the **grid-template-rows trick** for height
        # animation : a 1-col grid whose row track animates from ``0fr``
        # (collapsed) to ``1fr`` (expanded). The inner ``min-h-0
        # overflow-hidden`` div inherits that height, so the transition
        # adapts to the real content height (no ``max-h`` cap, no JS
        # measurement).
        "body": (
            "grid transition-[grid-template-rows] duration-300 ease-out"
        ),
        # The grid row child — must clip its own overflow and accept
        # ``min-h-0`` so the grid can shrink it below its natural
        # height during the collapse animation.
        "body_clip": "min-h-0 overflow-hidden",
        # Inner padding wrapper around the body content. Padding
        # lives here so it travels INSIDE the clipping region — it
        # animates with the content height instead of being added
        # on top and producing a layout jump at the transition end.
        "body_inner": "",
    },
    # Per-size : header padding, label font-size, icon size, body padding.
    "sizes": {
        "xs": {
            "header": "px-3 py-2 text-xs",
            "icon_size": "xs",
            "chevron_size": "xs",
            "body_inner": "px-3 pb-2 text-xs",
        },
        "sm": {
            "header": "px-3.5 py-2.5 text-sm",
            "icon_size": "sm",
            "chevron_size": "sm",
            "body_inner": "px-3.5 pb-2.5 text-sm",
        },
        "md": {
            "header": "px-4 py-3 text-sm",
            "icon_size": "sm",
            "chevron_size": "sm",
            "body_inner": "px-4 pb-3 text-sm",
        },
        "lg": {
            "header": "px-5 py-3.5 text-base",
            "icon_size": "md",
            "chevron_size": "md",
            "body_inner": "px-5 pb-3.5 text-base",
        },
        "xl": {
            "header": "px-6 py-4 text-lg",
            "icon_size": "lg",
            "chevron_size": "md",
            "body_inner": "px-6 pb-4 text-base",
        },
    },
}
