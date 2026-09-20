"""``Tree`` test bench.

Eight cards : Reference / Client playground / Edge cases / Composability /
A11y / Server playground / Server events / Client events. The tree is
a *client-first* component — expand/collapse and the
selection highlight run entirely in the browser off a single ``bz-data``
scope, no round-trip. The Client playground card shows both wirings : a pure
:class:`ClientState` binding (instant highlight, zero network) and a
:class:`PageState` binding + ``on_change`` (the server learns which node
was picked, via the hidden input the tree relocates its action onto).
"""

from bretzel import page, refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/tree"


SIZES = ["sm", "md", "lg"]
COLORS = ["primary", "secondary", "success", "warning", "error", "info",
          "muted"]


class FileOpen(PageState):
    """Server-side selection — hydrated from the tree's hidden input."""

    picked: str = field(default="")


# ── S3 — genuine Server playground (props control grid) ─────────────────


class TreePlayground(PageState):
    value:       str  = field(default="")
    selectable:  bool = field(default=True)
    size:        str  = field(default="md")
    color:       str  = field(default="primary")
    expanded:    str  = field(default="src,components")
    # Escape hatches.
    classes:     str  = field(default="")
    custom_id:   str  = field(default="")
    aria_label:  str  = field(default="")
    style:       str  = field(default="")
    extra_attrs: str  = field(default="")
    # Universal modifiers.
    visible:     str  = field(default="on")
    tooltip:     str  = field(default="")


def server_changed(state: TreePlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted).
    pass


class TreeClient(ClientState, persist="memory"):
    """Pure client selection — the highlight follows this, no server."""

    node: str = field(default="app.py")


def open_file(state: FileOpen) -> None:
    # Typed handler : the tree relocates its ``hx-post`` onto a hidden
    # input named ``picked``, so ``state.picked`` is hydrated from the
    # clicked node. ``picked_panel(deps=[FileOpen])`` re-renders. Empty
    # body — the mutation is the hydration itself.
    pass


# ── S4/S6 — canonical event-log cards (Tree has one event : change) ─────


class TreeEvents(PageState):
    log: list = field(default_factory=list)


# Drives the Server-events demo tree. ``value=`` is bound to THIS
# ClientState (not the PageState ``FileOpen`` the Selection card uses) so
# the selection is CLIENT-backed : it survives the ``@refreshable`` morph
# (idiomorph's absorb keeps the client ``sel`` signal) and — crucially —
# emits NO ``_serverSync``. Binding to a server field whose handler does
# not persist it would make every morph re-adopt ``sel=""`` and the
# change-emit effect fire a phantom ``change(value='')`` (cf. traps.md
# § "Unbound Select/Combobox in a @refreshable → double change"). This
# mirrors ``AccordionServerEvents`` / ``ToggleGroupServerEvents``.
class TreeServerEvents(ClientState, persist="memory"):
    picked: str = field(default="")


class TreeClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


def log_change(**form) -> None:
    picked = next((v for v in form.values() if v not in (None, "")), "")
    state = TreeEvents()
    state.log = [*state.log, f"change(value={picked!r})"]


def clear_log() -> None:
    TreeEvents().log = []


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def build_preview(state: TreePlayground) -> dict:
    kwargs: dict = {
        "selectable": state.selectable,
        "size": state.size,
        "color": state.color,
        "expanded": [v.strip() for v in state.expanded.split(",")
                     if v.strip()],
    }
    if state.value:
        kwargs["value"] = state.value
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


@refreshable(deps=[TreePlayground])
def server_panel() -> None:
    state = TreePlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("value (selected node id)"):
            ui.input(value=state.value, placeholder="app.py",
                     on_change=server_changed)
        with control("selectable"):
            ui.switch(checked=state.selectable, on_change=server_changed)
        with control("size"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("expanded (comma-separated ids)"):
            ui.input(value=state.expanded, placeholder="src,components",
                     on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="!max-w-xs",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-tree",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, placeholder="Project files",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="max-width: 320px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=tree",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder="Browse the project",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    kwargs = build_preview(state)
    with ui.flex(justify="center"):
        with ui.tree(**kwargs):
            project_nodes()

    ui.divider()

    preview = ui.tree(**kwargs)
    with preview:
        project_nodes()
    emitted_html_block(
        "Emitted HTML — the controls grid drives this snapshot live",
        serialize_html(preview),
    )


def project_nodes() -> None:
    """Sample project tree — call inside an open ``with ui.tree()``."""
    with ui.tree_node("src", label="src", icon="folder"):
        with ui.tree_node("components", label="components", icon="folder"):
            ui.tree_node("button.py", label="button.py", icon="file")
            ui.tree_node("tree.py", label="tree.py", icon="file")
        ui.tree_node("app.py", label="app.py", icon="file")
    with ui.tree_node("tests", label="tests", icon="folder"):
        ui.tree_node("test_tree.py", label="test_tree.py", icon="file")
    ui.tree_node("README", label="README.md", icon="file-text")
    ui.tree_node("pyproject", label="pyproject.toml", icon="settings")


@refreshable(deps=[FileOpen])
def picked_panel() -> None:
    picked = FileOpen().picked
    if picked:
        ui.text(f"Server received : {picked}",
                color="success", weight="medium")
    else:
        ui.text("Click a file — the server receives the node id via a "
                "single hx-post (the row highlights instantly, before "
                "the round-trip even starts).",
                color="muted", size="sm")


@refreshable(deps=[TreeEvents])
def events_panel() -> None:
    state = TreeEvents()

    ui.text(
        "Tree's one event : ``change``. The Selection card above shows "
        "the real single-value echo ; this canonical live-log card "
        "matches the shape every other component's Server events card "
        "uses.",
        color="muted", size="sm",
    )

    evt_state = TreeServerEvents()
    with ui.tree(value=evt_state.picked, on_change=log_change,
                 expanded=["src"]):
        project_nodes()

    ui.divider()

    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (newest first, last 10)",
                color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs",
                  on_click=clear_log, disabled=not state.log)

    if state.log:
        with ui.vstack(gap="xs"):
            for i, evt in enumerate(reversed(state.log[-10:]), 1):
                ui.text(f"{i}. {evt}",
                        color="muted", size="sm", classes="font-mono")
    else:
        ui.text("(no events yet — click a file above)",
                color="muted", size="sm")

    ui.divider()

    representative = ui.tree(value="app.py", on_change=log_change)
    with representative:
        ui.tree_node("app.py", label="app.py", icon="file")
    emitted_html_block(
        "Emitted HTML (representative — the change event)",
        serialize_html(representative),
    )


def page() -> None:
    with ui.container():
        with ui.vstack(gap="lg"):
            ui.heading("Tree", level=1)
            ui.text(
                "A recursive, collapsible hierarchy — file explorers, "
                "nav trees, category pickers, org charts. Branches "
                "expand/collapse client-side off one bz-data scope (no "
                "round-trip) ; the chevron is two static glyphs (▶ / ▼), "
                "never a rotation, so open/closed is unambiguous and "
                "survives the production Tailwind build.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack(gap="md"):
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every axis.",
                            color="muted", size="sm")

                    ui.heading("Sizes", level=3)
                    with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                        for sz in SIZES:
                            with ui.vstack(gap="xs"):
                                ui.text(sz, color="muted", size="xs")
                                with ui.tree(size=sz, expanded=["src"]):
                                    project_nodes()

                    ui.divider()
                    ui.heading("Colors (selection tint)", level=3)
                    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
                        for c in COLORS:
                            with ui.vstack(gap="xs"):
                                ui.text(c, color="muted", size="xs")
                                with ui.tree(color=c, value="app.py",
                                             expanded=["src"]):
                                    project_nodes()

                    ui.divider()
                    ui.heading("Without icons", level=3)
                    with ui.tree(expanded=["src"]):
                        with ui.tree_node("src", label="src"):
                            ui.tree_node("app.py", label="app.py")
                            ui.tree_node("tree.py", label="tree.py")
                        ui.tree_node("README", label="README.md")

                    ui.heading("Non-selectable (pure outline)", level=3)
                    with ui.tree(selectable=False, expanded=["intro"]):
                        with ui.tree_node("intro", label="Introduction",
                                          icon="book-open"):
                            ui.tree_node("install", label="Installation")
                            ui.tree_node("quickstart", label="Quickstart")
                        with ui.tree_node("guide", label="Guide",
                                          icon="compass"):
                            ui.tree_node("state", label="State")

            # ── Card 2 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack(gap="md"):
                    ui.heading("Edge cases", level=2)
                    ui.text("Inputs that historically break tree widgets.",
                            color="muted", size="sm")

                    ui.heading("Deep nesting (5 levels)", level=3)
                    with ui.tree(expanded=["l1", "l2", "l3", "l4"]):
                        with ui.tree_node("l1", label="level 1", icon="folder"):
                            with ui.tree_node("l2", label="level 2",
                                              icon="folder"):
                                with ui.tree_node("l3", label="level 3",
                                                  icon="folder"):
                                    with ui.tree_node("l4", label="level 4",
                                                      icon="folder"):
                                        ui.tree_node("l5", label="leaf",
                                                     icon="file")

                    ui.heading("Long label / emoji / XSS escape", level=3)
                    ui.text("The framework escapes labels — the script "
                            "renders as literal text, never executes.",
                            color="muted", size="xs")
                    with ui.tree(expanded=["root"]):
                        with ui.tree_node("root", label="root", icon="folder"):
                            ui.tree_node("long", label="A" * 70, icon="file")
                            ui.tree_node("emoji",
                                         label="Ship 🚀 — שלום — 中文",
                                         icon="file")
                            ui.tree_node("xss",
                                         label="<script>alert(1)</script>",
                                         icon="file")

                    ui.heading("Disabled node + label-less node", level=3)
                    with ui.tree(expanded=["dir"]):
                        with ui.tree_node("dir", label="dir", icon="folder"):
                            ui.tree_node("ok", label="enabled.py", icon="file")
                            ui.tree_node("no", label="disabled.py",
                                         icon="file", disabled=True)
                            ui.tree_node("bare", icon="file")  # label ← id

                    ui.heading("Empty tree", level=3)
                    ui.tree()

            # ── Card 3 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack(gap="md"):
                    ui.heading("Composability", level=2)
                    ui.text("Tree nested inside other Bretzel components.",
                            color="muted", size="sm")

                    ui.heading("Inside ui.card (sidebar-style nav)", level=3)
                    with ui.card():
                        with ui.tree(value="dashboard", size="sm",
                                     expanded=["reports"]):
                            ui.tree_node("dashboard", label="Dashboard",
                                         icon="layout-dashboard")
                            with ui.tree_node("reports", label="Reports",
                                              icon="bar-chart-3"):
                                ui.tree_node("weekly", label="Weekly")
                                ui.tree_node("monthly", label="Monthly")
                            ui.tree_node("settings", label="Settings",
                                         icon="settings")

                    ui.heading("Inside ui.tooltip", level=3)
                    with ui.tooltip("A collapsible outline"):
                        with ui.tree(selectable=False, expanded=["a"]):
                            with ui.tree_node("a", label="Section A"):
                                ui.tree_node("a1", label="Item 1")

                    ui.heading("label=Component (slot shape)", level=3)
                    ui.text(
                        "``label`` and ``icon`` accept a Component, "
                        "not just str — compose a badge or a styled "
                        "text node right into the node row.",
                        color="muted", size="sm",
                    )
                    with ui.tree(expanded=["root"]):
                        with ui.tree_node(
                            "root",
                            label=ui.text("Custom label", weight="bold",
                                          color="primary"),
                            icon="folder",
                        ):
                            ui.tree_node("a", label="Plain child")

            # ── Card 4 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="md"):
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Emits role=tree / treeitem / group with "
                        "aria-level, aria-expanded (branches) and "
                        "aria-selected (selectable). Each row is "
                        "focusable (Tab) and activates on Enter / Space. "
                        "Full arrow-key roving-tabindex navigation is a "
                        "documented follow-up (see inventory).",
                        color="muted", size="sm",
                    )
                    with ui.tree(value="b1", expanded=["a", "b"]):
                        with ui.tree_node("a", label="Fruits", icon="apple"):
                            ui.tree_node("a1", label="Apple")
                            ui.tree_node("a2", label="Banana")
                        with ui.tree_node("b", label="Veggies", icon="carrot"):
                            ui.tree_node("b1", label="Carrot")
                            ui.tree_node("b2", label="Potato")

            # ── Card 5 — Server playground ───────────────────────────
            with ui.card():
                with ui.vstack(gap="md"):
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Every prop AND every escape hatch is wired "
                        "to a control ; the preview AND the emitted "
                        "HTML both refresh on every change.",
                        color="muted", size="sm",
                    )
                    server_panel()

            # ── Card 6 — Server events ──────────────────────────────
            with ui.card():
                with ui.vstack(gap="md"):
                    ui.heading("Server events", level=2)
                    events_panel()

            # ── Card 7 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack(gap="md"):
                    ui.heading("Client playground", level=2)
                    ui.text(
                        "Mirror of ``BINDABLE_PROPS = ('value',)`` — the "
                        "picked node, and nothing else : ``expanded`` is "
                        "design-time (it seeds the scope, then the "
                        "browser owns it) and ``selectable`` / ``size`` "
                        "/ ``color`` restructure the render.",
                        color="muted", size="sm",
                    )
                    ui.text(
                        "Two wirings, same component. Click a file in "
                        "either tree.",
                        color="muted", size="sm",
                    )

                    ui.heading("Client binding — instant, no network",
                               level=3)
                    ui.text(
                        "value = ClientState field. The selected row "
                        "highlights the moment you click ; the value "
                        "lives in the browser, readable by any other "
                        "component with zero server hit.",
                        color="muted", size="sm",
                    )
                    with ui.tree(value=TreeClient().node,
                                 expanded=["src", "components"]):
                        project_nodes()

                    ui.divider()

                    ui.heading("Server binding — on_change fires a handler",
                               level=3)
                    ui.text(
                        "value = PageState field + on_change. The row "
                        "still highlights instantly (client-tracked), AND "
                        "a single hx-post carries the picked node to the "
                        "server via the tree's hidden input.",
                        color="muted", size="sm",
                    )
                    with ui.tree(value=FileOpen().picked, on_change=open_file,
                                 expanded=["src", "components"]):
                        project_nodes()
                    picked_panel()

                    ui.divider()

                    ui.text(
                        ClientExpression(
                            "'client-bound value : ' + "
                            "($bz.state.TreeClient.default.node"
                            " || '(none)')"
                        ),
                        color="muted", size="sm",
                        classes="font-mono",
                    )

                    ui.divider()

                    client_preview = ui.tree(value=TreeClient().node,
                                             expanded=["src"])
                    with client_preview:
                        project_nodes()
                    emitted_html_block(
                        "Emitted HTML (client binding) — the root's "
                        "bz-data holds the whole selection : every row "
                        "reads the same store cell through "
                        "bz-attr:data-selected, so the highlight moves "
                        "without a single request.",
                        serialize_html(client_preview),
                    )

            # ── Card 8 — Client events ──────────────────────────────
            with ui.card():
                with ui.vstack(gap="md"):
                    ui.heading("Client events", level=2)
                    ui.text(
                        "``change`` wired to a client expression that "
                        "pushes onto a ClientState list. Zero network ; "
                        "the log below re-renders via bz-text on every "
                        "push.",
                        color="muted", size="sm",
                    )
                    cevents = TreeClientEvents()
                    _new_value = ClientExpression("$event.target.value")
                    with ui.tree(value=TreeClient(key="client_events").node,
                                 on_change=cevents.log.push(_new_value),
                                 expanded=["src"]):
                        project_nodes()

                    ui.divider()

                    with ui.hstack(justify="between", align="center"):
                        ui.text("Live log (client-reactive — no refresh)",
                                color="muted", size="sm")
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=cevents.log.clear())

                    log_text = ClientExpression(
                        '($bz.state.TreeClientEvents.default.log'
                        ' || []).join("\\n") || "(no events yet)"'
                    )
                    ui.text(log_text,
                            color="muted", size="sm",
                            classes="font-mono whitespace-pre")

                    ui.divider()

                    representative = ui.tree(
                        value="app.py",
                        on_change=cevents.log.push(_new_value),
                    )
                    with representative:
                        ui.tree_node("app.py", label="app.py", icon="file")
                    emitted_html_block(
                        "Emitted HTML (representative — the change "
                        "event)",
                        serialize_html(representative),
                    )
