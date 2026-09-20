"""No-div-soup fusion : attach ``bz-id`` to the natural root.

Refreshable / partial regions need a stable, addressable root so HTMX
and idiomorph can target them. Wrapping every region in an extra
``<div bz-id=…>`` works but pollutes the DOM. Fusion looks at what the
inner render produced :

- A *single* :class:`Element` root → splice the framework attributes
  into its existing ``attrs``.
- Multiple roots / non-Element / a fragment → wrap them all in a
  ``<div>`` carrying the framework attributes.

The transform is a pure function over immutable nodes — no mutation,
no contextual modifier stack, just a fresh tree returned.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from bretzel.core.tree import Element, FragmentNode, Node
from bretzel.runtime.protocol import BZ_ID_ATTR


class FusionConflict(ValueError):  # noqa: N818 — domain term, not a generic Error
    """Kept as a public name for backwards compatibility.

    Earlier drafts raised this when a candidate single-root already
    carried a ``bz-id``. Reality : every :class:`Component` stamps its
    own id at render time, and that id is the per-component identity
    morph relies on — distinct from the refreshable section's id.
    Fusion now wraps in that case instead of raising, so this class is
    no longer thrown by the framework. Apps may still raise it from
    their own code if they want the old discipline.
    """


def _flatten_fragments(nodes: Iterable[Node]) -> list[Node]:
    """Expand any top-level :class:`FragmentNode` into its children, recursively.

    A fragment serialises as the concatenation of its children with no
    surrounding wrapper, so for fusion purposes a fragment acts as if
    its contents were inlined where the fragment stands.
    """
    out: list[Node] = []
    for node in nodes:
        if isinstance(node, FragmentNode):
            out.extend(_flatten_fragments(node.children))
        else:
            out.append(node)
    return out


def fuse_or_wrap(
    nodes: Iterable[Node],
    *,
    bz_id: str,
    extra_attrs: dict[str, Any] | None = None,
    wrapper_tag: str = "div",
) -> Element:
    """Apply the no-div-soup rule and return one HTML element."""
    flat = _flatten_fragments(nodes)
    framework_attrs = _framework_attrs(bz_id, extra_attrs)

    # Single Element root WITHOUT an existing bz-id → splice in place.
    if (
        len(flat) == 1
        and isinstance(flat[0], Element)
        and BZ_ID_ATTR not in flat[0].attrs
    ):
        root = flat[0]
        merged_attrs = {**root.attrs, **framework_attrs}
        return Element(tag=root.tag, attrs=merged_attrs, children=root.children)

    # Otherwise — wrap (multi-root, non-Element, or inner already
    # carries its own bz-id which we mustn't clobber).
    #
    # ``display:contents``: the box disappears, the ELEMENT stays. A zone
    # is a TRANSPORT boundary — HTMX targets its ``id``, idiomorph finds
    # it again — and none of that asks for a box. As long as it had one,
    # its N children counted as ONE in the parent's layout: the ``gap``
    # stopped at it, but so did ``align``, ``justify``, ``flex-1``, which
    # now reach the real elements instead of the parcel.
    #
    # Why NOT a gap of our own: we would have to pick its value, and
    # under a ``vstack(gap="lg")`` we would render "lg outside, md
    # inside" — one inconsistency for another. ``contents`` invents no
    # policy, it lets the parent's through.
    #
    # ⚠️ On THIS branch only — the splice branch merges the attrs INTO
    # the caller's element.
    #
    # Measurements, counter-examples and the why of the guard above:
    # ``tests/consistency/test_zone_box_is_transparent.py``.
    wrapper_attrs = dict(framework_attrs)
    wrapper_attrs.setdefault("class", "contents")
    return Element(
        tag=wrapper_tag,
        attrs=wrapper_attrs,
        children=tuple(flat),
    )


def _framework_attrs(
    bz_id: str,
    extra: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compose the attribute dict spliced onto the fused element.

    Order matters for HTML output stability ; we insert framework
    attrs first, then user extras (so cosmetic classes win in source
    order without overriding the framework's own).
    """
    out: dict[str, Any] = {BZ_ID_ATTR: bz_id, "id": bz_id}
    if extra:
        for k, v in extra.items():
            # Don't let user extras stomp the framework keys silently —
            # a literal "id"/"bz-id" would defeat the fusion contract.
            if k in (BZ_ID_ATTR, "id"):
                continue
            out[k] = v
    return out
