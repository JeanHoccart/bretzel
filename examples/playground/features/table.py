"""``Table`` test bench.

Cards (per ``playground-pattern.md``) : Reference / Edge cases /
Composability / A11y / Server playground / Server events.

``BINDABLE_PROPS = ()`` → no Client playground / Client events cards
(rows are server-rendered ; re-render via ``@refreshable`` on
sort / filter / pagination). The component's one event is the per-row
``on_item_click`` → Server events card.

Props : ``columns`` / ``rows`` / ``row_key`` / ``on_item_click`` /
``size`` / ``color`` + empty-state knobs (``empty_text`` /
``empty_icon`` / ``empty_description`` / ``empty``). The striped +
hover look is baked in (no toggles).
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/table"


COLORS = ["primary", "secondary", "success", "warning",
          "error", "info", "muted"]
SIZES = ["sm", "md", "lg"]
EMPTY_ICONS = ["inbox", "database", "search", "folder", "file-x"]


ISSUES = [
    {"id": 142, "title": "Pagination overflow on long lists",
     "status": "open",     "priority": "high",   "assignee": "AL"},
    {"id": 137, "title": "Tooltip flickers on hover",
     "status": "merged",   "priority": "medium", "assignee": "JD"},
    {"id": 129, "title": "Form submit double-fires",
     "status": "open",     "priority": "high",   "assignee": "MH"},
    {"id": 121, "title": "Dropdown closes immediately",
     "status": "closed",   "priority": "low",    "assignee": "GH"},
    {"id": 118, "title": "Dialog doesn't focus first input",
     "status": "open",     "priority": "medium", "assignee": "AL"},
]


# ── Cell renderers — reused by RICH_COLUMNS across several cards ──────
class TableClientEvents(ClientState, persist="memory"):
    """The Client events card's log — on the browser side."""

    log: list = field(default_factory=list)


def status_badge(value, _row):
    color = {"open": "info", "merged": "success",
             "closed": "muted"}.get(value, "muted")
    return ui.badge(value, color=color)


def priority_badge(value, _row):
    color = {"high": "error", "medium": "warning",
             "low": "muted"}.get(value, "muted")
    return ui.badge(value, color=color, variant="solid")


def assignee_avatar(value, _row):
    return ui.avatar(initials=value, color="primary")


def row_actions(_value, row):
    dd = ui.dropdown(
        trigger=ui.icon_button("more-horizontal",
                               variant="ghost",
                               aria_label=f"Actions for #{row['id']}"),
        align="end",
    )
    with dd:
        ui.dropdown_item(label="Open",     icon_left="arrow-up-right")
        ui.dropdown_item(label="Reassign", icon_left="user")
        ui.dropdown_item(label="Close",    icon_left="x", color="error")
    return dd


RICH_COLUMNS = [
    ui.column("id",       label="#",        width="4rem", align="right"),
    ui.column("title",    label="Title"),
    ui.column("status",   label="Status",   render=status_badge),
    ui.column("priority", label="Priority", render=priority_badge),
    ui.column("assignee", label="Assignee", align="center",
              render=assignee_avatar),
    ui.column("",         label="",         align="right",
              render=row_actions),
]


PLAIN_COLUMNS = [
    ui.column("id",       label="#",       width="4rem", align="right"),
    ui.column("title",    label="Title"),
    ui.column("status",   label="Status"),
    ui.column("priority", label="Priority"),
    ui.column("assignee", label="Assignee"),
]


# ── Card 6 — Server events (clickable rows) ──────────────────────────
class TableClicks(PageState):
    log: list = field(default_factory=list)


def open_issue(issue_id) -> None:
    # ``on_item_click`` binds the row's ``row_key`` (here ``id``) and the
    # server receives it. A click on the ⋯ actions menu inside a row does
    # NOT fire this — the row-click guard ignores interactive children.
    state = TableClicks()
    state.log = [*state.log, f"opened #{issue_id}"]


def clear_clicks() -> None:
    TableClicks().log = []


@refreshable(deps=[TableClicks])
def events_panel() -> None:
    state = TableClicks()

    ui.text(
        "Rows are clickable — ``row_key=\"id\"`` + "
        "``on_item_click=open_issue``. Click a row's body to open it ; "
        "click the ⋯ menu and the row click is suppressed "
        "(interactive-child guard). Rows are keyboard operable "
        "(Tab to a row, Enter / Space).",
        color="muted", size="sm",
    )

    ui.table(columns=RICH_COLUMNS, rows=ISSUES,
             row_key="id", on_item_click=open_issue)

    ui.divider()

    with ui.hstack(justify="between", align="center"):
        ui.text("Opened (newest last, last 8)", color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs",
                  on_click=clear_clicks, disabled=not state.log)
    if state.log:
        with ui.vstack(gap="xs"):
            for entry in state.log[-8:]:
                ui.text(entry, color="muted", size="sm",
                        classes="font-mono")
    else:
        ui.text("(click a row above)", color="muted", size="sm")

    ui.divider()

    representative = ui.table(
        columns=PLAIN_COLUMNS, rows=ISSUES[:2],
        row_key="id", on_item_click=open_issue,
    )
    emitted_html_block(
        "Emitted HTML (Table with on_item_click — each <tr> carries its "
        "own hx-post + hx-trigger=\"click[…guard…]\" + role/tabindex)",
        serialize_html(representative),
    )


# ── Card 5 — Server playground ───────────────────────────────────────
class TablePlayground(PageState):
    size:        str  = field(default="md")
    color:       str  = field(default="primary")
    # Data state — flips the preview to the empty branch so the
    # auto EmptyState (and its knobs) can be exercised.
    data:        str  = field(default="populated")
    empty_text:  str  = field(default="No data.")
    empty_icon:  str  = field(default="inbox")
    empty_description: str = field(default="")
    # Escape hatches.
    classes:     str  = field(default="")
    custom_id:   str  = field(default="")
    aria_label:  str  = field(default="")
    style:       str  = field(default="")
    extra_attrs: str  = field(default="")
    # Universal modifiers.
    visible:     str  = field(default="on")
    tooltip:     str  = field(default="")


def server_changed(state: TablePlayground) -> None:
    # Typed param → the dispatcher hydrates the changed control's value
    # into ``state`` (coerced + persisted) ; deps= re-renders the zone.
    pass


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


def build_preview(state: TablePlayground):
    if state.data == "empty":
        kwargs: dict = {
            "columns": PLAIN_COLUMNS,
            "rows": [],
            "empty_text": state.empty_text or "No data.",
            "empty_icon": state.empty_icon or "inbox",
        }
        if state.empty_description:
            kwargs["empty_description"] = state.empty_description
    else:
        kwargs = {"columns": PLAIN_COLUMNS, "rows": ISSUES}
    kwargs.update(size=state.size, color=state.color)
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
    return ui.table(**kwargs)


@refreshable(deps=[TablePlayground])
def server_panel() -> None:
    state = TablePlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("size (cell density)"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("color (header tint)"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("data"):
            ui.select(value=state.data,
                      options=[("populated", "Populated"),
                               ("empty", "Empty (EmptyState)")],
                      on_change=server_changed)
        with control("empty_text (when empty)"):
            ui.input(value=state.empty_text, placeholder="No data.",
                     on_change=server_changed)
        with control("empty_icon (when empty)"):
            ui.select(value=state.empty_icon,
                      options=[(i, i) for i in EMPTY_ICONS],
                      on_change=server_changed)
        with control("empty_description (when empty)"):
            ui.input(value=state.empty_description,
                     placeholder="Try adjusting your filters.",
                     on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="!shadow",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-table",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, placeholder="Issues",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="font-family: monospace",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=table",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder="Issue tracker",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    build_preview(state)

    ui.divider()

    emitted_html_block(
        "Emitted HTML (truncated — large table)",
        serialize_html(build_preview(state)),
    )


def client_events_panel() -> None:
    """The SAME event, wired onto a client expression.

    No ``@refreshable``: that is the point. The log lives in a
    ``ClientState``, the text is re-evaluated in the browser, no request
    leaves.

    WARNING: this card did not exist before 2026-09-06, and the reason
    was mechanical. ``EVENTS`` was empty, so the template read "this
    component has no event" — although the page already carried its
    Server events card. The ClassVar was wrong, not the component. Cf.
    ``.claude/work/audit-declaration-2026-09-06.md``.
    """
    events = TableClientEvents()
    ui.text(
        '``on_item_click`` wired to a client expression that pushes onto '
            'a ClientState. Zero requests.',
        color="muted", size="sm",
    )
    clicked = ClientExpression("String($event.detail ?? 'item_click')")
    ui.table(columns=[ui.column("name", label="Name")],
             rows=[{"id": 1, "name": "Ada"}, {"id": 2, "name": "Linus"}],
             on_item_click=events.log.push(clicked))

    ui.divider()

    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (client-reactif — aucun rafraichissement)",
                color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs",
                  on_click=events.log.clear())
    log_text = ClientExpression(
        "($bz.state.TableClientEvents.default.log || []).join('\\n') || "
            "'(no events yet — click the demo above)'"
    )
    ui.text(log_text, color="muted", size="sm",
            classes="font-mono whitespace-pre")

    ui.divider()

    emitted_html_block(
        "Emitted HTML (item_click client)",
        serialize_html(ui.table(columns=[ui.column("name", label="Name")],
                      rows=[{"id": 1, "name": "Ada"}],
                      on_item_click=events.log.push(clicked))),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Table", level=1)
            ui.text(
                "Data-display primitive — header row + body rows + "
                "custom cell renderers. ``ui.column(key, render=…)`` "
                "declares each column ; ``render=`` callbacks drop "
                "badges / avatars / dropdowns into cells. ``color`` "
                "tints the header (echo it onto a composed "
                "``ui.pagination(color=…)`` so the block reads as one). "
                "Rows become clickable with ``row_key=`` + "
                "``on_item_click=``. Empty rows auto-render an "
                "``EmptyState``. For sort / filter / pagination, wrap "
                "in ``@refreshable``.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every prop + cell "
                            "renderer shape.",
                            color="muted", size="sm")

                    ui.heading("Basic (plain text cells)", level=3)
                    ui.table(columns=PLAIN_COLUMNS, rows=ISSUES)

                    ui.heading("Cell renderers (badges + avatar + "
                               "dropdown)", level=3)
                    ui.table(columns=RICH_COLUMNS, rows=ISSUES)

                    ui.heading("Size — cell density (sm / md / lg)",
                               level=3)
                    ui.text("The striped + hover look is baked in ; "
                            "``size`` is the one density knob.",
                            color="muted", size="xs")
                    with ui.vstack():
                        for s in SIZES:
                            ui.text(f"size={s}", color="muted", size="xs")
                            ui.table(columns=PLAIN_COLUMNS,
                                     rows=ISSUES[:2], size=s)

                    ui.heading("Color — header tint (default primary)",
                               level=3)
                    with ui.vstack():
                        for c in COLORS:
                            ui.text(f"color={c}", color="muted", size="xs")
                            ui.table(columns=PLAIN_COLUMNS,
                                     rows=ISSUES[:2], color=c)

                    ui.heading("head_render — custom header cells", level=3)
                    ui.text(
                        "``head_render=(col) -> Any`` replaces the header "
                        "content, the way ``column(render=…)`` replaces a "
                        "cell's. It is what ``ui.datatable`` uses to put "
                        "its sort buttons in the ``<th>`` — the simple "
                        "table stays a display primitive and just offers "
                        "the seam.",
                        color="muted", size="xs",
                    )
                    ui.table(
                        columns=PLAIN_COLUMNS, rows=ISSUES[:2],
                        head_render=lambda col: ui.badge(
                            col.label or "—", color="muted", variant="soft",
                        ),
                    )

                    ui.heading("Column align + width", level=3)
                    ui.table(
                        columns=[
                            ui.column("id", label="#",
                                      align="right", width="3rem"),
                            ui.column("title", label="Title",
                                      align="left"),
                            ui.column("status", label="Status",
                                      align="center", width="6rem"),
                        ],
                        rows=ISSUES,
                    )

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Edge inputs and the empty-state branch.",
                            color="muted", size="sm")

                    ui.heading("Empty — auto EmptyState (default)",
                               level=3)
                    ui.table(columns=PLAIN_COLUMNS, rows=[])

                    ui.heading("Empty — custom text + icon + description",
                               level=3)
                    ui.table(columns=PLAIN_COLUMNS, rows=[],
                             empty_text="No issues match",
                             empty_icon="search",
                             empty_description="Try clearing the filter "
                             "or widening the date range.")

                    ui.heading("Empty — ``empty=`` escape hatch", level=3)
                    ui.table(
                        columns=PLAIN_COLUMNS, rows=[],
                        empty=lambda: ui.button("Create the first issue",
                                                icon_left="plus",
                                                color="primary"),
                    )

                    ui.heading("Single row", level=3)
                    ui.table(columns=PLAIN_COLUMNS, rows=ISSUES[:1])

                    ui.heading("Many rows (50, size=sm)", level=3)
                    many_rows = [
                        {"id": i, "title": f"Row {i}",
                         "status": "open" if i % 3 else "closed",
                         "priority": ("high" if i % 5 == 0
                                      else "medium" if i % 2 == 0
                                      else "low"),
                         "assignee": ["AL", "JD", "MH", "GH"][i % 4]}
                        for i in range(1, 51)
                    ]
                    ui.table(columns=PLAIN_COLUMNS, rows=many_rows,
                             size="sm")

                    ui.heading("Object rows (getattr lookup)", level=3)

                    class Row:
                        def __init__(self, **kw):
                            self.__dict__.update(kw)

                    ui.table(columns=PLAIN_COLUMNS, rows=[
                        Row(id=1, title="Object row 1", status="open",
                            priority="high", assignee="AL"),
                        Row(id=2, title="Object row 2", status="closed",
                            priority="low", assignee="JD"),
                    ])

                    ui.heading("Missing cell value (renders empty)",
                               level=3)
                    ui.table(columns=PLAIN_COLUMNS,
                             rows=[{"id": 999, "title": "Missing some"}])

                    ui.heading("HTML-special title (XSS escape)", level=3)
                    ui.table(columns=PLAIN_COLUMNS, rows=[{
                        "id": 1, "title": "<script>alert(1)</script>",
                        "status": "open", "priority": "low",
                        "assignee": "AL",
                    }])

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Table in common contexts. Note the "
                            "table + pagination share one ``color``.",
                            color="muted", size="sm")

                    ui.heading("Toolbar + pagination footer", level=3)
                    with ui.card():
                        with ui.vstack():
                            with ui.hstack(justify="between",
                                           align="center"):
                                ui.heading("Issues", level=3)
                                with ui.hstack(gap="sm"):
                                    ui.input(placeholder="Search…",
                                             classes="!w-48")
                                    ui.button("New", icon_left="plus",
                                              color="info")
                            ui.table(columns=RICH_COLUMNS, rows=ISSUES,
                                     color="info")
                            ui.divider()
                            with ui.hstack(justify="between",
                                           align="center"):
                                ui.text("Showing 1–5 of 137",
                                        color="muted", size="sm")
                                ui.pagination(value=1, total_pages=28,
                                              size="sm", color="info")

                    ui.heading("Inside ui.tabs", level=3)
                    with ui.tabs(value="open"):
                        ui.tab("open",   label="Open",   icon="circle")
                        ui.tab("closed", label="Closed",
                               icon="check-circle")
                        with ui.tab_panel(tab="open"):
                            ui.table(columns=PLAIN_COLUMNS,
                                     rows=[r for r in ISSUES
                                           if r["status"] == "open"])
                        with ui.tab_panel(tab="closed"):
                            ui.table(columns=PLAIN_COLUMNS,
                                     rows=[r for r in ISSUES
                                           if r["status"] == "closed"])

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Native ``<table>`` / ``<thead>`` / ``<tbody>`` "
                        "semantics carry through — screen readers "
                        "announce headers + cell positions. Pair with "
                        "``aria_label=`` for a concise description. "
                        "Clickable rows (Server events card) are "
                        "keyboard operable : each row is ``role=\"button\"`` "
                        "+ ``tabindex=0`` and responds to Enter / Space. "
                        "Sortable headers (out of scope for the simple "
                        "Table) should ride on ``aria-sort=``.",
                        color="muted", size="sm",
                    )
                    ui.table(columns=PLAIN_COLUMNS, rows=ISSUES,
                             aria_label="Issue tracker")

            # ── Card 6 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Every visual prop AND every escape hatch is "
                        "wired to a control ; the preview AND the "
                        "emitted HTML both refresh on every change. "
                        "Flip ``data`` to ``Empty`` to exercise the "
                        "auto EmptyState. Columns / rows shape demos "
                        "live in Reference.",
                        color="muted", size="sm",
                    )
                    server_panel()

            # ── Card 7 — Server events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server events", level=2)
                    ui.text(
                        "``on_item_click`` is the table's one event — a "
                        "per-row server action carrying the bound "
                        "``row_key``.",
                        color="muted", size="sm",
                    )
                    events_panel()

            # -- Client events --------------------------------------
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    client_events_panel()
