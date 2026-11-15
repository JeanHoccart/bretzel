"""Default :class:`Attachments` theme — the list of files, in its three
presentations, its refusal panel and its hidden input.

``ui.file_upload`` is ``ui.attachments`` plus a dropzone: its theme takes
these slots and sizes as they are, and adds the dropzone's
(``file_upload/theme.py``).

Key UX choices :

- The tile's remove ``×`` floats **outside** the card edge
  (``-top-2 -right-2``) on a solid dark background, so it stays readable
  over any thumbnail; the chip's ``×`` is inline.
- The strip uses the theme's thin scrollbar so the browser default does
  not waste vertical room (and no double scrollbar inside a Card).
"""

from __future__ import annotations

from typing import Any

ATTACHMENTS_THEME: dict[str, Any] = {
    "slots": {
        # ``min-w-0``: the root is often a flex/grid child whose default
        # ``min-width: auto`` pins it to its content's min-content.
        # Useful in a **constrained track** (grid ``1fr``, flex stretch)
        # so it respects its cell. ⚠️ NOT enough on its own against a
        # **shrink-to-fit** parent — it is the ``w-0 min-w-full`` on
        # ``file_list`` (see that slot) that stops the strip inflating
        # the ancestor and really makes ``overflow-x-auto`` work.
        # Switched off (``disabled=``, bindable: read from the input), the
        # list is dimmed and nothing in it answers — no ×, no link.
        "root": (
            "flex flex-col gap-2 min-w-0 "
            "has-[input:disabled]:opacity-50 has-[input:disabled]:pointer-events-none"
        ),
        # Native input — invisible, NOT focusable (tabindex=-1 on the
        # element itself ; ``sr-only`` alone leaves it in the tab order).
        "input_native": (
            "sr-only"
        ),
        # Validation panel.
        "error_panel": (
            "flex flex-col gap-1 w-full px-3 py-2 rounded-box "
            "bg-error/10 border-(length:--bz-stroke) border-error/20"
        ),
        "error_text": (
            "text-xs font-medium text-error"
        ),
        # ── The "strip" presentation (``display="strip"``) ─────────
        #
        # One row of tiles that scrolls in X. ``items-start`` so a tall
        # progress bar on one item doesn't stretch the others. Its bar is
        # the theme's (``ScrollbarConfig``): thin, hidden until hovered or
        # scrolled.
        #
        # ``w-0 min-w-full`` (NOT ``w-full``) is load-bearing so that
        # ``overflow-x-auto`` REALLY fires. With ``w-full``, the strip's
        # min-content = the SUM of the ``shrink-0`` cards; a
        # shrink-to-fit parent (``vstack align=start``, a grid cell,
        # ``inline-flex``…) then sizes itself on that sum → the strip
        # inflates its ancestor instead of scrolling, and the excess is
        # clipped (no scrollbar). ``width:0 ; min-width:100%`` breaks the
        # loop: the strip's max-content contribution becomes 0 (it no
        # longer pulls the ancestor), but it fills 100% of the parent →
        # the cards overflow ITS width → ``overflow-x-auto`` scrolls.
        #
        # Padding trade-off : the remove × button floats ``-top-2
        # -right-2`` (8px outside the card corner). Combined with
        # ``overflow-y: hidden`` (needed to prevent a stray vertical
        # scrollbar) this clips the button. Counter-padding ``pt-3
        # pr-3`` keeps the same overflow constraint AND gives the
        # floating buttons room to render without clipping.
        "file_list": (
            "flex flex-row items-start w-0 min-w-full gap-3 pt-3 pr-3 pb-2 "
            "snap-x overflow-x-auto overflow-y-hidden empty:hidden"
        ),
        # File card. ``overflow-visible`` so the floating × button
        # can stick out of the corner. ``shrink-0`` prevents the
        # horizontal flex container from squishing items.
        "file_item": (
            "group relative shrink-0 flex flex-col items-center "
            "justify-start w-28 p-2 rounded-box border-(length:--bz-stroke) border-text/10 "
            "bg-interface shadow-sm hover:border-(--bz-border-hover) "
            "hover:bg-(--bz-bg) transition snap-start"
        ),
        "file_thumb": (
            "w-20 h-16 mb-2 rounded-selector object-cover bg-background"
        ),
        "file_icon": (
            "w-10 h-10 mb-2 inline-flex items-center justify-center "
            "text-(--bz-text) text-3xl "
            "transition-transform group-hover:scale-110"
        ),
        # The size of the text is the step's (``sizes``).
        "file_name": (
            "w-full truncate text-center font-semibold text-text"
        ),
        "file_size": (
            "w-full text-center text-xs text-muted"
        ),
        # Async upload progress (per-file bar at the bottom of the card).
        "file_progress_bar": (
            "absolute bottom-0 left-0 right-0 h-1 bg-text/5 "
            "rounded-b-box overflow-hidden"
        ),
        "file_progress_fill": (
            "h-full bg-(--bz-solid) transition-[width] duration-200"
        ),
        # Status badges over the thumb / icon.
        "file_status_done": (
            "absolute top-1 left-1 inline-flex items-center "
            "justify-center w-5 h-5 rounded-full bg-success text-white "
            "shadow-sm"
        ),
        "file_status_error": (
            "absolute top-1 left-1 inline-flex items-center "
            "justify-center w-5 h-5 rounded-full bg-error text-white "
            "shadow-sm"
        ),
        "file_status_icon": (
            "inline-flex shrink-0 text-current text-xs"
        ),
        # Per-file remove button — solid, floats OUTSIDE the card
        # corner so it never overlaps the thumb.
        # ALWAYS visible — no reveal on hover. Tailwind v4 wraps every
        # ``hover:`` variant in ``@media (hover: hover)``: on a touch
        # device a × set at ``opacity-0`` stayed invisible FOREVER and the
        # only way to remove a file became unreachable (cf. traps.md).
        # ``active:`` (and not ``hover:``) carries the touch feedback.
        # No dimension here: the box comes from ``sizes["remove_btn"]``
        # and the glyph from ``sizes["remove_btn_icon_size"]``.
        # ``z-10``: above the link that covers the card (``file_link``).
        "remove_btn": (
            "absolute z-10 -top-2 -right-2 inline-flex items-center "
            "justify-center rounded-full bg-text text-background "
            "shadow-md hover:bg-error hover:text-white "
            "active:scale-90 active:bg-error active:text-white "
            "focus-visible:outline-none "
            "focus-visible:ring-2 focus-visible:ring-error/50 "
            "transition"
        ),
        # ── The "grid" presentation (``display="grid"``) ───────────
        #
        # Large tiles that wrap onto several lines. The tile keeps the
        # strip's structure (thumbnail, name, size, corner ×): only the
        # list wraps and the tile, its thumbnail and its icon grow.
        "grid_list": (
            "flex flex-row flex-wrap items-start gap-3 pt-3 pe-3 empty:hidden"
        ),
        "grid_item": (
            "group relative flex flex-col items-center justify-start "
            "w-40 p-2 rounded-box border-(length:--bz-stroke) border-text/10 "
            "bg-interface shadow-sm hover:border-(--bz-border-hover) "
            "hover:bg-(--bz-bg) transition"
        ),
        "grid_thumb": (
            "w-full h-28 mb-2 rounded-selector object-cover bg-background"
        ),
        "grid_icon": (
            "w-full h-28 mb-2 inline-flex items-center justify-center "
            "rounded-selector bg-background text-(--bz-text) text-5xl"
        ),
        # ── The "chips" presentation (``display="chips"``) ─────────
        #
        # NOT a restyling of the tiles: another STRUCTURE. The tile is a
        # column (`flex-col w-28`) with a thumbnail and a × as a corner
        # badge (`absolute -top-2 -right-2`); the chip is a row
        # (`flex-row`) with no thumbnail, whose × is INLINE. No class
        # takes you from one to the other — it is the DOM's nesting that
        # changes, and that is precisely what `slots=` cannot do.
        "chip_list": (
            "flex flex-row flex-wrap items-center gap-2 empty:hidden"
        ),
        # Height, paddings, gap: the step's (``sizes``) — one height for a
        # chip with a × and one without. With a ×, the right padding
        # shrinks to the ×'s breath (``has-[button]:``).
        "chip_item": (
            "group relative inline-flex flex-row items-center "
            "max-w-full rounded-full border-(length:--bz-stroke) border-text/10 "
            "bg-interface hover:border-(--bz-border-hover) "
            "hover:bg-(--bz-bg) transition"
        ),
        "chip_icon": (
            "inline-flex shrink-0 items-center justify-center text-(--bz-text)"
        ),
        "chip_name": (
            "truncate font-medium text-text"
        ),
        # INLINE statuses — the tile sets them ``absolute top-1 left-1``
        # on its thumbnail, a chip has none.
        "chip_status_done": (
            "inline-flex shrink-0 items-center justify-center w-4 h-4 "
            "rounded-full bg-success text-white"
        ),
        "chip_status_error": (
            "inline-flex shrink-0 items-center justify-center w-4 h-4 "
            "rounded-full bg-error text-white"
        ),
        "chip_progress_bar": (
            "absolute bottom-0 left-0 right-0 h-0.5 bg-text/5 "
            "rounded-b-full overflow-hidden"
        ),
        # An INLINE ×, in the chip's flow.
        "chip_remove_btn": (
            "relative z-10 shrink-0 inline-flex items-center justify-center "
            "rounded-full text-muted hover:bg-error hover:text-white "
            "active:scale-90 active:bg-error active:text-white "
            "transition-colors"
        ),
        # A file the server holds, with a link (``files=[{"href": …}]``):
        # its name opens it. The underline comes on hover only — the name
        # already reads as the file.
        # The name of a file is the link that opens it, and its ``::after``
        # covers the whole card (the card is ``relative``): a click
        # anywhere on it opens the file. The × sits above (``z-10``).
        "file_link": (
            "after:absolute after:inset-0 after:rounded-[inherit] "
            "hover:underline focus-visible:outline-none focus-visible:underline"
        ),
    },
    # ── Size paliers ─────────────────────────────────────────────────
    # The remove × follows the component's ``size=`` — the box, then the
    # glyph. Without it, it would stay at one size at ALL steps: the card
    # would grow, its × would not. The glyph's values are ``Icon`` size
    # names (not ``text-*`` classes): ``Icon`` owns the glyph's scale.
    # ``remove_btn`` lands on the tiles' ×; ``chip_remove_btn`` takes the
    # same step: one × size per step, whatever the presentation.
    #
    # A chip follows the step whole: its height (the same with or without
    # a ×), its paddings, its icon and its text — the field ladder's text
    # (``xs`` → ``text-xs`` … ``xl`` → ``text-lg``, less one step: a chip
    # is a label, not a field).
    "sizes": {
        "xs": {
            "remove_btn": "w-4 h-4",
            "chip_item": "h-6 gap-1 ps-2 pe-2 has-[button]:pe-0.5",
            "chip_icon": "text-xs",
            "chip_name": "text-xs",
            "chip_remove_btn": "w-5 h-5",
            "file_name": "text-xs",
            "remove_btn_icon_size": "xs",
        },
        "sm": {
            "remove_btn": "w-5 h-5",
            "chip_item": "h-7 gap-1.5 ps-2.5 pe-2.5 has-[button]:pe-1",
            "chip_icon": "text-sm",
            "chip_name": "text-xs",
            "chip_remove_btn": "w-5 h-5",
            "file_name": "text-xs",
            "remove_btn_icon_size": "xs",
        },
        "md": {
            "remove_btn": "w-6 h-6",
            "chip_item": "h-8 gap-1.5 ps-3 pe-3 has-[button]:pe-1",
            "chip_icon": "text-base",
            "chip_name": "text-sm",
            "chip_remove_btn": "w-6 h-6",
            "file_name": "text-xs",
            "remove_btn_icon_size": "xs",
        },
        "lg": {
            "remove_btn": "w-7 h-7",
            "chip_item": "h-10 gap-2 ps-3.5 pe-3.5 has-[button]:pe-1.5",
            "chip_icon": "text-lg",
            "chip_name": "text-base",
            "chip_remove_btn": "w-7 h-7",
            "file_name": "text-sm",
            "remove_btn_icon_size": "sm",
        },
        "xl": {
            "remove_btn": "w-8 h-8",
            "chip_item": "h-12 gap-2 ps-4 pe-4 has-[button]:pe-2",
            "chip_icon": "text-xl",
            "chip_name": "text-lg",
            "chip_remove_btn": "w-8 h-8",
            "file_name": "text-base",
            "remove_btn_icon_size": "sm",
        },
    },
}
