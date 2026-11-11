"""Default :class:`Markdown` theme.

Typography classes per HTML element emitted by the mistune renderer. The
wrapper carries ``bz-markdown`` as a marker class for user CSS overrides.
Fenced code blocks borrow :data:`CODE_THEME` (see :mod:`.markdown`) so a
snippet looks identical whether it comes from ``ui.code(...)`` or a fenced
block.

Spacing : block elements carry ``mb-3`` ; headings get a larger ``mt-*`` so
sections breathe ; lists use ``space-y-1`` so nested lists collapse cleanly.
A heading's SIZE and WEIGHT are not here: a ``##`` is a level-2 title, and
takes ``ui.heading``'s scale (:func:`~bretzel.components.primitives.heading.heading.heading_classes`) —
these slots only space it.
The first block's top margin and the last block's bottom one are dropped
by the wrapper: spacing BETWEEN blocks is the text's, spacing AROUND it is
the parent's gap.
A word longer than its line — a URL, most often — breaks rather than
overflowing its column (``break-words``).
"""

from __future__ import annotations

from typing import Any

MARKDOWN_THEME: dict[str, Any] = {
    "slots": {
        # The INK is the container's (``text-current``), not the theme's
        # text colour: in ``ui.card(color="primary")`` the theme's colour
        # would come out dark on indigo, contrast under 4.5. The top-level
        # blocks take 80 % of it, the headings all of it.
        "root": (
            "bz-markdown block w-full break-words "
            "[&>:not(h1,h2,h3,h4,h5,h6,blockquote)]:text-current/80 "
            "[&>:first-child]:mt-0 [&>:last-child]:mb-0"
        ),
        "h1": "mt-6 mb-3",
        "h2": "mt-5 mb-2",
        "h3": "mt-4 mb-2",
        "h4": "mt-3 mb-1",
        "h5": "mt-3 mb-1",
        "h6": "mt-3 mb-1",
        "p": "mb-3 leading-relaxed",
        "ul": "list-disc pl-6 mb-3 space-y-1",
        "ol": "list-decimal pl-6 mb-3 space-y-1",
        "li": "",
        "blockquote": "border-l-(length:--bz-stroke-accent) border-current/20 pl-4 italic mb-3 text-current/70",
        "a": "text-primary underline hover:no-underline",
        # Its own chip (``bg-surface``), so its own ink.
        "code": "px-1 py-0.5 rounded bg-surface border-(length:--bz-stroke) border-text/10 font-mono text-xs text-text/80",
        "hr": "border-t-(length:--bz-stroke) border-current/[0.125] my-4",
        "table": "w-full border-collapse mb-3",
        "th": "border-b-(length:--bz-stroke) border-current/25 px-3 py-2 text-start font-semibold",
        "td": "border-b-(length:--bz-stroke) border-current/[0.125] px-3 py-2",
        "strong": "font-semibold",
        "em": "italic",
        "img": "max-w-full h-auto rounded-box my-3",
        "del": "line-through text-current/75",
    },
}
