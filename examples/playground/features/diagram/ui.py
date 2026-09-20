"""The Diagram bench's rendering — its cards and their panels.

EIGHT, and it is ``playground-pattern.md`` § 3 that sets which, not a
preference: ``Diagram`` declares an event and a bindable prop, so Server
events, Client events and Client playground are MANDATORY (§ 4, § 6,
§ 5). Slots and External controls stay omitted — the component has
neither a named slot nor an imperative API, and the template says "no
empty cards".

⚠️ Three of these cards were missing from the first delivery, and the
reason was wrong the same way each time: I read EMPTY ClassVar and
concluded the component had neither event nor selection. They were empty
because I had not declared them — not because there was nothing to
declare. The template is read against the component one SHOULD have
written, not against the one just written.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression

from examples.playground.features.diagram.logic import (
    clear_log,
    log_item_click,
    pick,
    playground_click_handler,
    server_changed,
)
from examples.playground.features.diagram.state import (
    COLORS,
    DIRECTIONS,
    EDGES,
    NODES,
    SIZES,
    DiagramClient,
    DiagramClientEvents,
    DiagramPlayground,
    DiagramServerEvents,
    Picked,
)
from examples.playground.features.inspection import emitted_html_block


def card_node(spec):
    """A home-made ``render=``: a node's content belongs to the author.

    ⚠️ What a PROP can do goes through the prop. The first version
    centred with ``classes="justify-center"`` although ``ui.vstack``
    already emits ``justify-start``: two ``justify-*`` on the same
    element are decided by the Tailwind SHEET's order, not the
    attribute's, and the content stayed stuck at the top.

    And a colour-bridge step (``bg-(--bz-bg)``) is TINTED: a ``render=``
    inherits the root's bridge, so those nodes came out coloured in the
    middle of neutral nodes.
    """
    with ui.vstack(gap="none", align="start", justify="center",
                   classes="h-full w-full px-3 rounded-box "
                           "border-(length:--bz-stroke) border-(--bz-border) "
                           "bg-surface") as box:
        ui.text(spec.label or spec.key, size="sm", weight="medium",
                truncate=True)
        if spec.group:
            ui.text(spec.group, size="xs", color="muted")
    return box


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def build_preview(state: DiagramPlayground) -> dict:
    kwargs: dict = {
        "nodes": NODES,
        "edges": [] if state.empty else EDGES,
        "depth": state.depth,
        "direction": state.direction,
        "size": state.size,
        "color": state.color,
        "empty_text": state.empty_text,
    }
    if state.focus:
        kwargs["focus"] = state.focus
    if state.empty_icon:
        kwargs["empty_icon"] = state.empty_icon
    if state.empty_desc:
        kwargs["empty_description"] = state.empty_desc
    if state.render_mode == "custom":
        kwargs["render"] = card_node
    if state.click_mode == "server":
        kwargs["on_item_click"] = playground_click_handler
    if state.classes:
        kwargs["classes"] = state.classes
    if state.custom_id:
        kwargs["id"] = state.custom_id
    if state.style:
        kwargs["style"] = state.style
    attrs: dict = {}
    if state.aria_label:
        attrs["aria-label"] = state.aria_label
    attrs.update(parse_extra_attrs(state.extra_attrs))
    if attrs:
        kwargs["attrs"] = attrs
    if state.tooltip:
        kwargs["tooltip"] = state.tooltip
    if state.visible == "off":
        kwargs["visible"] = False
    return kwargs


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[Picked])
def focus_panel() -> None:
    """``focus=`` driven by a server click — the narrowing."""
    picked = Picked().key
    ui.diagram(nodes=NODES, edges=EDGES, focus=picked or None,
               on_item_click=pick)
    ui.text(
        f"'Centred on “'{picked}'” — click it again to see everything.'"
        if picked else
        'Click a node: the view narrows onto its neighbourhood (server '
            'side). A plain click already lights up its neighbours, and that '
            'one costs no request.',
        color="muted", size="sm",
    )


@refreshable(deps=[DiagramPlayground])
def server_panel() -> None:
    state = DiagramPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control('focus (the centred node)'):
            ui.select(value=state.focus,
                      options=[("", 'None (the whole graph)'),
                               *[(n.key, n.key) for n in NODES]],
                      on_change=server_changed)
        with control("depth (sauts de voisinage)"):
            ui.number_input(value=state.depth, min=1, max=4,
                            on_change=server_changed)
        with control("direction"):
            ui.select(value=state.direction,
                      options=[(d, d) for d in DIRECTIONS],
                      on_change=server_changed)
        with control("size"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("render (a node's content)"):
            ui.select(value=state.render_mode,
                      options=[("default", 'Default (icon + label)'),
                               ("custom", "card_node (rappel)")],
                      on_change=server_changed)
        with control("on_item_click"):
            ui.select(value=state.click_mode,
                      options=[("none", "None (aucun handler)"),
                               ("server", "Server callable")],
                      on_change=server_changed)
        with control('edges (empty → the empty state)'):
            ui.switch(checked=state.empty, label="graphe vide",
                      on_change=server_changed)
        with control("empty_text"):
            ui.input(value=state.empty_text, placeholder="No graph.",
                     on_change=server_changed)
        with control("empty_icon"):
            ui.input(value=state.empty_icon, placeholder="workflow",
                     on_change=server_changed)
        with control("empty_description"):
            ui.input(value=state.empty_desc,
                     placeholder='No feature consumes another.',
                     on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="!max-h-64",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-diagram",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder='Dependencies between features',
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="max-width: 480px",
                     on_change=server_changed)
        with control('extra_attrs (one per line, key=value)'):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=diagram",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder='The dependency axis',
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", 'True (default)'),
                               ("off", "False (aucun rendu)")],
                      on_change=server_changed)

    ui.divider()

    kwargs = build_preview(state)
    ui.diagram(**kwargs)

    ui.divider()

    emitted_html_block(
        "Emitted HTML",
        serialize_html(ui.diagram(**kwargs)),
    )


@refreshable(deps=[DiagramServerEvents])
def events_panel() -> None:
    state = DiagramServerEvents()

    ui.text(
        "``item_click`` is Diagram's only event. The handler receives the"
            " node's KEY — the feature's name, not an index nor an object to "
            'resolve again.',
        color="muted", size="sm",
    )
    ui.diagram(nodes=NODES, edges=EDGES, on_item_click=log_item_click)

    ui.divider()

    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (newest first, last 10)", color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs",
                  on_click=clear_log, disabled=not state.log)
    if state.log:
        with ui.vstack(gap="xs"):
            for i, evt in enumerate(reversed(state.log[-10:]), 1):
                ui.text(f"{i}. {evt}", color="muted", size="sm",
                        classes="font-mono")
    else:
        ui.text('(no events yet — click a node above)',
                color="muted", size="sm")

    ui.divider()

    emitted_html_block(
        "Emitted HTML (item_click serveur)",
        serialize_html(ui.diagram(edges=[("a", "b")],
                                  on_item_click=log_item_click)),
    )


def client_events_panel() -> None:
    """The SAME event, wired onto a client expression.

    No ``@refreshable``: that is the whole point. The log lives in a
    ``ClientState`` and the text is re-evaluated in the browser — no
    request leaves, so there is nothing to re-render on the server side.
    """
    events = DiagramClientEvents()

    ui.text(
        '``item_click`` wired to a client expression that pushes the key '
            'onto a ClientState. Zero requests.',
        color="muted", size="sm",
    )
    # ``$event.detail`` carries the node's key: it is what the component
    # puts in the payload, and it is the same value a server handler
    # receives.
    clicked = ClientExpression("$event.currentTarget.dataset.bzNode")
    ui.diagram(nodes=NODES, edges=EDGES,
               on_item_click=events.log.push(clicked))

    ui.divider()

    with ui.hstack(justify="between", align="center"):
        ui.text('Live log (client-reactive — no refresh at all)',
                color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs",
                  on_click=events.log.clear())
    # ⚠️ A RAW string, and single quotes on the JS side.
    #
    # An earlier version carried a real line break where the escape
    # sequence is needed: the emitted JS was `join("` followed by an end
    # of line, hence an unterminated literal. The price is not local —
    # the WHOLE runtime stops starting, `html.bz-ready` never arrives,
    # and not a single directive on the page works any more. A malformed
    # client expression does not degrade: it switches off.
    log_text = ClientExpression(
        "($bz.state.DiagramClientEvents.default.log || []).join('\\n') || "
            "'(no events yet — click a node above)'"
    )
    ui.text(log_text, color="muted", size="sm",
            classes="font-mono whitespace-pre")

    ui.divider()

    emitted_html_block(
        "Emitted HTML (item_click client)",
        serialize_html(ui.diagram(edges=[("a", "b")],
                                  on_item_click=events.log.push(clicked))),
    )


def client_panel() -> None:
    """The mirror of the ``BINDABLE_PROPS = ("value",)`` contract.

    No ``@refreshable``: that is the point. ``value`` is bound to the
    client store, so a click writes into it and everything reading it
    follows — the text line, the preview, the hidden field — without a
    single request leaving. The HTML block below is an SSR capture: what
    the runtime then does with it does not show there.
    """
    pick = DiagramClient()

    ui.text(
        '``value`` = the selected node, ⇄ two-way. The client driver is '
            'the click on a node; that is what makes the prop bindable rather'
            ' than static (client-reactive-surface.md § The rule).',
        color="muted", size="sm",
    )
    # ⚠️ The EXTERNAL CONTROL is this card's heart, not an ornament.
    # Without it we show only one direction — the component writing into
    # the store — and "⇄ two-way" is no more than an assertion. Here the
    # `select` is bound to the SAME field: choosing in it moves the
    # diagram's selection, clicking a node moves the `select`. No request
    # in either direction.
    with control('value (bound) — the select WRITES, the diagram READS'):
        with ui.hstack(gap="sm", align="center"):
            ui.select(
                value=pick.node,
                options=[("", "(aucun)"), *[(n.key, n.key) for n in NODES]],
            )
            ui.button("Effacer", variant="ghost", size="xs",
                      on_click=pick.node.set(""))
    with ui.hstack(gap="sm", align="center"):
        ui.text("current value:", color="muted", size="sm")
        ui.text(pick.node, weight="medium", size="sm")
    ui.diagram(nodes=NODES, edges=EDGES, value=pick.node)

    ui.divider()

    emitted_html_block(
        'Emitted HTML (value bound to a ClientState)',
        serialize_html(ui.diagram(edges=[("a", "b")], value=pick.node)),
    )


def page() -> None:
    with ui.container():
        with ui.vstack(gap="lg"):
            ui.heading("Diagram", level=1)
            ui.text(
                'A directed graph laid out in layers on the server: '
                    'cycles broken, layers by longest path, crossings reduced'
                    ' by the median heuristic. The edges live in an '
                    '``<svg>``, the nodes are positioned HTML — so every node'
                    ' stays a themed, tabbable, clickable component. Pointing'
                    ' at a node lights up what touches it, with no request.',
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every prop.",
                            color="muted", size="sm")

                    ui.heading('Basic — the edges are enough', level=3)
                    ui.diagram(edges=EDGES)

                    ui.heading("nodes= + edges= (descripteurs)", level=3)
                    ui.diagram(
                        nodes=NODES,
                        edges=[ui.edge("planning", "planning_engine",
                                       label="uses"),
                               ui.edge("planning_engine", "geo",
                                       label="reads", style="dashed"),
                               ui.edge("geo", "db")],
                    )

                    ui.heading("Sizes", level=3)
                    for s in SIZES:
                        ui.text(f"size={s}", color="muted", size="xs")
                        ui.diagram(edges=[("a", "b"), ("b", "c")], size=s)

                    ui.heading("Colors", level=3)
                    for c in COLORS:
                        ui.text(f"color={c}", color="muted", size="xs")
                        ui.diagram(edges=[("a", "b"), ("b", "c")], color=c)

                    ui.heading("direction", level=3)
                    for d in DIRECTIONS:
                        ui.text(f"direction={d}", color="muted", size="xs")
                        ui.diagram(edges=EDGES, direction=d)

                    ui.heading("focus= + depth=", level=3)
                    ui.text("focus='planning_engine', depth=1 puis 2",
                            color="muted", size="xs")
                    ui.diagram(edges=EDGES, focus="planning_engine")
                    ui.diagram(edges=EDGES, focus="planning_engine", depth=2)

                    ui.heading('on_item_click — the server-side narrowing',
                               level=3)
                    focus_panel()

            # ── Card 2 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)

                    ui.heading('A cycle', level=3)
                    ui.text('The returning edge is reversed for PLACEMENT, never '
                        'for the arrowhead.',
                            color="muted", size="xs")
                    ui.diagram(edges=[("a", "b"), ("b", "c"), ("c", "a")])

                    ui.heading('An edge that skips a layer', level=3)
                    ui.text('It runs flat under the middle layer; it does not '
                        'pass OVER the node.',
                            color="muted", size="xs")
                    ui.diagram(edges=[("a", "b"), ("b", "c"), ("a", "c")])

                    ui.heading('A self-loop', level=3)
                    ui.diagram(edges=[("a", "a"), ("a", "b")])

                    ui.heading('An isolated node', level=3)
                    ui.diagram(nodes=[ui.node("seul", icon="circle")],
                               edges=[])

                    ui.heading('focus= pointing at a node that does not exist', level=3)
                    ui.text('A stale key falls back to the whole graph, not to a '
                        'blank screen.',
                            color="muted", size="xs")
                    ui.diagram(edges=EDGES, focus="disparu")

                    ui.heading('A label to escape (XSS)', level=3)
                    ui.diagram(nodes=[ui.node("x", label="<script>alert(1)"),
                                      ui.node("y", label="a & b")],
                               edges=[("x", "y")])

                    ui.heading("Graphe vide", level=3)
                    ui.diagram(edges=[], empty_text='No dependency.',
                               empty_icon="unplug",
                               empty_description='No feature consumes another.')

                    ui.heading('Empty graph — the ``empty=`` escape hatch',
                               level=3)
                    ui.text('The three convenience props cover the common case; '
                        '``empty=`` renders whatever you want in their place.'
                        ' The same API as ``ui.table`` and ``ui.datatable``.',
                            color="muted", size="xs")
                    ui.diagram(
                        edges=[],
                        empty=lambda: ui.button('Declare a dependency',
                                                icon_left="plus",
                                                color="primary"),
                    )

            # ── Card 3 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text(
                        'What the component becomes once placed SOMEWHERE'
                            ' ELSE — that is where the faults a solo mount '
                            'never shows become visible.',
                        color="muted", size="sm")

                    ui.heading('render= — a node is a ui.* subtree',
                               level=3)
                    ui.diagram(nodes=NODES, edges=EDGES, render=card_node,
                               size="lg")

                    ui.heading('In a constrained grid', level=3)
                    ui.text('The cell is narrower than the drawing: it must '
                        'SCROLL, not shrink.',
                            color="muted", size="xs")
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        ui.diagram(edges=EDGES)
                        ui.diagram(edges=EDGES, direction="down")

                    ui.heading('In a height-bounded column', level=3)
                    ui.text("traps.md's trap: a clipping root has a minimum "
                        'height of ZERO.',
                            color="muted", size="xs")
                    with ui.vstack(classes="h-[260px]"):
                        with ui.pane():
                            ui.diagram(nodes=NODES, edges=EDGES, size="xl")

            # ── Card 4 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "This is where the component's argument is "
                            'settled. A node is HTML, not a ``<rect>``: it '
                            "tabs in LAYER order, carries the theme's focus "
                            'ring, and Enter / Space activate it when it '
                            'carries a handler. The edge layer is ``aria-'
                            'hidden`` — what a screen reader should walk '
                            'through is the nodes.',
                        color="muted", size="sm")
                    ui.text('Tab here: the order follows the arrows.',
                            color="muted", size="xs")
                    ui.diagram(nodes=NODES, edges=EDGES, on_item_click=pick)

            # ── Card 5 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        'Every prop, every universal escape hatch, every '
                            'modifier — all driven from a PageState.',
                        color="muted", size="sm")
                    server_panel()

            # ── Card 6 — Server events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server events", level=2)
                    events_panel()

            # ── Card 7 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    client_panel()

            # ── Card 8 — Client events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    client_events_panel()
