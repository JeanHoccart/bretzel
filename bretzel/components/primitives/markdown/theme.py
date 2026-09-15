"""Default :class:`Markdown` theme.

Typography classes per HTML element emitted by the mistune renderer. The
wrapper carries ``bz-markdown`` as a marker class for user CSS overrides.
Fenced code blocks borrow :data:`CODE_THEME` (see :mod:`.markdown`) so a
snippet looks identical whether it comes from ``ui.code(...)`` or a fenced
block.

Spacing : block elements carry ``mb-3`` ; headings get a larger ``mt-*`` so
sections breathe ; lists use ``space-y-1`` so nested lists collapse cleanly.
"""

from __future__ import annotations

from typing import Any

MARKDOWN_THEME: dict[str, Any] = {
    "slots": {
        "root": "bz-markdown block w-full text-text/80",
        "h1": "text-3xl font-bold mt-6 mb-3 text-text",
        "h2": "text-2xl font-semibold mt-5 mb-2 text-text",
        "h3": "text-xl font-semibold mt-4 mb-2 text-text",
        "h4": "text-lg font-semibold mt-3 mb-1 text-text",
        "h5": "text-base font-semibold mt-3 mb-1 text-text",
        "h6": "text-sm font-semibold mt-3 mb-1 text-text",
        "p": "mb-3 leading-relaxed",
        "ul": "list-disc pl-6 mb-3 space-y-1",
        "ol": "list-decimal pl-6 mb-3 space-y-1",
        "li": "",
        "blockquote": "border-l-(length:--bz-stroke-accent) border-text/20 pl-4 italic mb-3 text-text/70",
        "a": "text-primary underline hover:no-underline",
        "code": "px-1 py-0.5 rounded bg-surface border-(length:--bz-stroke) border-text/10 font-mono text-xs",
        "hr": "border-t-(length:--bz-stroke) border-text/10 my-4",
        "table": "w-full border-collapse mb-3",
        "th": "border-b-(length:--bz-stroke) border-text/20 px-3 py-2 text-start font-semibold",
        "td": "border-b-(length:--bz-stroke) border-text/10 px-3 py-2",
        "strong": "font-semibold",
        "em": "italic",
        "img": "max-w-full h-auto rounded-box my-3",
        "del": "line-through text-text/60",
    },
}
