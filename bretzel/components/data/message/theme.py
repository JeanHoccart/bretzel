"""Default :class:`Message` and :class:`MessageList` themes.

A message is a row: its avatar, then a column (its author, its files,
its words, the line under them). ``side="end"`` reverses the row, so
mine sit on the far side with their avatar; each side stops 15 % short
of the other edge (``pe-`` / ``ps-``, logical: a right-to-left page
mirrors them), so a thread reads staggered. A bubble
is sized to its words and tinted, not filled — its ink stays the page's,
readable in both themes: mine in the accent, the others' neutral.

In a list, the messages are spaced by the thread's gap, and a grouped
one (same side and author as the one before) sits closer.
"""

from __future__ import annotations

from typing import Any

MESSAGE_THEME: dict[str, Any] = {
    "slots": {
        "root": (
            "bz-message group flex w-full min-w-0 items-start gap-3 "
            "data-[side=end]:flex-row-reverse data-[side=start]:pe-[15%] "
            "data-[side=end]:ps-[15%] data-[grouped=true]:-mt-3"
        ),
        "avatar": "grid size-8 shrink-0 place-items-center",
        "column": (
            "flex min-w-0 flex-1 flex-col items-start gap-1 text-sm text-text "
            "group-data-[side=end]:items-end"
        ),
        "bubble": "flex w-fit max-w-full flex-col gap-2 rounded-box px-4 py-3",
        "bubble_end": "bz-c-primary bg-(--bz-bg)",
        "bubble_start": "bg-text/5",
        "author": "text-xs font-semibold text-muted",
        "files": "flex flex-wrap gap-1.5",
        "plain": "whitespace-pre-wrap break-words",
        "foot": "flex items-center gap-1 text-xs text-muted",
        "error": "font-medium text-error",
    },
}

MESSAGE_LIST_THEME: dict[str, Any] = {
    "slots": {
        # It scrolls itself: ``ui.pane``'s own classes (``flex-1`` in a
        # flex column, ``h-full`` in a block of fixed height — without it
        # the list grows to its content and never scrolls).
        "root": (
            "bz-message-list relative flex h-full min-h-0 w-full flex-1 flex-col "
            "overflow-y-auto [&>*]:shrink-0"
        ),
        "thread": "flex flex-col gap-4 py-4",
        # « Back to the bottom »: shown while the reader is up the thread
        # (the runtime marks the list ``data-away``).
        "bottom": (
            "pointer-events-none sticky bottom-3 flex justify-center opacity-0 "
            "transition-opacity [[data-away]>&]:pointer-events-auto "
            "[[data-away]>&]:opacity-100"
        ),
        # Under the button, opaque and lifted: it floats over the thread.
        "backing": "rounded-field bg-background shadow-md",
    },
}
