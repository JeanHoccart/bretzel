"""The Diagram playground's page-scoped state, plus the constant axes.

One field per component prop, one per universal escape hatch, one per
modifier — it is what the template asks for, and it is what makes the
Server playground a real bench rather than a demo.

``Picked`` is apart: it drives the Reference card's NARROWING. Server
side, because changing the centre changes the nodes drawn, hence the
placement.
"""

from bretzel import ui
from bretzel.state import ClientState, PageState, field

SIZES = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning", "error", "info",
          "muted"]
DIRECTIONS = ["right", "down"]

# The shape of a real app map: pages consuming an engine, which itself
# consumes two sources. A diamond plus a long edge, hence phantom nodes —
# the configuration where an edge can pass OVER a node if the placement
# is wrong.
EDGES = [
    ("dashboard", "planning_engine"),
    ("planning", "planning_engine"),
    ("tournees", "planning_engine"),
    ("planning_engine", "geo"),
    ("planning_engine", "db"),
    ("geo", "db"),
    ("settings", "db"),
]

NODES = [
    ui.node("dashboard", label="dashboard", icon="layout-dashboard",
            badge="1 route", group="pages"),
    ui.node("planning", label="planning", icon="calendar-days",
            badge="2 routes", group="pages"),
    ui.node("tournees", label='rotated', icon="truck", group="pages"),
    ui.node("settings", label="settings", icon="settings", group="pages"),
    ui.node("planning_engine", label="planning_engine", icon="cog",
            group="socle", width=200),
    ui.node("geo", label="geo", icon="map-pin", group="socle"),
    ui.node("db", label="db", icon="database", group="socle"),
]


class Picked(PageState):
    """The node centred in the Reference card — SERVER side.

    Narrowing changes the nodes drawn, hence the placement: it cannot be
    client side. Lighting up can be — and the component does it alone.
    """

    key: str = field(default="")


class DiagramPlayground(PageState):
    focus:        str  = field(default="")
    depth:        int  = field(default=1)
    direction:    str  = field(default="right")
    size:         str  = field(default="md")
    color:        str  = field(default="primary")
    empty_text:   str  = field(default="No graph.")
    empty_icon:   str  = field(default="workflow")
    empty_desc:   str  = field(default="")
    empty:        bool = field(default=False)
    render_mode:  str  = field(default="default")
    click_mode:   str  = field(default="none")
    # Universal escape hatches.
    classes:      str  = field(default="")
    custom_id:    str  = field(default="")
    aria_label:   str  = field(default="")
    style:        str  = field(default="")
    extra_attrs:  str  = field(default="")
    # Modificateurs universels.
    visible:      str  = field(default="on")
    tooltip:      str  = field(default="")




class DiagramServerEvents(PageState):
    """The Server events card's log.

    ``item_click`` is ``Diagram``'s ONLY event — the template requires
    them all to be wired, so a single live control is enough here.
    """

    log: list = field(default_factory=list)


class DiagramClientEvents(ClientState, persist="memory"):
    """The same log, but in the BROWSER's memory.

    The same event wired onto a client expression: the list grows without
    any request leaving. It is what the card's HTML block shows — a
    ``bz-on:click`` where the server put an ``hx-post``.
    """

    log: list = field(default_factory=list)


class DiagramClient(ClientState, persist="memory"):
    """The selected node, on the BROWSER side.

    The mirror of the ``BINDABLE_PROPS = ("value",)`` contract: binding
    ``value=`` to this field is wiring the selection onto the client
    store. A click writes into it without any request leaving, and
    everything reading the field follows.
    """

    node: str = field(default="")
