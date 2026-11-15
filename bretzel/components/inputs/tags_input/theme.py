"""Default :class:`TagsInput` theme.

A text field whose values are TAGS inside the field, on the line one
types on — the recipients of a mail. The frame follows ``ui.input`` /
``ui.combobox`` (same border, radius, focus ring, size scale), so a form
mixing them reads as one family; the tags follow ``ui.badge`` (their
classes come from the resolved Badge theme, like the combobox's pills).

Slots :
- ``root``     : ``relative w-full`` wrapper anchoring the suggestions
- ``trigger``  : the bordered field holding the tags and the text input
- ``tags_row`` : the wrapping row of tags + input
- ``tag``      : what a tag adds to the badge: the invalid and the
                 selected (Backspace) states
- ``input``    : the ``<input type="text">`` one types in
- ``panel``    : the suggestions, anchored under the field
- ``option``   : one suggestion
- ``option_active`` : the highlighted suggestion (keyboard or pointer)
"""

from __future__ import annotations

from typing import Any

TAGS_INPUT_THEME: dict[str, Any] = {
    "slots": {
        "root": "bz-tags-input relative w-full",
        # ``cursor-text``: a click anywhere in the field focuses the
        # input (the runtime does it), so the whole frame reads as one.
        "trigger": (
            # The frame and its focus ring are the variant's (``variants``).
            "flex items-center w-full rounded-field text-text "
            "cursor-text outline-none transition duration-200 "
            "has-[input:disabled]:opacity-50 "
            "has-[input:disabled]:cursor-not-allowed"
        ),
        # The tags wrap and the field grows, up to about four lines
        # (``sizes[…]["tags_row"]``), then the row scrolls INSIDE the field
        # — never sideways.
        "tags_row": (
            "flex flex-wrap items-center gap-1 flex-1 min-w-0 "
            "overflow-x-hidden overflow-y-auto"
        ),
        # Added to the badge's classes. Invalid: the error colours, the
        # reason in the tag's tooltip. Selected: the first Backspace on an
        # empty field selects the last tag, the second removes it.
        "tag": (
            "max-w-full cursor-default "
            "aria-invalid:bg-error/15 aria-invalid:text-error "
            "data-[selected=true]:ring-2 data-[selected=true]:ring-inset "
            "data-[selected=true]:ring-(--bz-focus)"
        ),
        "input": (
            "flex-1 min-w-[80px] bg-transparent outline-none border-none p-0 "
            "text-text placeholder:text-muted/70 disabled:cursor-not-allowed"
        ),
        # Aligned on the anchored-panel family (test_anchored_panels_match).
        "panel": (
            "absolute z-40 mt-1 overflow-y-auto "
            "rounded-box border-(length:--bz-stroke) border-text/10 bg-surface "
            "shadow-lg transition-opacity duration-75 starting:opacity-0"
        ),
        "option": (
            "flex items-center w-full text-start px-3 py-2 cursor-pointer "
            "outline-none"
        ),
        "option_active": "bg-interface",
    },
    # ``pill_size`` and ``remove_icon_size`` are not classes: the Badge
    # step of the tags and the Icon step of their cross, read by the render.
    "variants": {
        "surface": {
            "trigger": "bg-interface border-(length:--bz-stroke) border-text/10 focus-within:border-(--bz-solid) focus-within:ring-2 focus-within:ring-(--bz-focus-soft) focus-within:ring-offset-2 focus-within:ring-offset-background has-[input:disabled]:bg-muted/10",
        },
        "ghost": {
            "trigger": "[[data-bz-keyboard]_&]:focus-within:ring-2 [[data-bz-keyboard]_&]:focus-within:ring-(--bz-focus) [[data-bz-keyboard]_&]:focus-within:ring-offset-2 [[data-bz-keyboard]_&]:focus-within:ring-offset-background",
        },
    },
    "sizes": {
        "xs": {
            "tags_row": "max-h-20",
            "trigger": "min-h-7 px-2 py-0.5 text-xs",
            "input": "text-xs",
            "option": "text-xs",
            "panel": "max-h-48",
            "pill_size": "xs",
            "remove_icon_size": "xs",
        },
        "sm": {
            "tags_row": "max-h-24",
            "trigger": "min-h-8 px-3 py-0.5 text-sm",
            "input": "text-sm",
            "option": "text-sm",
            "panel": "max-h-52",
            "pill_size": "sm",
            "remove_icon_size": "xs",
        },
        "md": {
            "tags_row": "max-h-28",
            "trigger": "min-h-10 px-3 py-1.5 text-sm",
            "input": "text-sm",
            "option": "text-sm",
            "panel": "max-h-60",
            "pill_size": "md",
            "remove_icon_size": "xs",
        },
        "lg": {
            "tags_row": "max-h-32",
            "trigger": "min-h-12 px-4 py-2 text-base",
            "input": "text-base",
            "option": "text-base",
            "panel": "max-h-72",
            "pill_size": "lg",
            "remove_icon_size": "sm",
        },
        "xl": {
            "tags_row": "max-h-36",
            "trigger": "min-h-14 px-5 py-2.5 text-lg",
            "input": "text-lg",
            "option": "text-lg",
            "panel": "max-h-80",
            "pill_size": "xl",
            "remove_icon_size": "sm",
        },
    },
}
