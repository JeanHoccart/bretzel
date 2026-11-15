"""Default :class:`Editor` theme — the frame of a field, a bar on top.

``surface`` (the default): the BOX is the field, as for
:class:`~bretzel.components.inputs.message_input.MessageInput` — the frame
of ``ui.input`` (``rounded-field``, its border, its focus ring lit while
one types), the bar inside it at the top, the text under it.

``ghost``: neither background nor frame — the container around it (a
card, the lines of a mail) structures the screen. The mouse puts the caret
in it and nothing else; the keyboard brings the usual ring. A
``contenteditable`` matches ``:focus-visible`` on a click too, so the
ring reads the page's own mark of a keyboard user (``data-bz-keyboard`` on
``<html>``, set by ``helpers.js`` on Tab and taken off by a pointer).

The buttons of the bar are ``ui.icon_button`` as shipped; the bar only
says how a PRESSED one reads (``aria-pressed``: the B is lit while the
cursor is in bold) — the wash a soft button has at rest.

The text has one format, the theme's: ``text-sm``, single line spacing,
a line break that adds nothing (``Enter``), a paragraph three quarters of a line apart
(``Enter`` twice). Lists are indented by their marker, nested lists by
one more step. Nothing lets the user pick a font, a size or a colour.
"""

from __future__ import annotations

from typing import Any

EDITOR_THEME: dict[str, Any] = {
    "slots": {
        "root": (
            "bz-editor bz-c-primary flex flex-col w-full min-w-0 rounded-field "
            "transition duration-200 "
            "data-disabled:opacity-50 data-disabled:cursor-not-allowed"
        ),
        "toolbar": (
            "flex flex-wrap items-center gap-0.5 px-1.5 py-1 "
            "[&_[aria-pressed=true]]:bg-(--bz-bg) "
            "[&_[aria-pressed=true]]:text-(--bz-solid)"
        ),
        # A thin rule between the formatting commands and the app's tools.
        "separator": "mx-1 h-5 w-0 border-l-(length:--bz-stroke) border-line",
        # The text. ``whitespace-pre-wrap`` is ProseMirror's requirement
        # (it warns without it); the descendants' look is the one format.
        "surface": (
            "relative block w-full min-h-24 px-4 py-3 text-sm leading-normal text-text "
            "outline-none whitespace-pre-wrap break-words cursor-text "
            # Blocks three quarters of a line apart — the space after a paragraph in
            # Word or Outlook —, and nothing inside a list item: a
            # nested list follows its item's line directly (the preflight
            # already zeroes the margins of ``p``, ``ul`` and ``ol``).
            "[&>*+*]:mt-[0.75lh] "
            "[&_ul]:list-disc [&_ol]:list-decimal [&_ul]:ps-6 [&_ol]:ps-6 "
            "[&_a]:text-(--bz-solid) [&_a]:underline [&_a]:underline-offset-2 [&_a]:cursor-pointer "
            "[&_strong]:font-semibold "
            # The placeholder: the runtime marks the empty surface.
            "data-empty:before:pointer-events-none data-empty:before:absolute "
            "data-empty:before:text-placeholder "
            "data-empty:before:content-[attr(data-bz-placeholder)]"
        ),
        # The link panel: an address field and its two buttons.
        "link": "flex items-center gap-2 w-80 max-w-[85vw]",
    },
    "variants": {
        "surface": (
            "bg-interface border-(length:--bz-stroke) border-line "
            # Lit while one TYPES, not while a button of the bar has the
            # focus: that one draws its own ring (MessageInput's rule).
            "has-[[contenteditable]:focus]:border-(--bz-solid) "
            "has-[[contenteditable]:focus]:ring-2 "
            "has-[[contenteditable]:focus]:ring-(--bz-focus-soft) "
            "has-[[contenteditable]:focus]:ring-offset-2 "
            "has-[[contenteditable]:focus]:ring-offset-background "
            "[&>[role=toolbar]]:border-b-(length:--bz-stroke) "
            "[&>[role=toolbar]]:border-line"
        ),
        "ghost": (
            "[[data-bz-keyboard]_&]:has-[[contenteditable]:focus]:ring-2 "
            "[[data-bz-keyboard]_&]:has-[[contenteditable]:focus]:ring-(--bz-focus) "
            "[[data-bz-keyboard]_&]:has-[[contenteditable]:focus]:ring-offset-2 "
            "[[data-bz-keyboard]_&]:has-[[contenteditable]:focus]:ring-offset-background"
        ),
    },
}

#: The look of the field — the same two words as every field of the family.
VARIANTS: tuple[str, ...] = tuple(EDITOR_THEME["variants"])
