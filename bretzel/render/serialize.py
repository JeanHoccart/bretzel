"""Public helper : :class:`Component` → serialized HTML string.

Pretty-prints the component's render tree for inspection use cases
(playground test benches, doc snippets). Element children are broken
onto their own indented lines ; opening tags whose single-line form
exceeds the width budget split their attributes one-per-line.

Safe to call from inside a live page render — the helper detaches the
component from its auto-registered parent before serializing so the
same instance never ends up rendered twice (once visually, once via
the inspection helper). Outside a request context, wrap calls in
:func:`bretzel.components.base.testing.render_isolated`.

If you need the raw single-line form (e.g. a unit test asserting on
exact byte-level output), call :func:`bretzel.core.serialize.serialize`
on ``component.render()`` directly — that path stays untouched.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bretzel.core.escape import escape_html, serialize_attrs
from bretzel.core.serialize import VOID_ELEMENTS
from bretzel.core.tree import Element, FragmentNode, HtmlNode, Node, TextNode

if TYPE_CHECKING:
    from bretzel.components.base import Component


_INDENT = "  "
_OPENING_TAG_WIDTH = 100  # split attributes one-per-line beyond this


def serialize_html(component: Component) -> str:
    """Render *component* in isolation and return pretty HTML."""
    # Deferred — bretzel.components.base depends on bretzel.render,
    # so a top-level import deadlocks.
    from bretzel.components.base import Component as _Component
    from bretzel.render.context import maybe_current_context

    # Page-side callers build the component inside a ``with`` block, so
    # __init__ auto-attached it to the active parent. Without detach,
    # the component would render twice : once visually, once here.
    _Component._detach_from_parent(component)

    # ⚠️ Enter RENDER MODE around ``render()`` — as ``_render_children``
    # does during the normal walk. Without it, a Component built INSIDE
    # *component*'s ``render()`` (a close ×, a chevron, a themed icon
    # from a string) registers itself with the active parent and LEAKS
    # onto ``root_children``: it renders a 2nd time, orphaned, in the
    # page that called ``serialize_html``. That is the root of the
    # playground's stray × (2026-07-18) — a caller rendering outside
    # render mode, not a faulty component. Save/restore like
    # ``_render_children``: a 2nd serialize in the same request must not
    # find the flag stuck.
    ctx = maybe_current_context()
    previous = ctx.is_rendering if ctx is not None else None
    if ctx is not None:
        ctx.is_rendering = True
    try:
        return _format_node(component.render(), depth=0)
    finally:
        if ctx is not None:
            ctx.is_rendering = bool(previous)


def _format_node(node: Node, depth: int) -> str:
    if isinstance(node, TextNode):
        return escape_html(node.content)

    if isinstance(node, HtmlNode):
        # Raw HTML escape hatch — emit verbatim, no re-indent (the
        # caller already chose this content and we don't want to
        # second-guess its whitespace).
        return node.html

    if isinstance(node, FragmentNode):
        return "\n".join(_format_node(c, depth) for c in node.children)

    if isinstance(node, Element):
        return _format_element(node, depth)

    raise TypeError(f"Cannot pretty-print unknown Node type : {type(node).__name__}")


def _format_element(node: Element, depth: int) -> str:
    pad = _INDENT * depth
    # The attributes are serialised by ``_format_opening``, on each of
    # the four branches below. The line that prepared them here therefore
    # computed them a SECOND time, for a variable nothing has read since
    # the opening went through that helper.

    # Void elements self-close, no children to walk.
    if node.tag in VOID_ELEMENTS:
        return _format_opening(node, depth, void=True)

    if not node.children:
        return f"{_format_opening(node, depth)}</{node.tag}>"

    # All-textual children → keep inline so short labels stay on one
    # line. We treat ``HtmlNode`` as inline too — Pygments-highlighted
    # blocks live inside Code's <code> and shouldn't be split.
    if all(isinstance(c, (TextNode, HtmlNode)) for c in node.children):
        inner = "".join(_format_node(c, 0) for c in node.children)
        return f"{_format_opening(node, depth)}{inner}</{node.tag}>"

    # At least one Element child → break onto multiple lines.
    lines = [_format_opening(node, depth)]
    for child in node.children:
        lines.append(_format_node(child, depth + 1))
    lines.append(f"{pad}</{node.tag}>")
    return "\n".join(lines)


def _format_opening(node: Element, depth: int, *, void: bool = False) -> str:
    pad = _INDENT * depth
    inner_pad = _INDENT * (depth + 1)
    attrs_str = serialize_attrs(node.attrs)
    closing = "/>" if void else ">"
    single_line = f"{pad}<{node.tag}{attrs_str}{closing}"

    # Compact form when the opening tag fits, or has zero attributes
    # (nothing to spread across multiple lines).
    if len(single_line) <= _OPENING_TAG_WIDTH or not node.attrs:
        return single_line

    # Split : tag on its own line, one attribute per line.
    parts = [f"{pad}<{node.tag}"]
    for key, value in node.attrs.items():
        attr_chunk = serialize_attrs({key: value}).strip()
        parts.append(f"{inner_pad}{attr_chunk}")
    # Closing bracket aligns with the opening ``<``.
    parts.append(f"{pad}{closing}")
    return "\n".join(parts)


__all__ = ["serialize_html"]
