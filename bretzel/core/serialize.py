"""Node tree → HTML string.

The single canonical path from a ``Node`` to a serialized document. Pure
function : no I/O, no mutation, no side-effects.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from bretzel.core.escape import escape_html, serialize_attrs
from bretzel.core.tree import Element, FragmentNode, HtmlNode, LaterNode, Node, TextNode

# HTML5 void elements — emitted as ``<tag attrs/>`` with no closing tag and
# no children. Any children passed alongside are silently ignored at the
# moment of writing ; we may upgrade to a ``ValueError`` once components
# stop relying on the lenient behaviour.
VOID_ELEMENTS: frozenset[str] = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }
)


#: An element's name: a letter, then letters, digits or ``-`` (custom
#: elements: ``bz-calendar``, ``iconify-icon``).
_TAG_NAME = re.compile(r"[A-Za-z][A-Za-z0-9-]*")


def serialize(node: Node, later: Callable[[LaterNode], str] | None = None) -> str:
    """Render a ``Node`` tree to an HTML string.

    Dispatch table :

    - :class:`Element` whose tag is in :data:`VOID_ELEMENTS` →
      ``<tag attrs/>`` with no closing tag and no children.
    - Any other :class:`Element` → ``<tag attrs>children</tag>``.
    - :class:`TextNode` → :func:`escape_html` of the content.
    - :class:`HtmlNode` → the payload, **verbatim** (the documented escape hatch).
    - :class:`FragmentNode` → its children concatenated, no surrounding wrapper.

    Unknown :class:`Node` subclasses raise :class:`TypeError` — extending
    the framework with new node kinds requires updating this dispatcher.

    ``later`` writes a :class:`LaterNode` in its place instead — what it
    returns — and keeps it for after (a full page, ``render/later.py``).
    Not inside a ``<template>``: its content is out of the document, so a
    place written there could never be found to put the piece back.
    """
    if later is not None and isinstance(node, LaterNode):
        return later(node)

    if isinstance(node, Element):
        # ⚠️ The tag is written as is: it must be a NAME, or a tag built
        # from a value such as ``"h1><img onerror=…><h1"`` writes a real
        # ``<img>``. Every element passes here.
        if not _TAG_NAME.fullmatch(node.tag):
            raise ValueError(f"{node.tag!r} is not an HTML tag name.")
        attrs = serialize_attrs(node.attrs)
        if node.tag in VOID_ELEMENTS:
            return f"<{node.tag}{attrs}/>"
        within = None if node.tag == "template" else later
        inner = "".join(serialize(child, within) for child in node.children)
        return f"<{node.tag}{attrs}>{inner}</{node.tag}>"

    if isinstance(node, TextNode):
        return escape_html(node.content)

    if isinstance(node, HtmlNode):
        return node.html

    if isinstance(node, FragmentNode):
        return "".join(serialize(child, later) for child in node.children)

    raise TypeError(f"Cannot serialize unknown Node type : {type(node).__name__}")
