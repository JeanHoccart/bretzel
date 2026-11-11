"""Default :class:`FileUpload` theme.

Two variants — **dropzone** (large dashed area) and **button** (compact
inline trigger) — sharing the file-list strip below. Each ``size=``
palier (xs/sm/md/lg/xl) scales padding + icon + font + button height
in the ``sizes`` map below ; the render path picks the right one.

Key UX choices :

- The remove ``×`` button floats **outside** the card edge
  (``-top-2 -right-2``) on a solid dark background, so it stays
  readable over any thumbnail.
- The horizontal strip uses a custom thin scrollbar so the browser
  default scrollbar doesn't waste vertical real-estate (and we
  don't end up with a double scrollbar inside Card).
- The dropzone auto-shrinks when ``files.length > 0`` — the empty
  state collapses to a compact "Drop more files" hint. Mirror of
  Linear / Notion patterns.
- A global ``dragenter`` listener on ``window`` highlights every
  dropzone on the page when the user drags a file from the OS — the
  dropzone glows so the drop target is obvious from any
  scroll position.
"""

from __future__ import annotations

from typing import Any

FILE_UPLOAD_THEME: dict[str, Any] = {
    "slots": {
        # ``min-w-0``: the root is often a flex/grid child whose default
        # ``min-width: auto`` pins it to its content's min-content.
        # Useful in a **constrained track** (grid ``1fr``, flex stretch)
        # so it respects its cell. ⚠️ NOT enough on its own against a
        # **shrink-to-fit** parent — it is the ``w-0 min-w-full`` on
        # ``file_list`` (see that slot) that stops the strip inflating
        # the ancestor and really makes ``overflow-x-auto`` work. The two
        # together = robust everywhere (the family of the date_picker
        # `w-fit` bug).
        #
        # The WIDTH is the variant's (``variants`` below), not the root's.
        "root": (
            "bz-file-upload flex flex-col gap-3 min-w-0"
        ),
        # Native input — invisible, NOT focusable (tabindex=-1 on the
        # element itself ; ``sr-only`` alone leaves it in the tab
        # order). The wrapper is the focus host.
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
        # File-list strip. ``items-start`` so a tall progress bar on
        # one item doesn't stretch the others. Custom scrollbar so
        # we don't double up with the page scrollbar — thin, themed,
        # only shows on hover.
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
        # the cards overflow ITS width → ``overflow-x-auto`` finally
        # scrolls. Robust in any context (shrink-parent AND
        # full-width). The ``min-w-0`` on the root is still useful (a
        # grid cell narrower than the dropzone).
        #
        # Padding trade-off : the remove × button floats ``-top-2
        # -right-2`` (8px outside the card corner). Combined with
        # ``overflow-y: hidden`` (needed to prevent a stray vertical
        # scrollbar) this clips the button. Counter-padding ``pt-3
        # pr-3`` keeps the same overflow constraint AND gives the
        # floating buttons room to render without clipping.
        "file_list": (
            "flex flex-row items-start w-0 min-w-full gap-3 pt-3 pr-3 pb-2 "
            "snap-x overflow-x-auto overflow-y-hidden empty:hidden "
            # ⚠️ These six variants DO NOT APPLY IN DEV: the element
            # carries them all, and the page's sheets contain no prefixed
            # rule for them, so the strip inherits the global 4 px bar
            # instead of its 1.5. In PROD they compile: so it is not a
            # writing error but a dev/prod divergence, the same family as
            # ``theme/css.py`` § ``_NO_SCROLLBAR``.
            #
            # Kept as they are: the shape is right, and replacing them
            # with a home-made hook would go against the established
            # preference (standard Tailwind written by the dev rather
            # than a proprietary utility). What needs fixing is the dev
            # mode.
            "[&::-webkit-scrollbar]:h-1.5 "
            "[&::-webkit-scrollbar-track]:bg-transparent "
            "[&::-webkit-scrollbar-thumb]:bg-text/10 "
            "[&::-webkit-scrollbar-thumb]:rounded-full "
            "[&::-webkit-scrollbar-thumb]:transition-colors "
            "hover:[&::-webkit-scrollbar-thumb]:bg-text/25"
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
        # ── The "chips" presentation (``list="chips"``) ────────────
        #
        # NOT a restyling of the tiles: another STRUCTURE. The tile is a
        # column (`flex-col w-28`) with a thumbnail and a × as a corner
        # badge (`absolute -top-2 -right-2`); the chip is a row
        # (`flex-row`) with no thumbnail, whose × is INLINE. No class
        # takes you from one to the other — it is the DOM's nesting that
        # changes, and that is precisely what `slots=` cannot do
        # (overriding them would leave the × floating).
        #
        # The ``chip_`` prefix: THIS file's convention for an alternative
        # presentation (cf. ``dropzone_*`` / ``button_*`` for the
        # ``variant=`` axis).
        "chip_list": (
            "flex flex-row flex-wrap items-center gap-2 pt-3 empty:hidden"
        ),
        "chip_item": (
            "group relative inline-flex flex-row items-center gap-1.5 "
            "max-w-full pl-2 pr-1 py-1 rounded-full border-(length:--bz-stroke) border-text/10 "
            "bg-interface hover:border-(--bz-border-hover) "
            "hover:bg-(--bz-bg) transition"
        ),
        "chip_icon": (
            "inline-flex shrink-0 items-center justify-center "
            "text-(--bz-text) text-sm"
        ),
        "chip_name": (
            "truncate text-xs font-medium text-text"
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
        # An INLINE ×, in the chip's flow — the structural difference
        # that motivated this whole presentation.
        "chip_remove_btn": (
            "relative shrink-0 inline-flex items-center justify-center "
            "rounded-full text-muted hover:bg-error hover:text-white "
            "active:scale-90 active:bg-error active:text-white "
            "transition-colors"
        ),
        "file_thumb": (
            "w-20 h-16 mb-2 rounded-selector object-cover bg-background"
        ),
        "file_icon": (
            "w-10 h-10 mb-2 inline-flex items-center justify-center "
            "text-(--bz-text) text-3xl "
            "transition-transform group-hover:scale-110"
        ),
        "file_name": (
            "w-full truncate text-center text-xs font-semibold text-text"
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
            "h-full bg-(--bz-solid) transition-[width] duration-150"
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
        # ``hover:`` variant in ``@media (hover: hover)`` (a v3→v4
        # break): on a touch device the rule does not exist, so a × set
        # at ``opacity-0`` stayed invisible FOREVER and the only way to
        # remove a file became unreachable (reproduced in the browser,
        # cf. traps.md). Showing it permanently fixes the root rather
        # than compensating the symptom: an action is not hidden behind a
        # gesture the device cannot produce. ``active:`` (and not
        # ``hover:``) carries the touch feedback, which does work
        # everywhere.
        # No dimension here: the box comes from ``sizes["remove_btn"]``
        # and the glyph from ``sizes["remove_btn_icon_size"]``, otherwise
        # the × stays frozen whatever the component's ``size=`` (the
        # "frozen child" family, cf. _FROZEN_CHILD_BASELINE). Badge is
        # the model.
        "remove_btn": (
            "absolute -top-2 -right-2 inline-flex items-center "
            "justify-center rounded-full bg-text text-background "
            "shadow-md hover:bg-error hover:text-white "
            "active:scale-90 active:bg-error active:text-white "
            "focus-visible:outline-none "
            "focus-visible:ring-2 focus-visible:ring-error/50 "
            "transition"
        ),
        # variant=dropzone — the big dashed area. Padding + content
        # scale via the ``sizes`` map below ; this slot only owns
        # the colour / focus / interactive parts.
        #
        # Neutral at REST, like an Input : a dashed ``border-text/15``
        # over ``bg-interface``, no colour tint until the user engages.
        # The coloured accent lives ONLY in the interactive states
        # — hover (border + faint fill), focus ring, and the drag
        # highlights (``dropzone_active`` / ``dropzone_global_drag``).
        # Trade-off : ``color="success"`` vs ``color="primary"`` now
        # read identically at rest and only diverge on hover / focus /
        # drag — deliberate, to keep the resting component calm.
        "dropzone_wrapper": (
            "group relative flex flex-col items-center justify-center "
            "w-full rounded-box border-(length:--bz-stroke-strong) border-dashed "
            "border-text/15 bg-interface cursor-pointer "
            "transition duration-200 "
            "hover:border-(--bz-border-hover) hover:bg-(--bz-bg) "
            "has-[:disabled]:opacity-50 has-[:disabled]:cursor-not-allowed "
            "outline-none focus-visible:border-(--bz-solid) "
            "focus-visible:ring-2 focus-visible:ring-offset-2 "
            "focus-visible:ring-offset-background "
            "focus-visible:ring-(--bz-focus)"
        ),
        # Class added by ``bz-attr:class`` when the user is dragging
        # files OVER this dropzone (vs the global highlight, which
        # signals a drag on the page — see ``dropzone_global_drag``).
        "dropzone_active": (
            "border-(--bz-solid) bg-(--bz-bg) scale-[0.99]"
        ),
        # Highlight added when ``isGlobalDragActive`` is true — a
        # file is being dragged anywhere on the page, every dropzone
        # surfaces itself.
        "dropzone_global_drag": (
            "border-(--bz-border-hover) bg-(--bz-bg) "
            "ring-2 ring-(--bz-focus-soft) ring-offset-2 "
            "ring-offset-background"
        ),
        "dropzone_empty_state": (
            "flex flex-col items-center justify-center pointer-events-none"
        ),
        # Neutral ``text-muted`` at rest ; lights up in the colour on
        # hover — mirror of the Input icon slots' ``group-focus-within``
        # behaviour.
        "dropzone_icon": (
            "inline-flex shrink-0 text-muted "
            "group-hover:text-(--bz-text) transition duration-200 "
            "group-hover:-translate-y-0.5"
        ),
        "dropzone_title": (
            "font-semibold text-text text-center"
        ),
        "dropzone_subtitle": (
            "text-muted text-center"
        ),
        # variant=button — compact inline trigger. Neutral at rest like
        # an Input (``border-text/10`` + ``bg-interface`` + ``text-text``)
        # so it sits calm next to a primary CTA ; the coloured
        # accent surfaces on hover (border + text + faint fill) and the
        # focus ring. The icon rides ``text-current``, so it follows the
        # label colour through the hover transition automatically.
        "button_wrapper": (
            "inline-flex items-center justify-center gap-2 "
            "rounded-field border-(length:--bz-stroke) border-text/10 bg-interface "
            "text-text font-medium cursor-pointer transition "
            "hover:bg-(--bz-bg) hover:border-(--bz-border-hover) "
            "hover:text-(--bz-text) "
            "has-[:disabled]:opacity-50 has-[:disabled]:cursor-not-allowed "
            "outline-none focus-visible:ring-2 focus-visible:ring-offset-2 "
            "focus-visible:ring-offset-background "
            "focus-visible:ring-(--bz-focus)"
        ),
        "button_icon": (
            "inline-flex shrink-0 text-current"
        ),
    },
    # ── Variants: the root's width ───────────────────────────────────
    # The dropzone is a SURFACE, it fills its row. The button is a
    # button: it takes its label's width. With the dropzone's ``w-full``
    # on a stretching column, the compact trigger would become a full-width
    # bar and push its neighbour to the end of an ``hstack``.
    # ``items-start`` keeps the file list under it at the root's width
    # while the button hugs its label.
    "variants": {
        "dropzone": "w-full",
        "button": "items-start",
    },
    # ── Size paliers ─────────────────────────────────────────────────
    # Each size scales the visual weight of dropzone padding /
    # icon-size / title-text-size / button height. Read manually in
    # ``FileUpload.render`` because we want size-specific decisions on
    # multiple sub-elements (not just the root).
    "sizes": {
        # One row per step, one entry per key — the shape of every other
        # table (``sizes[<size>][<key>]``). The keys that NAME A
        # SLOT (``dropzone_title``, ``dropzone_subtitle``, ``remove_btn``)
        # land on that slot through the base composer; the others are read
        # by ``FileUpload.render``.
        #
        # ⚠️ **The dropzone padding is split by AXIS, and that is not a
        # style choice.** The vertical axis cannot live in BOTH layers
        # (``py-8`` as a static ``class=``, ``py-3`` added in ``bz-class``
        # when files are there): both utilities have the
        # SAME specificity — it is the Tailwind sheet's order that
        # decides, not the order of addition to the ``classList``. An
        # element carrying ``py-8 py-3`` takes the ``py-8``, so the compact
        # state would **never apply**.
        # Hence three entries instead of two: ``dropzone_padding_x`` is
        # identical in both states and stays static; the vertical one is
        # carried EXCLUSIVELY by the dynamic layer, which emits the full
        # ternary — ``dropzone_padding_y`` for the EMPTY state (the large
        # welcome area), ``dropzone_padding_with_files`` for the WITH-FILES
        # state (the dropzone collapses into a "drop more" reminder). Same
        # axis, so the two cannot coexist — the ternary picks one. It is
        # ``accordion.py``'s pattern ("both row classes live exclusively in
        # the ``bz-class``"). Do NOT put a ``py-*`` in the static padding:
        # the repetition is invisible in the HTML, it only shows in
        # ``getComputedStyle``.
        #
        # ``dropzone_icon_size_with_files``: the icon shrinks when the
        # dropzone is compact (files present).
        #
        # ``remove_btn`` / ``remove_btn_icon_size``: the remove × follows
        # the component's ``size=`` — the box, then the glyph. Without
        # that it would stay at ``w-6 h-6`` / ``text-xs`` at ALL steps:
        # the card would grow, its × would not. The glyph's values are
        # ``Icon`` size names (not ``text-*`` classes): it is ``Icon`` that
        # owns the glyph's scale. Same contract as Badge's
        # ``close_icon_size``.
        "xs": {
            "dropzone_padding_x": "px-3",
            "dropzone_padding_y": "py-3",
            "dropzone_padding_with_files": "py-2",
            "dropzone_icon_size": "text-lg",
            "dropzone_icon_size_with_files": "text-sm",
            "dropzone_icon_margin": "mb-1",
            "dropzone_icon_margin_with_files": "mb-0.5",
            "dropzone_title": "text-xs",
            "dropzone_subtitle": "text-xs mt-0.5",
            "button_padding": "px-2 h-7 text-xs",
            "button_icon_size": "text-xs",
            "remove_btn": "w-5 h-5",
            "remove_btn_icon_size": "xs",
        },
        "sm": {
            "dropzone_padding_x": "px-4",
            "dropzone_padding_y": "py-5",
            "dropzone_padding_with_files": "py-2.5",
            "dropzone_icon_size": "text-xl",
            "dropzone_icon_size_with_files": "text-base",
            "dropzone_icon_margin": "mb-2",
            "dropzone_icon_margin_with_files": "mb-1",
            "dropzone_title": "text-sm",
            "dropzone_subtitle": "text-xs mt-1",
            "button_padding": "px-3 h-8 text-sm",
            "button_icon_size": "text-sm",
            "remove_btn": "w-5 h-5",
            "remove_btn_icon_size": "xs",
        },
        "md": {
            "dropzone_padding_x": "px-6",
            "dropzone_padding_y": "py-8",
            "dropzone_padding_with_files": "py-3",
            "dropzone_icon_size": "text-3xl",
            "dropzone_icon_size_with_files": "text-xl",
            "dropzone_icon_margin": "mb-3",
            "dropzone_icon_margin_with_files": "mb-1.5",
            "dropzone_title": "text-sm",
            "dropzone_subtitle": "text-xs mt-1",
            "button_padding": "px-4 h-10 text-sm",
            "button_icon_size": "text-base",
            "remove_btn": "w-6 h-6",
            "remove_btn_icon_size": "xs",
        },
        "lg": {
            "dropzone_padding_x": "px-8",
            "dropzone_padding_y": "py-12",
            "dropzone_padding_with_files": "py-4",
            "dropzone_icon_size": "text-4xl",
            "dropzone_icon_size_with_files": "text-2xl",
            "dropzone_icon_margin": "mb-3",
            "dropzone_icon_margin_with_files": "mb-2",
            "dropzone_title": "text-base",
            "dropzone_subtitle": "text-sm mt-1",
            "button_padding": "px-5 h-12 text-base",
            "button_icon_size": "text-lg",
            "remove_btn": "w-7 h-7",
            "remove_btn_icon_size": "sm",
        },
        "xl": {
            "dropzone_padding_x": "px-10",
            "dropzone_padding_y": "py-16",
            "dropzone_padding_with_files": "py-5",
            "dropzone_icon_size": "text-5xl",
            "dropzone_icon_size_with_files": "text-3xl",
            "dropzone_icon_margin": "mb-4",
            "dropzone_icon_margin_with_files": "mb-2",
            "dropzone_title": "text-lg",
            "dropzone_subtitle": "text-base mt-1.5",
            "button_padding": "px-6 h-14 text-lg",
            "button_icon_size": "text-xl",
            "remove_btn": "w-8 h-8",
            "remove_btn_icon_size": "sm",
        },
    },
}
