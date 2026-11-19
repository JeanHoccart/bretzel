"""A full page in two times: what shows first, what the page hides after.

A closed dialog's panel, a menu's panel: the page carries them so they open
at once, but nothing of them shows at load. Written where they stand, the
browser parses, styles and wires them before it can show anything else —
on a mail app's main page, more than half of it.

So a full page writes each of them (a :class:`~bretzel.core.tree.LaterNode`,
set by the component that knows it is closed) as an empty ``<template>``
that keeps its place, and the piece itself at the end of ``<body>``, after
the runtime's scripts. The runtime boots on what shows, then puts each piece
back when the document is complete (``runtime/_src/index.js``): the DOM is
then the one the page would have had in one piece, which the zone
fingerprints, computed before on the whole tree, describe.

Everything stays in the page and in the same response — opening a dialog
never waits for the server. Only the full page splits: a partial
navigation or an action is swapped whole by htmx, its pieces stay in place.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from bretzel.core.serialize import serialize
from bretzel.core.tree import LaterNode, Node
from bretzel.runtime.protocol import LATER_PIECE_ATTR, LATER_PLACE_ATTR


def visible_first(nodes: Iterable[Node]) -> tuple[str, list[str]]:
    """``(what shows, the pieces)``: the HTML of ``nodes`` with each hidden
    piece replaced by its place, and the HTML of each piece, in the order
    of their places."""
    pieces: list[LaterNode] = []

    def place(node: LaterNode) -> str:
        pieces.append(node)
        return place_of(len(pieces) - 1)

    shown = "".join(serialize(node, place) for node in nodes)
    return shown, [serialize(piece) for piece in pieces]


def place_of(index: int) -> str:
    """The empty ``<template>`` that keeps piece ``index``'s place."""
    return f'<template {LATER_PLACE_ATTR}="{index}"></template>'


def after_all(pieces: list[str]) -> str:
    """The pieces as they close ``<body>``, each naming its place."""
    return "".join(
        f'<template {LATER_PIECE_ATTR}="{index}">{piece}</template>'
        for index, piece in enumerate(pieces)
    )


_PIECE = re.compile(rf'<template {LATER_PIECE_ATTR}="(\d+)">')


def whole_page(html: str) -> str:
    """A full page as the browser holds it once loaded: each piece back in
    its place (``takeLater`` in ``index.js``), the inverse of the split.

    For the gates and benches that compare a served page with a render in
    one piece. A place missing or written twice raises — the browser would
    lose the piece in silence.
    """
    while (found := _PIECE.search(html)) is not None:
        depth, end = 1, found.end()
        while depth:
            inner, close = html.find("<template", end), html.find("</template>", end)
            if close < 0:
                raise ValueError(f"piece {found.group(1)} is never closed")
            if 0 <= inner < close:
                depth, end = depth + 1, inner + len("<template")
            else:
                depth, end = depth - 1, close + len("</template>")
        piece = html[found.end(): end - len("</template>")]
        html = html[: found.start()] + html[end:]
        place = place_of(int(found.group(1)))
        if html.count(place) != 1:
            raise ValueError(f"place {found.group(1)} is written {html.count(place)} times")
        html = html.replace(place, piece)
    return html


__all__ = ["after_all", "place_of", "visible_first", "whole_page"]
