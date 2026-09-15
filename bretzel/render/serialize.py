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

    # ⚠️ Entrer en RENDER MODE autour de ``render()`` — comme le fait
    # ``_render_children`` pendant le walk normal. Sans ça, un Component
    # construit DANS le ``render()`` de *component* (× de fermeture,
    # chevron, icône thémée d'une string) s'auto-enregistre au parent
    # actif et FUIT sur ``root_children`` : il rend une 2ᵉ fois, orphelin,
    # dans la page qui appelle ``serialize_html``. C'est la racine du ×
    # parasite du playground (2026-07-18) — un caller qui rendait hors
    # render-mode, pas un composant fautif. Save/restore comme
    # ``_render_children`` : un 2ᵉ serialize dans la même requête ne doit
    # pas voir le flag coincé.
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
    # Les attributs sont sérialisés par ``_format_opening``, sur chacune
    # des quatre branches ci-dessous. La ligne qui les préparait ici les
    # calculait donc une SECONDE fois, pour une variable que plus rien ne
    # lisait depuis que l'ouverture est passée par ce helper.

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
