"""Node tree → HTML string.

The single canonical path from a ``Node`` to a serialized document. Pure
function : no I/O, no mutation, no side-effects.
"""

from __future__ import annotations

from bretzel.core.escape import escape_html, serialize_attrs
from bretzel.core.tree import Element, FragmentNode, HtmlNode, Node, TextNode

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


def serialize(node: Node) -> str:
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
    """
    if isinstance(node, Element):
        attrs = serialize_attrs(node.attrs)
        if node.tag in VOID_ELEMENTS:
            return f"<{node.tag}{attrs}/>"
        inner = "".join(serialize(child) for child in node.children)
        return f"<{node.tag}{attrs}>{inner}</{node.tag}>"

    if isinstance(node, TextNode):
        return escape_html(node.content)

    if isinstance(node, HtmlNode):
        return node.html

    if isinstance(node, FragmentNode):
        return "".join(serialize(child) for child in node.children)

    raise TypeError(f"Cannot serialize unknown Node type : {type(node).__name__}")
