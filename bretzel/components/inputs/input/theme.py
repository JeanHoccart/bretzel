"""Default :class:`Input` theme.

Identity : soft border ``border-text/10``, generous ``rounded-field``,
focus ring tinted ``ring-(--bz-focus-soft)`` over the page
``ring-offset-background``, ``transition-all duration-200`` so the
focus state slides in instead of snapping.

Two roots — the input has TWO architectures depending on whether the
caller passed prefix / suffix slots :

- **No affixes** (the common case) : ``root`` is a thin relative
  wrapper, the focus ring lives on the ``<input>`` itself
  (``input`` slot).
- **With prefix or suffix** : the caller wires
  ``ui.input(prefix="$", ...)`` ; render switches to the ``prefix_root``
  layout where the frame and the focus ring live on the WRAPPER, and
  the ``<input>`` itself goes transparent (``input_inner`` slot).

Slot ``clear_button`` : the ``×`` of ``clearable=True``, on the same
right edge as ``icon_right``.

Icon slots ``icon_left`` / ``icon_right`` overlay the input absolute-
positioned and shift their colour on ``group-focus-within`` so the
icon "lights up" in the colour as the field gets focus.
"""

from __future__ import annotations

from typing import Any

INPUT_THEME: dict[str, Any] = {
    "slots": {
        # No-affix architecture : root just positions icons over the input.
        # ``transition`` (not ``transition-all``) so colours / ring / shadow
        # fade smoothly but WIDTH / HEIGHT / PADDING never animate — those
        # would otherwise play a visible grow→shrink when the browser
        # applies styles late (dev browser-Tailwind) or idiomorph swaps the
        # node on boosted nav.
        "root": (
            "relative flex items-center w-full transition "
            "duration-200 group"
        ),
        # The visible <input> in the no-affix case — frame + focus ring live here.
        "input": (
            "bz-input "  # audit marker — cf. tests/audit/checklist.py
            "block w-full rounded-field border-(length:--bz-stroke) border-text/10 "
            "bg-interface text-text placeholder:text-muted/60 "
            "outline-none transition duration-200 "
            "focus:border-(--bz-solid) "
            "focus:ring-2 focus:ring-(--bz-focus-soft) "
            "focus:ring-offset-2 focus:ring-offset-background "
            "disabled:opacity-50 disabled:cursor-not-allowed "
            "disabled:bg-muted/10 "
            "read-only:cursor-default read-only:bg-interface/50"
        ),
        # Affixes architecture : the wrapper carries the frame + ring.
        # ``relative``: the ``×`` of ``clearable=True`` positions itself
        # at ``absolute right-3`` as in the other layout — a SINGLE
        # writing of the slot for both. With no anchor here, it would go
        # and settle on the first positioned ancestor, that is to say
        # anywhere in the page.
        "prefix_root": (
            "relative flex items-center w-full rounded-field "
            "border-(length:--bz-stroke) border-text/10 "
            "bg-interface transition duration-200 group "
            "focus-within:border-(--bz-solid) "
            "focus-within:ring-2 focus-within:ring-(--bz-focus-soft) "
            "focus-within:ring-offset-2 focus-within:ring-offset-background"
        ),
        # The <input> when wrapped in prefix_root : strip its own frame.
        "input_inner": (
            "block w-full outline-none bg-transparent text-text "
            "placeholder:text-muted/60 rounded-field"
        ),
        # Inline static label slots (e.g. ``https://`` / ``.com``).
        "prefix": (
            "shrink-0 text-muted/60 text-sm font-medium select-none "
            "pl-3 py-2"
        ),
        "suffix": (
            "shrink-0 text-muted/60 text-sm font-medium select-none "
            "pr-3 py-2"
        ),
        # Absolute-positioned icons overlaid on the no-affix input ;
        # ``group-focus-within`` lights them up in the focus colour.
        "icon_left": (
            "absolute left-3 text-muted/60 "
            "group-focus-within:text-(--bz-text-muted) "
            "transition-colors pointer-events-none "
            "flex items-center justify-center"
        ),
        "icon_right": (
            "absolute right-3 text-muted/60 "
            "group-focus-within:text-(--bz-text-muted) "
            "transition-colors pointer-events-none "
            "flex items-center justify-center"
        ),
        # The ``×`` of ``clearable=True``. It occupies the SAME right
        # edge as ``icon_right`` (and as ``suffix`` in the other layout)
        # — the two together would overlap, and it is up to the caller to
        # choose which they want there.
        #
        # ``peer-placeholder-shown:hidden``: the visibility is PURE CSS,
        # with no scope and no JS. ``:placeholder-shown`` matches exactly
        # when the field is empty, so the cross only exists when there is
        # something to clear, and it reacts to typing without any signal
        # being involved. It is what allows adding the affordance WITHOUT
        # touching the value scope that lives on the ``<input>`` (and
        # lives there for a reason: its stable ``bz-id`` makes the typed
        # text survive a morph).
        #
        # NOT ``pointer-events-none``, unlike the two icons: this one is
        # clicked.
        "clear_button": (
            "absolute right-3 text-muted/60 "
            "not-disabled:hover:text-text cursor-pointer "
            "transition-colors outline-none rounded-selector "
            "focus-visible:ring-2 focus-visible:ring-(--bz-focus) "
            "flex items-center justify-center "
            "peer-placeholder-shown:hidden "
            "disabled:opacity-50 disabled:cursor-not-allowed"
        ),
    },
    # Sizes apply to the input ``height + padding + text-size`` and add
    # extra left/right padding when an icon slot is present (so the
    # text doesn't collide with the absolute-positioned icon).
    "sizes": {
        "xs": {
            "input": "h-7 px-2 text-xs",
            "icon_pad_left": "pl-7",
            "icon_pad_right": "pr-7",
            "clear_icon_size": "xs",
        },
        "sm": {
            "input": "h-8 px-3 text-xs",
            "icon_pad_left": "pl-8",
            "icon_pad_right": "pr-8",
            "clear_icon_size": "xs",
        },
        "md": {
            "input": "h-10 px-3 text-sm",
            "icon_pad_left": "pl-10",
            "icon_pad_right": "pr-10",
            "clear_icon_size": "sm",
        },
        "lg": {
            "input": "h-12 px-4 text-base",
            "icon_pad_left": "pl-12",
            "icon_pad_right": "pr-12",
            "clear_icon_size": "sm",
        },
        "xl": {
            "input": "h-14 px-5 text-lg",
            "icon_pad_left": "pl-14",
            "icon_pad_right": "pr-14",
            "clear_icon_size": "md",
        },
    },
}
