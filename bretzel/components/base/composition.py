"""Operations on the rendered tree and on where a component sits in it."""

from __future__ import annotations

from collections.abc import Iterable
from contextvars import ContextVar
from typing import Any

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.theme_values import _ui_name_for_error
from bretzel.core.tracking import TRACKER
from bretzel.core.tree import Element, Node


def unwrap_transparent(child: Any, owner: Any = None) -> tuple[Any, Any]:
    """``(the real child, what gives it back its wrapper)``.

    The problem it solves
    ---------------------
    Several containers treat their children **by type**: ``ui.tabs``
    looks for ``Tab``, ``ui.stepper`` for ``Step``, ``ui.accordion`` for
    ``AccordionItem``, ``ui.sidebar`` for its title and its footer. Yet a
    child is very often WRAPPED — in a ``@refreshable`` zone (to refresh
    itself) or in a ``ui.fragment``. The wrapper is not an instance of
    what it contains, so the sorting misses it.

    The wrapper is already transparent to LAYOUT (the zone fuses into its
    only child, or renders as ``display:contents`` — cf.
    ``render/fusion.py``). It was not transparent to IDENTITY, and that
    cost, in silence:

    ==================  ==========================================
    ``ui.tabs``         the wrapped tab **disappears** from the bar
    ``ui.stepper``      the step **disappears**
    ``ui.accordion``    the item loses its **header** and its label
    ``ui.sidebar``      the footer fell **into the scrolling zone**
    ``ui.toggle_group`` **raises** — the only loud one
    ==================  ==========================================

    Why it ALSO returns a rewrapping function
    -------------------------------------------
    One cannot simply throw the wrapper away: a zone's wrapper carries
    its ``bz-id``, the target HTMX aims at to refresh it. A parent that
    rendered the child bare would produce a correct tab… that would never
    refresh again. So the parent composes the child as before, then gives
    its identity back to the produced node ::

        real, rewrap = unwrap_transparent(child)
        node = real._render_in_tabs(...)   # the parent composes
        node = rewrap(node)                # the zone dresses again

    On a bare child, ``rewrap`` is the identity — the caller has no
    branch to write.

    ⚠️ **A wrapper with several children is NOT traversed.** It is
    rendered as-is, as before. A parent that sorts cannot cut a node in
    two, and guessing which of the three children is "the real one" would
    be deciding in the caller's place. A zone that contains a tab AND
    something else must be split by whoever writes it.

    A zone inside a parent that COMPOSES its children is refused
    ---------------------------------------------------------------
    The rewrap holds for the PAGE render only.
    When the zone refreshes alone, its fragment is rendered without the
    parent, so a parent that draws its children its own way — ``ui.tabs``
    makes a tab a button of its bar, with its index and its bindings —
    sees them come out bare: the tab leaves the bar, the step disappears,
    the toggle button raises. Nothing on the server can redo that
    composition, since the parent is built in the middle of a page
    function. Such a parent says so with ``_COMPOSES_CHILDREN = True``
    and is passed as ``owner``; a zone among its children is refused, and
    the message says to put the zone around the parent.
    ``ui.sidebar`` only PLACES its children — it renders them as they are
    — so a zone there refreshes fine and is still traversed.
    """
    if owner is not None and getattr(type(child), "IS_ZONE", False) \
            and getattr(type(owner), "_COMPOSES_CHILDREN", False):
        name = f"ui.{_ui_name_for_error(owner)}"
        raise ComponentUsageError(
            f"{name} draws its children itself, so a @refreshable zone "
            "directly inside it cannot redraw alone: the first time it "
            "refreshes, its fragment comes out without "
            f"{name} around it and the child is lost.\n"
            f"  Put the zone AROUND {name} — the whole {name} redraws, and "
            "only what changed is sent."
        )
    if not getattr(type(child), "IS_TRANSPARENT_WRAPPER", False):
        return child, _identity
    kids = list(getattr(child, "_children", ()) or ())
    if len(kids) != 1:
        return child, _identity
    return kids[0], getattr(child, "_rewrap", _identity)


def _identity(node: Any) -> Any:
    return node


#: The HTML attributes whose MEANING is bound to a specific tag, with the
#: list of tags where they have one. Closed and short on purpose: only
#: what changes meaning (or no longer has one) elsewhere goes in, not
#: everything that is "unusual".
TAG_BOUND_ATTRS: dict[str, frozenset[str]] = {
    # On an ``<a>``, ``type`` is a MIME-type hint about the target — not
    # the nature of a button.
    "type": frozenset({"button", "input", "ol", "link", "script", "style"}),
    "href": frozenset({"a", "link", "area", "base"}),
    "src": frozenset({
        "img", "script", "iframe", "video", "audio", "source",
        "embed", "track", "input",
    }),
    "alt": frozenset({"img", "area", "input"}),
    "for": frozenset({"label", "output"}),
    "target": frozenset({"a", "area", "form", "base"}),
}


def drop_tag_bound_attrs(
    tag: str, attrs: dict[str, Any], *, spare: Iterable[str] = ()
) -> None:
    """Remove from ``attrs`` what no longer means anything under ``tag``.

    A component declares its props against its ``DEFAULT_TAG``, and
    several have a non-``None`` default that therefore always comes out:
    ``Button.type`` is ``"button"``, ``Image.alt`` is mandatory. When the
    tag changes — through the universal ``tag=`` kwarg, or because a prop
    implies it (``ui.button(href=…)`` and ``ui.card(href=…)`` render an
    ``<a>``) — those attributes would stay: a ``type="button"`` on
    something that no longer is a button.

    Called at the end of ``Component.emit_attrs`` — the only place where
    the tag and the attribute bag meet for the whole catalogue. Here and
    not there because the choke point is under ratchet: what is a shared
    primitive lives in this file.

    ``spare`` lists what the caller wrote THEMSELVES —
    ``attrs={"type": "text/html"}`` on an ``<a>`` is a real MIME type,
    and the raw escape hatch has the last word everywhere else (cf.
    ``merge_attr``'s precedence contract). We only remove what the
    component produced on its own.

    ⚠️ Two components set their attribute **after** ``emit_attrs``
    (``menu_item`` its ``type``, ``image`` its ``alt``), so out of reach
    from here: they carry their own guard. That is why the
    ``test_a_changed_tag_drops_what_it_cannot_carry`` gate reads the
    RENDER and not this table.
    """
    spared = set(spare)
    for name, tags in TAG_BOUND_ATTRS.items():
        if name in attrs and name not in spared and tag not in tags:
            del attrs[name]


def _append_class(node: Node, extra: str) -> Node:
    """``node`` with ``extra`` added to its ``class``."""
    if not isinstance(node, Element):
        return node
    current = str(node.attrs.get("class", "")).strip()
    return Element(
        tag=node.tag,
        attrs={**node.attrs, "class": f"{current} {extra}".strip()},
        children=node.children,
    )


def zone_of_children(parent: Any) -> Any:
    """The ``@refreshable`` render a child of ``parent`` belongs to: the
    zone itself under its section, the parent's own zone elsewhere,
    ``None`` outside any zone (a root that is not a component, a page)."""
    if getattr(type(parent), "IS_ZONE", False):
        return parent
    return getattr(parent, "_zone", None)


#: The component whose ``render()`` runs, and how deep the parent stack was
#: when it started. A component built in there with no parent opened since
#: — a dialog's close button, a datatable's table, the input a column's
#: ``render=`` returns — is named under THAT component
#: (:func:`parent_to_name_under`).
#:
#: Falling back to ``root`` would give ``root_icon_button_0``, a counter
#: that the refresh of a zone starts again. Two unrelated nodes would share
#: an id, and idiomorph would pair them; the same node would also change id
#: with the path it arrived by (``root_`` on load, the zone's seed after a
#: navigation). Gate: ``tests/consistency/test_a_built_child_is_named_under_its_maker.py``.
_MAKER: ContextVar[tuple[Any, int] | None] = ContextVar("bretzel_maker", default=None)


def parent_to_name_under(ctx: Any) -> Any:
    """The component a new one takes its id under: the one rendering, if
    nothing was opened since its render began; else the open parent."""
    maker = _MAKER.get()
    if maker is not None and len(ctx.parent_stack) <= maker[1]:
        return maker[0]
    return ctx.parent_stack[-1] if ctx.parent_stack else None


def render_in_its_zone(component: Any, render: Any) -> Any:
    """``render(component)``, what it reads going to the component's zone,
    and what it builds named under it (``_MAKER``).

    A component remembers its zone when it is attached (``add_child``).
    It usually renders inside that zone's recording; when it does not —
    a container (``ui.tabs``, ``ui.stepper``…) composes a zone's child
    outside the zone's own flattening, a parent renders it as a slot —
    the zone's recording is reopened, so a read at render (a table's
    ``rows=``) is still the zone's. Without it, the zone would follow too
    little and freeze without a word.
    """
    from bretzel.render.context import maybe_current_context

    ctx = maybe_current_context()
    token = _MAKER.set((component, len(ctx.parent_stack) if ctx is not None else 0))
    try:
        zone = component._zone
        if zone is None or zone is TRACKER.recording_owner():
            return render(component)
        with zone.learning():
            return render(component)
    finally:
        _MAKER.reset(token)
