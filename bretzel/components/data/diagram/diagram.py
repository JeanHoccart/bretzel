"""``Diagram`` — a directed graph, laid out in layers on the server.

Usage, tier 1 — you declare only the edges, the nodes follow in their
order of appearance ::

    ui.diagram(edges=[("planning", "planning_engine"),
                      ("tours", "planning_engine"),
                      ("planning_engine", "geo")])

Tier 2 — each node is described, and a node's render is yours ::

    def card(node):
        with ui.card(padding="sm") as c:
            with ui.hstack(gap="sm", align="center"):
                ui.icon(node.icon, color=node.color)
                ui.text(node.label, weight="medium", truncate=True)
        return c

    ui.diagram(
        nodes=[ui.node("geo", label="geo", icon="map-pin", color="warning")],
        edges=[ui.edge("planning", "geo", label="uses", style="dashed")],
        focus=state.selected,
        render=card,
        on_item_click=select,
    )

Why DESCRIPTORS and not subcomponents
---------------------------------------
``ui.tree_node`` exists because containment nests: a ``with`` block says
"inside". A graph does not nest — an edge links any two nodes, and no
``with`` expresses that. And the component owns the loop: it is IT that
breaks the cycles, assigns the layers and decides which nodes are drawn
according to ``focus``. The author therefore has nowhere to write their
markup, hence ``render=`` — the same contract as ``ui.column(render=)``.
Cf. ``Component.COLLECTION_OWNER``.

⚠️ ``render=`` is called back during the flattening of the tree, like a
column's ``render=``: it must be **synchronous**. A coroutine is refused
there by the base layer.

The HTML / SVG split
--------------------
The nodes are absolutely positioned HTML; only the edges live in an
``<svg>`` placed behind them. It is what React Flow settles on, and for
the same reason: a node drawn as ``<rect>`` + ``<text>`` would lose
everything the rest of the framework gives it for free — truncation, the
focus ring, a themed icon, a badge, the tab order. The DOM order follows
the layers, so tabbing follows the reading direction.

The default view
----------------
``focus=None`` shows the whole graph: there is nothing to centre on. As
soon as ``focus`` names a node, the view tightens onto its neighbourhood
at ``depth`` hops — because a real app's graph is dense (22 nodes and 61
edges, measured on an app since removed) and a tangle answers no
question, whereas the neighbourhood answers the one you have: "what
touches this".

The layout itself does not live here:
:mod:`bretzel.components.data.diagram.layout` is pure, with no framework
import, and that is what makes the hard half testable without a browser.
"""

from __future__ import annotations

import functools
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, ClassVar

from bretzel.components.base import (
    Component,
    ComponentUsageError,
    coerce_children,
    reactive_prop,
)
from bretzel.components.base._wiring import (
    activate_keydown,
    hidden_carrier_attrs,
    server_sync_marker,
)
from bretzel.components.base.events import (
    client_event_attr,
    item_action_attrs,
)
from bretzel.components.data.diagram.layout import (
    Metrics,
    keys_from_edges,
    layout,
    neighbourhood,
)
from bretzel.components.data.diagram.theme import DIAGRAM_THEME
from bretzel.core.tree import Element, Node, TextNode
from bretzel.render.context import current_context

#: A click on an interactive child of a node (a button placed by a
#: ``render=``, a link) does NOT fire the node's click.
#:
#: Same construction as ``Table``'s for clickable rows, and for the same
#: parser constraint: HTMX splits ``hx-trigger`` on commas and closes the
#: filter at the first ``]``, so no ``closest('a,button')`` — we combine
#: ``closest()`` calls on one tag each.
_NODE_INTERACTIVE_TAGS = ("button", "a", "input", "select", "textarea", "label")
_NODE_CLICK_GUARD = " && ".join(
    f"!event.target.closest('{tag}')" for tag in _NODE_INTERACTIVE_TAGS
)
_NODE_CLICK_KEYDOWN = activate_keydown("$el.click();")

#: The edge styles, and the name of the theme slot that carries them.
_EDGE_STYLES = {"solid": "edge", "dashed": "edge_flipped"}


# ───────────────────────────────────────────────────────────────────────────
# Descripteurs
# ───────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class GraphNode:
    """Describe one node in a graph."""

    key: str
    label: str = ""
    icon: str | None = None
    color: str | None = None
    badge: str | None = None
    group: str | None = None
    width: float | None = None


@dataclass(frozen=True, slots=True)
class GraphEdge:
    """Describe a directed edge from ``source`` to ``target``."""

    source: str
    target: str
    label: str = ""
    style: str = "solid"
    color: str | None = None


def node(
    key: str,
    *,
    label: str = "",
    icon: str | None = None,
    color: str | None = None,
    badge: str | None = None,
    group: str | None = None,
    width: float | None = None,
) -> GraphNode:
    """Describe a graph node for ``ui.diagram``."""
    return GraphNode(
        key=key, label=label, icon=icon, color=color,
        badge=badge, group=group, width=width,
    )


def edge(
    source: str,
    target: str,
    *,
    label: str = "",
    style: str = "solid",
    color: str | None = None,
) -> GraphEdge:
    """Describe a graph edge for ``ui.diagram``."""
    return GraphEdge(
        source=source, target=target, label=label, style=style, color=color
    )


def _as_pair(item: Any) -> tuple[str, str]:
    """``("a", "b")`` or ``ui.edge("a", "b")`` — the same pair."""
    if isinstance(item, GraphEdge):
        return (item.source, item.target)
    source, target = item
    return (str(source), str(target))


def _as_node(item: Any) -> GraphNode:
    """``"a"`` or ``ui.node("a")`` — the same descriptor."""
    return item if isinstance(item, GraphNode) else GraphNode(key=str(item))


# ───────────────────────────────────────────────────────────────────────────
# Le composant
# ───────────────────────────────────────────────────────────────────────────


class Diagram(Component):
    """Render a server-laid-out directed graph in layers."""

    THEME: ClassVar[dict[str, Any]] = DIAGRAM_THEME
    THEME_KEY: ClassVar[str] = "diagram"
    #: The component owns the loop: cycles broken, layers assigned,
    #: crossings reduced, and ``focus`` even decides WHICH nodes are
    #: drawn. The author cannot write that loop — hence the ``render=``
    #: callback, the only possible entry point.
    COLLECTION_OWNER: ClassVar[str | None] = "component"
    #: ``item_click`` is a REAL event, not a jury-rigged parameter.
    #:
    #: The consequence is not cosmetic: `on_item_click=` now accepts the
    #: three shapes of any framework `on_*` — a server callable, a client
    #: expression string, or a LIST of both. As long as it was not
    #: declared, it accepted only a callable, and the playground template
    #: read "this component has no event" — so no Server events card and
    #: no Client events card.
    #:
    #: ⚠️ The routing stays MANUAL, unlike the common case. The base
    #: layer sets the `hx-post` of a declared event on the ROOT, whereas
    #: here each node carries its own, with its key. `on_item_click` is
    #: therefore a named parameter of the ``__init__`` — the base layer
    #: never sees it go by — and `_click_attrs` does the work. Same
    #: situation as `ui.table`'s `on_item_click`.
    EVENTS: ClassVar[tuple[str, ...]] = ("item_click",)
    IS_CONTAINER: ClassVar[bool] = False
    #: ``value`` = the SELECTED node, and it is ⇄ two-way.
    #:
    #: `client-reactive-surface.md` § *The rule* is explicit at the
    #: test's first step: "does the user edit this value by interacting
    #: with THIS component? … the selection → ⇄ two-way". The client
    #: driver exists — it is the click on a node — so `@refreshable`
    #: alone is not enough.
    #:
    #: ⚠️ This component shipped an EMPTY bindable surface for a day, on
    #: the hunch "pure display". The hunch was wrong and the written rule
    #: said the opposite: a diagram is not a display, it is a SELECTOR.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("value",)

    value: Any = reactive_prop(
        default="", emit_attr=False, writes=True,
        names_field=True,
    )
    size: str = reactive_prop(default="md", emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)

    def __init__(
        self,
        *,
        value: Any = None,
        edges: Iterable[Any] = (),
        nodes: Iterable[Any] = (),
        focus: str | None = None,
        depth: int = 1,
        direction: str = "right",
        render: Callable[[GraphNode], Any] | None = None,
        on_item_click: Callable[..., Any] | str
        | list[Callable[..., Any] | str] | None = None,
        size: str | None = None,
        color: str | None = None,
        empty_text: str = "No graph.",
        empty_icon: str | None = "workflow",
        empty_description: str | None = None,
        empty: Callable[[], Any] | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs.
        super().__init__(value=value, size=size, color=color, **kwargs)
        if direction not in ("right", "down"):
            raise ComponentUsageError(
                f"ui.diagram: direction={direction!r} — expected 'right' "
                f"(the layers are columns) or 'down'."
            )
        self._edges = [e if isinstance(e, GraphEdge) else GraphEdge(*_as_pair(e))
                       for e in edges]
        self._pairs = [_as_pair(e) for e in self._edges]
        declared = [_as_node(n) for n in nodes]
        self._declared = {n.key: n for n in declared}
        # Tier 1: with no ``nodes=``, the keys come from the edges, in
        # their order of first appearance — so deterministic.
        self._keys = (
            [n.key for n in declared] if declared else keys_from_edges(self._pairs)
        )
        self._focus = focus
        self._depth = depth
        self._direction = direction
        self._render = render
        self._click = on_item_click
        self._empty_text = empty_text
        self._empty_icon = empty_icon
        self._empty_description = empty_description
        self._empty = empty
        self._reject_unknown_endpoints()

    def _reject_unknown_endpoints(self) -> None:
        """An edge that cites an undeclared node is refused, by name.

        Only when ``nodes=`` is given: without it the keys COME OUT of
        the edges, so nothing can be unknown. The layout engine, for its
        part, ignores silently — that is the right behaviour for a pure
        function called in a render, but at the component level we can
        name the culprit, so we name it. A missing node otherwise
        produces an amputated drawing you re-read for ten minutes before
        understanding.
        """
        if not self._declared:
            return
        known = set(self._keys)
        missing = sorted(
            {k for pair in self._pairs for k in pair if k not in known}
        )
        if missing:
            raise ComponentUsageError(
                f"ui.diagram: the edges cite {', '.join(missing)}, which "
                f"is not in nodes=. Add the node, fix the key, or remove "
                f"nodes= so the nodes are inferred from the edges."
            )

    def _build_empty(self, size_key: str) -> tuple[Node, ...]:
        """The empty state: ``empty=`` if given, otherwise the automatic one.

        Same API as ``ui.table`` and ``ui.datatable`` — three convenience
        props plus an escape hatch, and both branches go through
        ``coerce_children``. Without it, an ``empty=`` that returns
        ``None`` writes the string ``"None"`` on screen; that is the bug
        ``ui.table`` paid for on 2026-08-18.
        """
        if self._empty is not None:
            return coerce_children(self._empty())

        # `ui.empty_state`, like `ui.table` — not a grey centred text
        # written by hand. It carries the icon, the title hierarchy and
        # the theme's spacing; rewriting them here would give a second
        # version that would drift.
        from bretzel.components.feedback.empty_state import EmptyState

        # ⚠️ `_detach_from_parent` BEFORE `render()`. A Component built
        # in a `render()` registers itself with the ACTIVE parent and
        # leaks when the component is detached — traps.md's "Icon built
        # in render() without detach" trap.
        empty = EmptyState(
            self._empty_text,
            icon=self._empty_icon,
            description=self._empty_description,
            # The empty state follows the diagram's step: without that
            # a `size=` changes NOTHING on an empty graph, which is
            # exactly the dead kwarg this repository hunts.
            size=size_key,
        )
        Component._detach_from_parent(empty)
        return (empty.render(),)

    # ── View selection ──────────────────────────────────────────────────

    def _drawn(self) -> tuple[list[str], list[GraphEdge]]:
        """The nodes and edges actually drawn.

        ``_drawn`` and not ``_visible``: ``visible`` is a universal
        kwarg, and the base layer files its own in ``self._visible``. The
        method overwrote it — the component raised "NoneType is not
        callable" at render, not at construction.

        ``focus=None`` renders everything: there is nothing to centre on.
        Otherwise we tighten onto the neighbourhood — and a ``focus``
        that designates no known node falls back on the whole graph
        rather than on an empty drawing, because a stale key in an
        interface state is a commonplace accident (a renamed feature, an
        id kept in session) and a blank screen says nothing about it.
        """
        if self._focus is None or self._focus not in set(self._keys):
            return list(self._keys), list(self._edges)
        keep = neighbourhood(self._focus, self._pairs, depth=self._depth)
        keys = [k for k in self._keys if k in keep]
        edges = [e for e in self._edges if e.source in keep and e.target in keep]
        return keys, edges

    def _adjacency(
        self, keys: list[str], edges: list[GraphEdge]
    ) -> dict[str, list[str]]:
        """``{key: itself + what touches it}``, both ways.

        Computed ONCE at render and baked into the DOM: that is what
        makes the highlighting free on the client side. The browser has
        nothing to walk, it reads an array.

        Sorted, because the HTML of two renders of the same graph must be
        byte-identical — otherwise idiomorph replaces instead of merging,
        and any non-regression comparison becomes noise.
        """
        near: dict[str, set[str]] = {k: {k} for k in keys}
        for edge in edges:
            if edge.source in near and edge.target in near:
                near[edge.source].add(edge.target)
                near[edge.target].add(edge.source)
        return {k: sorted(v) for k, v in near.items()}

    # ── Rendu ───────────────────────────────────────────────────────────

    def _node_body(self, spec: GraphNode, step: dict, slots: dict) -> tuple[Node, ...]:
        """A node's content — the author's ``render=``, or the default."""
        if self._render is not None:
            return coerce_children(self._render(spec))

        from bretzel.components.feedback.badge import Badge
        from bretzel.components.primitives.icon import Icon

        inner: list[Node] = []
        if spec.icon:
            glyph = Icon(name=spec.icon, size=step.get("icon", "sm"),
                         color=spec.color)
            Component._detach_from_parent(glyph)
            inner.append(glyph.render())
        label_class = " ".join(
            p for p in (slots.get("label", ""), step.get("text", "")) if p
        )
        inner.append(
            Element(
                tag="span",
                attrs={"class": label_class},
                children=(TextNode(spec.label or spec.key),),
            )
        )
        if spec.badge:
            pill = Badge(label=spec.badge, size=step.get("badge", "xs"),
                         color="muted")
            Component._detach_from_parent(pill)
            inner.append(pill.render())
        return (
            Element(
                tag="div",
                attrs={"class": slots.get("node_body", "")},
                children=tuple(inner),
            ),
        )

    def _click_attrs(self, key: str, lit: str) -> dict[str, Any]:
        """The ``item_click`` wiring for THIS node.

        The action is per NODE, not on the root — so it goes through
        ``item_action_attrs``, the shared router of the four components
        in that case (a ``ui.table`` row, a bar, a slice, a node). It
        renders the three shapes of a framework ``on_*``: a server
        callable, a client expression string, or a list of both.

        ⚠️ This site COPIED that router instead of calling it, and it
        paid for the two things the router already knew how to do: the
        trigger rewritten by hand right after ``action_attrs``, and an
        UNGUARDED client expression — so an ``on_item_click="…"`` also
        fired when you clicked a button placed by ``render=``, where the
        same expression on ``ui.table`` does not. Adopted on 2026-09-07;
        it is the "primitive shipped, never adopted at the call sites"
        failure mode the coherence audit names.

        ``lit`` is the highlighting expression. It comes FIRST so the
        highlight is visible before the request leaves, and it is the
        ONLY thing this site adds to the router.
        """
        attrs = item_action_attrs(
            self._click,
            event="item_click",
            bind=lambda fn: functools.partial(fn, key),
            owner_id=self.id,
            ctx=current_context(),
            # The DECLARED event is `item_click`, the DOM one is `click`.
            dom_event="click",
            guard=_NODE_CLICK_GUARD,
            # `debounce=` / `throttle=`: the base layer applies them
            # only to the ROOT's action.
            modifier=self._trigger_modifier,
        )
        # The HIGHLIGHT comes first, and it is NOT guarded — it is the
        # only thing this site adds to the shared router. The highlight
        # must be visible before the request leaves, and a click on a
        # button placed by `render=` must still designate the node, even
        # if it does not fire the action.
        handler_side = attrs.get(client_event_attr("click"), "")
        attrs[client_event_attr("click")] = (
            f"{lit}; {handler_side}" if handler_side else lit
        )
        handlers = (
            list(self._click) if isinstance(self._click, (list, tuple))
            else [self._click]
        )
        # A node on which there is something to do announces itself as
        # such. The highlight alone is not enough to make it a button —
        # it fires on the click, not on the keyboard.
        if any(callable(h) for h in handlers if h is not None):
            attrs["role"] = "button"
            attrs["tabindex"] = "0"
            attrs["bz-on:keydown"] = _NODE_CLICK_KEYDOWN
        return attrs

    def render(self) -> Element:
        theme = self._resolved_theme()
        slots = theme.get("slots", {})
        sizes = theme.get("sizes", {})
        size_key = self._reactive_values.get("size") or "md"
        step = sizes.get(size_key, sizes.get("md", {}))

        # ⚠️ The scope and the hidden input are built BEFORE the empty
        # branch, and set on the root in BOTH cases.
        #
        # The first version exited early on an empty graph, so its root
        # had neither `bz-data` nor a carrier: a bound `value=` lost its
        # cell there, and `_serverSync` disappeared with it. A
        # component's contract must not change shape with its DATA —
        # that is what `test_server_sync_completeness` caught, by
        # building it with no edge.
        root_attrs, carrier = self._selection_wiring(slots)

        keys, edges = self._drawn()
        if not keys:
            hollow = Element(
                tag="div",
                attrs={"class": slots.get("empty", "")},
                children=self._build_empty(size_key),
            )
            return Element(
                tag="div",
                attrs=root_attrs,
                children=(hollow, carrier) if carrier is not None else (hollow,),
            )

        metrics = Metrics(
            node_width=float(step.get("w", 160)),
            node_height=float(step.get("h", 44)),
            layer_gap=float(step.get("layer", 72)),
            lane_gap=float(step.get("lane", 20)),
        )
        widths = {
            k: float(self._declared[k].width)
            for k in keys
            if k in self._declared and self._declared[k].width is not None
        }
        placed = layout(
            keys,
            [(e.source, e.target) for e in edges],
            metrics=metrics,
            direction=self._direction,
            widths=widths,
        )

        # ── The edge layer ──────────────────────────────────────────
        # The arrow marker is identified by the instance's id: two
        # diagrams on one page would otherwise share a ``<defs>`` and the
        # second would reuse the first's arrow — same shape here, but a
        # different ``color=`` would make it diverge.
        marker = f"{self.id or 'bz-diagram'}__arrow"
        by_pair = {(e.source, e.target): e for e in edges}
        paths: list[Node] = []
        for route in placed.routes:
            spec = by_pair.get((route.source, route.target))
            slot = _EDGE_STYLES.get(
                spec.style if spec else "solid", "edge"
            )
            attrs: dict[str, Any] = {
                "d": route.path,
                "class": theme.get(slot, theme.get("edge", "")),
                "marker-end": f"url(#{marker})",
                # An edge stays in the foreground only if BOTH its ends
                # are — otherwise the screen fills with the links that
                # leave the neighbourhood towards the outside, that is to
                # say with what we were precisely trying to remove.
                "bz-class": (
                    f"isEdgeLit({json.dumps(route.source)}, "
                    f"{json.dumps(route.target)}) ? '' : "
                    f"{json.dumps(theme.get('edge_dim', 'opacity-15'))}"
                ),
            }
            if spec is not None and spec.color:
                attrs["class"] = f"{attrs['class']} stroke-(--bz-fg)"
            if spec is not None and spec.label:
                paths.append(
                    Element(
                        tag="path",
                        attrs=attrs,
                        children=(
                            Element(tag="title", attrs={},
                                    children=(TextNode(spec.label),)),
                        ),
                    )
                )
                continue
            paths.append(Element(tag="path", attrs=attrs, children=()))

        arrow = Element(
            tag="defs",
            attrs={},
            children=(
                Element(
                    tag="marker",
                    attrs={
                        "id": marker,
                        "viewBox": "0 0 8 8",
                        "refX": "7", "refY": "4",
                        # 5 and not 7: the arrowhead carried as much
                        # ink as the node it designates. The direction is
                        # already said by the layers (you read towards
                        # the right) — the arrow CONFIRMS it, it does not
                        # announce it.
                        "markerWidth": "5", "markerHeight": "5",
                        "orient": "auto-start-reverse",
                    },
                    children=(
                        Element(
                            tag="path",
                            attrs={"d": "M0,0 L8,4 L0,8 z",
                                   "class": "fill-text/20"},
                            children=(),
                        ),
                    ),
                ),
            ),
        )
        svg = Element(
            tag="svg",
            attrs={
                "class": slots.get("edges", ""),
                "viewBox": f"0 0 {placed.width:.0f} {placed.height:.0f}",
                "width": f"{placed.width:.0f}",
                "height": f"{placed.height:.0f}",
                # The path is decorative: what the screen reader must
                # walk is the nodes, in layer order.
                "aria-hidden": "true",
            },
            children=(arrow, *paths),
        )

        # ── The nodes ───────────────────────────────────────────────
        # In LAYER order, not in input order: the DOM order is the tab
        # order, and we want to read the graph in the direction of the
        # arrows.
        boxes = {b.key: b for b in placed.boxes}
        near = self._adjacency(keys, edges)
        node_els: list[Node] = []
        for layer in placed.layers:
            for key in layer:
                box = boxes.get(key)
                if box is None:  # pragma: no cover — a layer only cites
                    continue     # nodes that were placed
                spec = self._declared.get(key, GraphNode(key=key))
                node_class = slots.get("node", "")
                if key == self._focus:
                    node_class = " ".join(
                        p for p in (node_class, slots.get("node_focus", "")) if p
                    )
                attrs: dict[str, Any] = {
                    "class": node_class,
                    # ⚠️ Position and size as INLINE styles. An
                    # assembled class (`left-[240px]`) only exists in
                    # dev: the production compiler only sweeps literals,
                    # and the page falls apart in production only.
                    "style": (
                        f"left:{box.x:.2f}px;top:{box.y:.2f}px;"
                        f"width:{box.width:.2f}px;height:{box.height:.2f}px"
                    ),
                    "data-bz-node": key,
                # The adjacency stays EXPOSED as data: the predicate
                # receives it as an argument, but a home-made `render=`
                # or a CSS selector may want to read it.
                "data-bz-adj": json.dumps(near.get(key, [key])),
                }
                if spec.group:
                    attrs["data-bz-group"] = spec.group
                # Designating a node lights up what touches it. Zero
                # requests: the adjacency is baked here, the browser
                # walks nothing. It is a READING gesture, it has nothing
                # to ask the server.
                #
                # On the click and not on hover: a touch screen has no
                # hover, and a `hover` is equally dead on a machine whose
                # pointer is coarse.
                adj = json.dumps(near.get(key, [key]))
                lit_expr = f"light({json.dumps(key)})"
                # The adjacency travels in the PREDICATE, not in a
                # state: `isLit` derives from the selection, so the
                # highlight follows a write coming from outside (a
                # control bound to the same field) exactly like a click.
                attrs["bz-class"] = (
                    f"isLit({json.dumps(key)}, {adj}) ? '' : "
                    f"{json.dumps(slots.get('node_dim', 'opacity-25'))}"
                )
                attrs.update(self._click_attrs(key, lit_expr))
                node_els.append(
                    Element(
                        tag="div",
                        attrs=attrs,
                        children=self._node_body(spec, step, slots),
                    )
                )

        # The highlight scope, set on the canvas so that the edge layer
        # AND the nodes inherit it — it is a single scope, like a
        # `ui.tree`'s disclosure.
        #
        # The methods come out of `$bz.diagram.scope` rather than being
        # serialised here: their body is rigorously the same from one
        # node to the next, only the ADJACENCY differs, and that travels
        # on the node.
        canvas = Element(
            tag="div",
            attrs={
                "class": slots.get("canvas", ""),
                "style": f"width:{placed.width:.2f}px;height:{placed.height:.2f}px",
            },
            children=(svg, *node_els),
        )
        return Element(
            tag="div",
            attrs=root_attrs,
            children=(
                (canvas, carrier) if carrier is not None else (canvas,)
            ),
        )

    def _selection_wiring(
        self, slots: dict
    ) -> tuple[dict[str, Any], Element | None]:
        """The root's attributes, and the hidden input if one is needed.

        ⚠️ This scope literal joins the base layer's debt no. 1 (14 → 15
        files, `test_scope_literal_debt_only_shrinks`), and it is a
        DECISION, not an oversight. A ⇄ two-way prop requires the "local
        value → store cell" switch; the 13 components that have both a
        runtime slab and a selection all carry it. The price of avoiding
        it would be to re-inline the five methods of `$bz.diagram.scope`
        into EVERY node.
        """
        binding = self._binding_metadata.get("value")
        initial = str(self._reactive_values.get("value") or "")
        (scope_key,) = self._scope_keys("value")
        if binding is not None:
            # Bound: the store cell IS the truth, we do not duplicate
            # it locally (that would race the framework's application of
            # the delta).
            path = self.path_of(binding)
            scope = (
                "{...$bz.diagram.scope,"
                f"_read(){{return {path};}},"
                f"_write(v){{{path} = v;}}}}"
            )
        else:
            sync = server_sync_marker(
                *self._scope_keys("value"),
                enabled=self._value_server_backed("value"),
            )
            scope = (
                "{...$bz.diagram.scope,"
                f"{scope_key}: {json.dumps(initial)}"
                + (f",{sync}" if sync else "")
                + "}"
            )

        # ── The hidden input — form / server-action integration ─────
        # A `<div>` carries neither `name`/`value` nor a native `change`:
        # the carrier does both, as in the 11 other components whose root
        # is not a form control.
        carrier: Element | None = None
        name = self._reactive_values.get("name") or self._derive_field_name()
        if name:
            value_directive = self.path_of(binding) if binding is not None else scope_key
            carrier_attrs: dict[str, Any] = {
                **hidden_carrier_attrs(value_directive, initial=initial),
                "name": str(name),
            }
            carrier = Element(tag="input", attrs=carrier_attrs, children=())

        return (
            {
                "class": slots.get("root", ""),
                # The scope lives on the ROOT and not on the canvas: it
                # is the root that must be able to answer a click that
                # lands NEXT TO a node, in the drawing's white space.
                "bz-data": scope,
                # Clicking in the void lights everything back up. So
                # does a click OUTSIDE the component — that is what
                # `arm($el)` arms, through the overlays' shared
                # `clickOutside`.
                "bz-on:click": (
                    "if (!$event.target.closest('[data-bz-node]')) reset()"
                ),
                "bz-effect": "arm($el)",
            },
            carrier,
        )
