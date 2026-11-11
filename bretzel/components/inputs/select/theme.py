"""Default :class:`Select` theme.

Custom popover-based combobox — no native ``<select>``. The trigger
is a button styled like an Input ; the panel is an absolute-
positioned dropdown of options. Keyboard navigation (↑↓ Enter
Escape) is wired client-side via the ``bz-*`` runtime.

Slots :
- ``root``      : ``relative w-full`` wrapper anchoring the panel
- ``trigger``   : the button shown when closed (border + chevron)
- ``label``     : the inner ``<span>`` showing the current value
                  or the placeholder
- ``placeholder`` : muted color modifier when no value picked
- ``chevron``   : the trailing chevron icon
- ``panel``     : the absolute dropdown holding options
- ``option``    : each option button — base + size scaling
- ``option_active`` : highlighted-state modifier (hover / keyboard)
- ``option_current``  : the current value's tint (single mode only)
- ``option_check``    : the ✓ marking a PICKED option (multi only) —
                 the affordance ``option_selected``'s accent text
                 alone cannot carry (colour only, WCAG 1.4.1)
- ``option_selected`` : selected-state modifier (the current value)
"""

from __future__ import annotations

from typing import Any

SELECT_THEME: dict[str, Any] = {
    "slots": {
        # Outer wrapper. ``relative`` so the panel anchors against
        # the trigger's box ; full-width by default to match other
        # form controls.
        "root": "bz-select relative w-full",
        # Trigger button — same visual as Input/Textarea so the form
        # looks coherent.
        "trigger": (
            "flex items-center w-full rounded-field border-(length:--bz-stroke) "
            "border-text/10 bg-interface text-text "
            "cursor-pointer outline-none "
            "transition duration-200 "
            "focus:border-(--bz-solid) "
            "focus:ring-2 focus:ring-(--bz-focus-soft) "
            "focus:ring-offset-2 focus:ring-offset-background "
            "disabled:opacity-50 disabled:cursor-not-allowed "
            "disabled:bg-muted/10"
        ),
        # Inner label ; ``truncate`` keeps long values one-line.
        "label": "flex-1 text-start truncate",
        # Modifier added when the displayed text is the placeholder.
        "placeholder": "text-muted/70",
        # Chevron icon. ``pointer-events-none`` so clicks pass through
        # to the trigger button underneath.
        "chevron": (
            "shrink-0 ml-2 text-muted pointer-events-none "
            # Turned by the trigger's OPEN state (``aria-expanded``, an
            # ancestor: ``in-``), the transition with it — it turns
            # opening, snaps back closing with the panel. Static and variant-
            # prefixed: a ``bz-class`` duration would fight the icon's own
            # ``duration-150`` (gate test_bz_class_never_repeats_static_tokens).
            "in-aria-expanded:rotate-180 in-aria-expanded:transition-[rotate] "
            "in-aria-expanded:duration-200"
        ),
        # Dropdown panel — Card-style surface. Positioned by
        # ``$bz.helpers.floating`` (``position: fixed`` + inline
        # ``top``/``left``), which pins ``min-width`` to the trigger via
        # ``match_width``. NO ``left-0 right-0`` here : under fixed
        # positioning the leftover ``right: 0`` stretches the panel to the
        # viewport's right edge.
        "panel": (
            "absolute z-40 mt-1 overflow-y-auto "
            "rounded-box border-(length:--bz-stroke) border-text/10 bg-surface "
            "shadow-lg "
            # The enter fade, at the FIELD cadence — half the menus'.
            # The mechanism of the three classes is explained in a single
            # copy in ``overlay/dropdown/theme.py``.
            #
            # Why 75 and not 150: a menu is a DETOUR (you open it, you
            # look, you choose) and 150 ms read there as care; a field is
            # on the PATH, often filled in series, and the same duration
            # reads there as latency. It is the CLASS of component that
            # decides, not the component.
            "transition-opacity duration-75 "
            "starting:opacity-0"
        ),
        # Each option — full-width clickable row.
        "option": (
            "flex items-center w-full text-start "
            "px-3 py-2 cursor-pointer outline-none "
            # No fade: a row lights at once and goes out at once — sliding
            # down a list, the previous row would trail behind the pointer.
            # As in a native menu.
            "disabled:opacity-50 disabled:cursor-not-allowed"
        ),
        # Highlighted state — applied via ``bz-attr:class`` when
        # the keyboard cursor or hover lands on the option.
        # The hovered row and the current value's tint — the why, once,
        # in ``combobox/theme.py``.
        "option_active": "bg-interface",
        "option_current": "aria-selected:bg-(--bz-bg)",
        # A picked option's tick (multi mode). ``ml-auto`` pushes it to
        # the right edge without touching the label's alignment. The
        # glyph's size lives in ``sizes[<size>]["check_icon_size"]`` — an
        # icon is sized in ``text-*``, never in ``w-``/``h-`` (traps.md).
        "option_check": "shrink-0 ms-auto text-(--bz-text)",
        # Selected state — applied to the option whose value matches
        # the current binding.
        "option_selected": "font-semibold text-(--bz-text)",
        # ── Multi-mode additions ─────────────────────────────────────
        # Mirror the slots Combobox carries for the same purpose
        # (pills + header bar). Identical recipes so a form mixing
        # Select-multi + Combobox-multi reads as one family —
        # duplication is intentional pre-extraction.
        # No pill classes here : multi-mode pills source their styling
        # from :data:`BADGE_THEME` via ``_badge_pill_classes()`` in
        # ``combobox.combobox`` — single source of truth across pickers.
        # Pills row INSIDE the trigger — used in multi mode CLOSED
        # state. ONE line: the trigger has a fixed height, and wrapped
        # pills would spill out of it. It reads "Alice Martin +3":
        # ``pills_first`` (the first pick, plain text, truncated if it must) then
        # ``pills_more``. The removable pills live in the panel's header.
        "pills_row": (
            "flex flex-nowrap items-center gap-1.5 flex-1 min-w-0 overflow-hidden"
        ),
        "pills_first": "min-w-0 truncate text-text",
        "pills_more": "shrink-0 text-muted tabular-nums",
        # Header bar at the top of the panel : the picks as pills.
        # Sticky so it survives scroll.
        "header_bar": (
            "flex flex-wrap items-center gap-2 px-2 py-1.5 "
            "border-b-(length:--bz-stroke) border-text/10 sticky top-0 "
            "bg-surface/95 backdrop-blur z-10"
        ),
        # Text size in ``sizes[<size>]["footer_counter"]`` — do NOT put
        # it back here (slot + table = a Tailwind collision, traps.md).
        "footer_counter": (
            "shrink-0 text-muted tabular-nums"
        ),
        "header_pills": (
            "flex flex-wrap items-center gap-1 flex-1 min-w-0"
        ),
        # Footer bar under the list : counter + Select all / Clear.
        # The mirror of the header, cf. ``combobox/theme.py``.
        "footer_bar": (
            "flex items-center gap-2 px-2 py-1.5 "
            "border-t-(length:--bz-stroke) border-text/10 sticky bottom-0 "
            "bg-surface/95 backdrop-blur z-10"
        ),
        "footer_actions": (
            "shrink-0 inline-flex items-center gap-1 ms-auto"
        ),
        "footer_btn_primary": (
            "inline-flex items-center px-2 py-1 rounded-selector "
            "font-medium text-(--bz-text) "
            "hover:bg-(--bz-bg) cursor-pointer "
            "outline-none focus-visible:ring-2 "
            "focus-visible:ring-(--bz-focus)"
        ),
        "footer_btn_muted": (
            "inline-flex items-center px-2 py-1 rounded-selector "
            "font-medium text-muted "
            "hover:bg-error/10 hover:text-error "
            "cursor-pointer outline-none focus-visible:ring-2 "
            "focus-visible:ring-error/40"
        ),
        # Clear-all × on the trigger right edge (multi mode). Hover
        # gated on ``not-disabled:`` so the × stays visually frozen when
        # the parent Select is ``disabled``.
        "clear": (
            "shrink-0 inline-flex items-center justify-center "
            "ml-1 rounded-selector text-muted not-disabled:hover:text-text "
            "not-disabled:hover:bg-text/5 cursor-pointer outline-none "
            "focus-visible:ring-2 focus-visible:ring-(--bz-focus)"
        ),
    },
    # A scale aligned on ``COMBOBOX_THEME["sizes"]``: Select-multi and
    # Combobox-multi must read as a single family in one form. They
    # already share ``_badge_pill_classes``; any retouching here goes in
    # pairs.
    #
    # ⚠️ "Aligned", NOT "identical". Three gaps are STRUCTURAL: combobox carries
    # ``input`` and ``empty`` which select does not have (no client
    # filter → never a "no results" state), and its ``trigger`` uses
    # ``min-h-10`` where select freezes ``h-10`` — the same height,
    # expressed differently because the combobox's trigger grows with its
    # pills.
    #
    # What IS kept mechanically is the panel's look (shadow / offset /
    # radius), cf.
    # ``tests/consistency/test_anchored_panels_match.py``.
    #
    # The ``*_size`` keys are not classes but the subcomponents' size
    # tokens (Badge, Icon) — the ``BADGE_THEME`` convention. An icon is
    # sized in ``text-*``, never in ``w-``/``h-`` (traps.md).
    #
    # ``md`` = the historical look, unchanged.
    "sizes": {
        "xs": {
            "trigger": "h-7 px-2 text-xs",
            "option": "text-xs",
            "check_icon_size": "xs",
            "panel": "max-h-48",
            "footer_counter": "text-xs",
            "footer_btn_primary": "text-xs",
            "footer_btn_muted": "text-xs",
            "pill_size": "xs",
            "chevron_size": "xs",
            "clear_icon_size": "xs",
        },
        "sm": {
            "trigger": "h-8 px-3 text-sm",
            "option": "text-sm",
            "check_icon_size": "xs",
            "panel": "max-h-52",
            "footer_counter": "text-xs",
            "footer_btn_primary": "text-xs",
            "footer_btn_muted": "text-xs",
            "pill_size": "xs",
            "chevron_size": "xs",
            "clear_icon_size": "xs",
        },
        "md": {
            "trigger": "h-10 px-3 text-sm",
            "option": "text-sm",
            "check_icon_size": "sm",
            "panel": "max-h-60",
            "footer_counter": "text-xs",
            "footer_btn_primary": "text-xs",
            "footer_btn_muted": "text-xs",
            "pill_size": "sm",
            "chevron_size": "sm",
            "clear_icon_size": "xs",
        },
        "lg": {
            "trigger": "h-12 px-4 text-base",
            "option": "text-base",
            "check_icon_size": "md",
            "panel": "max-h-72",
            "footer_counter": "text-sm",
            "footer_btn_primary": "text-sm",
            "footer_btn_muted": "text-sm",
            "pill_size": "md",
            "chevron_size": "md",
            "clear_icon_size": "sm",
        },
        "xl": {
            "trigger": "h-14 px-5 text-lg",
            "option": "text-lg",
            "check_icon_size": "lg",
            "panel": "max-h-80",
            "footer_counter": "text-base",
            "footer_btn_primary": "text-base",
            "footer_btn_muted": "text-base",
            "pill_size": "lg",
            "chevron_size": "lg",
            "clear_icon_size": "sm",
        },
    },
}
