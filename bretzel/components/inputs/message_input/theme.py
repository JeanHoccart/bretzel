"""Default :class:`MessageInput` theme — one field frame that lights up whole.

Laid out as a single column: the author's chips, the joined files, the
text, the bar. Each row hides itself when empty (``empty:hidden``), so a
box with nothing joined is the text and its bar only. The text has no
frame of its own: the BOX is the field — the very frame of ``ui.input``
with an affix (``prefix_root``: ``rounded-field``, its border, its focus
ring), so a message box and a search field read as one family. The
buttons in it are ``ui.icon_button`` as shipped: no class of ours on
them.

The joined files are :class:`FileUpload`'s own markup, through a private
subclass whose root steps aside (``message_input._Attachments``).
"""

from __future__ import annotations

from typing import Any

MESSAGE_INPUT_THEME: dict[str, Any] = {
    "slots": {
        "root": (
            "bz-message-input bz-c-primary flex flex-col w-full min-w-0 rounded-field "
            "border-(length:--bz-stroke) border-text/10 "
            "bg-interface transition duration-200 "
            # Lit while one TYPES, not whenever the focus is inside: on
            # the round button, its own ring says where the keyboard is —
            # two rings at once read as two fields.
            "has-[textarea:focus]:border-(--bz-solid) "
            "has-[textarea:focus]:ring-2 has-[textarea:focus]:ring-(--bz-focus-soft) "
            "has-[textarea:focus]:ring-offset-2 has-[textarea:focus]:ring-offset-background"
        ),
        "top": "flex flex-wrap items-center gap-1.5 px-3 pt-3 empty:hidden",
        "field": (
            "block w-full resize-none border-0 bg-transparent px-4 py-3 text-sm text-text "
            "placeholder:text-muted/60 outline-none field-sizing-content min-h-[4.5rem] "
            "max-h-60 overflow-y-auto disabled:cursor-not-allowed disabled:opacity-50"
        ),
        "bar": "flex items-center gap-1 px-2 pb-2",
        "count": "px-1 text-xs tabular-nums text-muted",
        # The microphone's own wrapper, not the button: shown only where
        # the browser can dictate (the runtime marks ``<html>``), so a
        # morph re-rendering it changes nothing; it pulses while it listens.
        "voice": (
            "hidden [[data-bz-can-dictate]_&]:contents "
            "[&:has([data-listening=true])_button]:animate-pulse"
        ),
    },
}

#: A tool is a ghost :class:`IconButton`; its look is the button's.
MESSAGE_INPUT_TOOL_THEME: dict[str, Any] = {
    "slots": {
        "root": "",
    },
}
