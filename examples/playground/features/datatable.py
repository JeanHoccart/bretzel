"""``Datatable`` test bench.

Cards (per ``playground-pattern.md``) : Reference / Edge cases /
Composability / A11y / Server playground / Server events / Client events.

``BINDABLE_PROPS = ()`` → **no Client playground card.** The whole query
(sort / page / search) lives in a server ``DatatableState`` : a click
mutates it and the enclosing ``@refreshable`` re-renders with the new
query baked in. There is no client driver for anything here, by design —
that is what makes the selection readable from Python.

⚠️ La carte **Client events**, elle, est obligatoire — et cette ligne a
dit le contraire pendant des mois. Elle amalgamait deux ClassVar : c'est
``BINDABLE_PROPS`` qui décide de la carte Client PLAYGROUND, et
``EVENTS`` qui décide des DEUX cartes d'events. Le composant accepte
``on_item_click=`` — il le transmet à la ``ui.table`` qu'il compose —
donc il accepte aussi une expression cliente, comme tout ``on_*`` du
framework. Il l'a déclaré le 2026-09-07, dernier des quatre.

**Two rules this page demonstrates by obeying them**, both enforced at
construction :

1. **One ``DatatableState`` subclass per table.** States are keyed by
   class, so two tables sharing one subclass would share one sort and
   one page.
2. **An interactive table lives in a ``@refreshable(deps=[ItsState])``.**
   Without the zone, clicking a header posts, mutates the state, and the
   page never changes. ``ui.datatable`` raises rather than let that ship.

Purely static demos (a size ladder, a colour ladder) opt out of both by
having no sortable column and ``search=False`` — nothing to mutate, so
they share one state class and need no zone.
"""

from __future__ import annotations

from bretzel import refreshable, ui
from bretzel.components import DatatableState, Query, apply_query
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field
from examples.playground.features.inspection import emitted_html_block

PATH = "/datatable"


COLORS = ["primary", "secondary", "success", "warning",
          "error", "info", "muted"]
SIZES = ["sm", "md", "lg"]
EMPTY_ICONS = ["inbox", "database", "search", "folder", "file-x"]


# ── Data ─────────────────────────────────────────────────────────────
_TITLES = [
    "Pagination overflow on long lists", "Tooltip flickers on hover",
    "Form submit double-fires", "Dropdown closes immediately",
    "Dialog doesn't focus first input", "Sticky header drops on morph",
    "Sort arrow points the wrong way", "Search box loses focus",
    "Empty state hides the toolbar", "Row click fires inside a button",
    "Column width ignored on Safari", "Avatar initials overflow",
]
_STATUSES = ["open", "merged", "closed"]
_PRIORITIES = ["high", "medium", "low"]
_PEOPLE = ["AL", "JD", "MH", "GH", "RF"]

ISSUES = [
    {
        "id": 100 + i,
        "title": _TITLES[i % len(_TITLES)],
        "status": _STATUSES[i % 3],
        "priority": _PRIORITIES[(i * 2) % 3],
        "assignee": _PEOPLE[i % 5],
        # Deliberately uneven : a None and an empty string, so the
        # blanks-sort-last behaviour is visible rather than asserted.
        "score": None if i == 4 else "" if i == 9 else (i * 7) % 100,
    }
    for i in range(34)
]


class Row:
    """Attribute-access row, to exercise the ``getattr`` lookup path."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


# ── Cell renderers ───────────────────────────────────────────────────
def status_badge(value, _row):
    color = {"open": "info", "merged": "success",
             "closed": "muted"}.get(value, "muted")
    return ui.badge(value, color=color)


def priority_badge(value, _row):
    color = {"high": "error", "medium": "warning",
             "low": "muted"}.get(value, "muted")
    return ui.badge(value, color=color, variant="solid")


def assignee_avatar(value, _row):
    # ``xs`` (24 px) et pas le defaut (40 px) : c'est l'avatar qui fixe la
    # hauteur de ligne, et 40 px poussait la rangee a 61 px pour du texte
    # de 14 px. A 24 px la ligne retombe a 44 px, la densite des tables de
    # travail (Linear, GitHub, shadcn).
    return ui.avatar(initials=value, color="primary", size="xs")


def row_actions(_value, row):
    dd = ui.dropdown(
        # ``sm`` et pas le defaut : avec l'avatar ramene a 24 px, c'est ce
        # bouton qui fixait seul la hauteur de ligne a 61 px. Meme
        # raisonnement, meme cible de densite.
        trigger=ui.icon_button("more-horizontal", variant="ghost", size="xs",
                               aria_label=f"Actions for #{row['id']}"),
        align="end",
    )
    with dd:
        ui.dropdown_item(label="Open",     icon_left="arrow-up-right")
        ui.dropdown_item(label="Reassign", icon_left="user")
        ui.dropdown_item(label="Close",    icon_left="x", color="error")
    return dd


# Sortable where sorting means something : an id, a title, a score. The
# status / priority columns are rendered as badges — sortable too, since
# sorting runs on the RAW value, not on what ``render=`` produced.
def load_issues(q: Query) -> tuple[list, int]:
    """The tier-2 shape : you own the pipeline, the component asks.

    Here it just delegates to the same in-memory helper the list tier
    uses — a real app would build a SQL query from ``q`` instead. What
    matters is that it can be re-run OUT of band, which is what makes the
    CSV export possible at all.
    """
    return apply_query(ISSUES, SORTABLE_COLUMNS, q)


SORTABLE_COLUMNS = [
    ui.column("id",       label="#",        width="4.5rem", align="right",
              sortable=True),
    # The free-text column gets the room : without a hint the browser
    # splits the width by content and the badge columns win, wrapping
    # every title over three lines.
    ui.column("title",    label="Title",    sortable=True, width="38%"),
    # Domain stated rather than derived : the Reference table runs in the
    # callable tier, where the component holds no rows to inspect. The
    # Edge-cases table below uses ``filter=True`` on the same column, and
    # that one IS a plain list.
    ui.column("status",   label="Status",   sortable=True,
              filter=["open", "merged", "closed"], render=status_badge),
    ui.column("priority", label="Priority", sortable=True,
              filter=["high", "medium", "low"], render=priority_badge),
    # Filtrable sur un domaine EXPLICITE de 12 personnes alors que les
    # donnees n'en montrent que 5 : c'est la seule colonne du banc qui
    # depasse le seuil de 8, donc la seule ou la RECHERCHE du popover
    # apparaisse. Sans elle cette affordance n'etait exercee nulle part et
    # ne pouvait se verifier qu'en test.
    ui.column("assignee", label="Assignee", align="center",
              filter=["AL", "JD", "MH", "GH", "RF",
                      "BK", "CN", "DP", "ES", "FT", "IV", "LW"],
              render=assignee_avatar),
    ui.column("score",    label="Score",    align="right", sortable=True),
    ui.column("",         label="",         align="right",
              render=row_actions),
]

PLAIN_COLUMNS = [
    ui.column("id",     label="#",      width="4.5rem", align="right"),
    ui.column("title",  label="Title"),
    ui.column("status", label="Status"),
    ui.column("score",  label="Score",  align="right"),
]


# ── State — one subclass per live table ──────────────────────────────
class RefQuery(DatatableState):
    """The Reference card's live table."""
    per_page: int = field(default=8)


class StaticQuery(DatatableState):
    """Shared by every non-interactive demo — nothing ever mutates it."""


class EdgeQuery(DatatableState):
    per_page: int = field(default=5)


class ComposeQuery(DatatableState):
    per_page: int = field(default=5)


class A11yQuery(DatatableState):
    per_page: int = field(default=5)


class EventsQuery(DatatableState):
    per_page: int = field(default=5)


class PreviewQuery(DatatableState):
    """The Server playground preview's own query."""
    per_page: int = field(default=6)


# The size ladder shows the FULL component at each density — search box,
# sort headers and pager included — because that is what you actually
# judge when picking a size. One query state per rung : they are live
# tables, and a shared state would make all three sort together.
class SizeSmQuery(DatatableState):
    per_page: int = field(default=4)


class SizeMdQuery(DatatableState):
    per_page: int = field(default=4)


class SizeLgQuery(DatatableState):
    per_page: int = field(default=4)


SIZE_LADDER = [("sm", SizeSmQuery), ("md", SizeMdQuery), ("lg", SizeLgQuery)]


# ── Card 1 — Reference ───────────────────────────────────────────────
@refreshable(deps=[RefQuery])
def reference_panel() -> None:
    ui.text(
        "The full component. Click a header to sort (asc → desc → back "
        "to source order) ; the filter buttons in the toolbar narrow by "
        "value ; type to search ; page through the result. This one runs "
        "in the CALLABLE tier (``rows=load_issues``), which is what lets "
        "the CSV button export every matching row rather than the page "
        "on screen. Every click is a server round-trip — "
        "``RefQuery().sort_key`` is readable from any handler.",
        color="muted", size="sm",
    )
    ui.datatable(state=RefQuery, columns=SORTABLE_COLUMNS,
                 rows=load_issues, exportable=True,
                 export_filename="issues.csv",
                 search_placeholder="Search issues…")


def size_row(size: str, query) -> None:
    """Un barreau de l'échelle. Partagé par les trois zones ci-dessous."""
    with ui.vstack(gap="xs"):
        ui.text(f"size={size}", color="muted", size="xs")
        ui.datatable(state=query, columns=SORTABLE_COLUMNS,
                     rows=ISSUES, size=size,
                     search_placeholder=f"Search ({size})…")


# UNE zone par table, et pas une zone pour les trois. Une zone se
# re-rend quand N'IMPORTE LEQUEL de ses `deps` bouge : avec
# `deps=[SizeSmQuery, SizeMdQuery, SizeLgQuery]`, changer de page sur la
# table `sm` re-rendait AUSSI `md` et `lg` — trois tableaux complets pour
# un clic, ce qui se voit à l'écran. Les trois états sont indépendants,
# donc les trois zones le sont.
@refreshable(deps=[SizeSmQuery])
def size_sm_panel() -> None:
    size_row("sm", SizeSmQuery)


@refreshable(deps=[SizeMdQuery])
def size_md_panel() -> None:
    size_row("md", SizeMdQuery)


@refreshable(deps=[SizeLgQuery])
def size_lg_panel() -> None:
    size_row("lg", SizeLgQuery)


def size_ladder_panel() -> None:
    """L'échelle entière — trois zones indépendantes empilées.

    Volontairement PAS un `@refreshable` : ce n'est plus qu'une mise en
    page. Le rafraîchissement vit au niveau de chaque barreau.
    """
    with ui.vstack(gap="lg"):
        size_sm_panel()
        size_md_panel()
        size_lg_panel()


# ── Card 2 — Edge cases ──────────────────────────────────────────────
@refreshable(deps=[EdgeQuery])
def edge_panel() -> None:
    ui.text(
        "Search for something absent (``zzz``) : the empty state shows, "
        "the footer still reports ``0 results of 34``, and the pager "
        "disappears rather than offering pages that don't exist.",
        color="muted", size="sm",
    )
    ui.datatable(
        state=EdgeQuery, columns=SORTABLE_COLUMNS, rows=ISSUES,
        empty_text="No issue matches",
        empty_icon="search",
        empty_description="Clear the search box or widen the filter.",
    )


# ── Card 5 — Server playground ───────────────────────────────────────
class DatatablePlayground(PageState):
    size:               str = field(default="md")
    color:              str = field(default="primary")
    search:             str = field(default="on")
    search_placeholder: str = field(default="Search…")
    max_height:         str = field(default="")
    data:               str = field(default="populated")
    empty_text:         str = field(default="No data.")
    empty_icon:         str = field(default="inbox")
    empty_description:  str = field(default="")
    # Escape hatches.
    classes:     str = field(default="")
    custom_id:   str = field(default="")
    aria_label:  str = field(default="")
    style:       str = field(default="")
    extra_attrs: str = field(default="")
    # Universal modifiers.
    visible: str = field(default="on")
    tooltip: str = field(default="")


def server_changed(state: DatatablePlayground) -> None:
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


def build_preview(state: DatatablePlayground):
    kwargs: dict = {
        "state": PreviewQuery,
        "columns": SORTABLE_COLUMNS,
        "rows": [] if state.data == "empty" else ISSUES,
        "size": state.size,
        "color": state.color,
        "search": state.search == "on",
        "empty_text": state.empty_text or "No data.",
        "empty_icon": state.empty_icon or "inbox",
    }
    if state.search_placeholder:
        kwargs["search_placeholder"] = state.search_placeholder
    if state.max_height:
        kwargs["max_height"] = state.max_height
    if state.empty_description:
        kwargs["empty_description"] = state.empty_description
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
    return ui.datatable(**kwargs)


# L'apercu depend des DEUX (il lit la config ET pagine) ; la grille de
# quinze controles ne depend que de la config. Reunies, changer de page
# dans l'apercu reconstruisait les quinze selects.
@refreshable(deps=[DatatablePlayground, PreviewQuery])
def preview_panel() -> None:
    state = DatatablePlayground()
    build_preview(state)
    ui.divider()
    # Le HTML emis appartient a l'apercu, pas a la grille : il RECONSTRUIT
    # un `ui.datatable(state=PreviewQuery)`, donc il doit vivre dans une
    # zone qui surveille cet etat. Le garde de construction du datatable
    # le dit lui-meme si on l'oublie — il l'a dit.
    emitted_html_block(
        "Emitted HTML (truncated — large table)",
        serialize_html(build_preview(state)),
    )


@refreshable(deps=[DatatablePlayground])
def server_panel() -> None:
    state = DatatablePlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("size (density + child sizes)"):
            ui.select(value=state.size, options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("color (header tint + pager)"):
            ui.select(value=state.color, options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("search (show the box)"):
            ui.select(value=state.search,
                      options=[("on", "True (default)"), ("off", "False")],
                      on_change=server_changed)
        with control("search_placeholder"):
            ui.input(value=state.search_placeholder, placeholder="Search…",
                     on_change=server_changed)
        with control("max_height (→ scroll + sticky header)"):
            ui.input(value=state.max_height, placeholder="18rem",
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
            ui.input(value=state.classes, placeholder="!gap-6",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-datatable",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, placeholder="Issues",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="font-family: monospace",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=datatable",
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

    preview_panel()


# ── Card 6 — Server events ───────────────────────────────────────────
class DatatableClicks(PageState):
    log: list = field(default_factory=list)


def open_issue(issue_id) -> None:
    # ``on_item_click`` is forwarded to the composed ``ui.table`` — the
    # bound ``row_key`` arrives here. A click on the ⋯ menu inside a row
    # does NOT fire it (interactive-child guard), and neither does a
    # click on a sort header, which is a button.
    state = DatatableClicks()
    state.log = [*state.log, f"opened #{issue_id}"]


def clear_clicks() -> None:
    DatatableClicks().log = []


# DEUX zones : la table repond a `EventsQuery` (tri / page / recherche),
# le journal a `DatatableClicks` (les clics de ligne). Reunies, chaque
# changement de page reconstruisait le journal, et chaque clic de ligne
# reconstruisait le tableau — deux fois plus de travail que necessaire,
# des deux cotes.
# ``EventsQuery`` aussi : ce panneau est appelé DANS ``events_panel``,
# donc un tri ou une page le redessine de toute façon. Le déclarer, ou
# sortir le panneau — ici il est inline, entre la table et son HTML.
@refreshable(deps=[DatatableClicks, EventsQuery])
def click_log_panel() -> None:
    state = DatatableClicks()
    with ui.vstack():
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


# ── Card 7 — Client events ───────────────────────────────────────────
class DatatableClientEvents(ClientState):
    """Le journal de la carte Client events — côté navigateur."""

    log: list = field(default_factory=list)


class ClientEventsQuery(DatatableState):
    """Une sous-classe par table — la règle du composant."""


def client_events_panel() -> None:
    """Le MÊME event, câblé sur une expression cliente.

    Pas de ``@refreshable`` : c'est le point. Le journal vit dans un
    ``ClientState``, le texte se réévalue dans le navigateur, aucune
    requête ne part.

    ⚠️ Cette carte n'existait pas avant le 2026-09-07, et la raison
    était la même que pour ``ui.table`` la veille : ``EVENTS`` était
    vide, donc le gabarit lisait « ce composant n'a pas d'event » —
    alors que la page portait déjà sa carte Server events. Le ClassVar
    était faux, pas le composant.
    """
    events = DatatableClientEvents()
    ui.text(
        "``on_item_click`` câblé sur une expression cliente qui empile "
        "dans un ClientState. Zéro requête — et le datatable ne câble "
        "rien lui-même : il transmet à la table qu'il compose, donc les "
        "trois formes d'un ``on_*`` valent ici comme là.",
        color="muted", size="sm",
    )
    clicked = ClientExpression("String($event.detail ?? 'item_click')")
    ui.datatable(
        state=ClientEventsQuery,
        columns=[ui.column("name", label="Name")],
        rows=[{"id": 1, "name": "Ada"}, {"id": 2, "name": "Linus"}],
        row_key="id",
        search=False,
        on_item_click=events.log.push(clicked),
    )

    ui.divider()

    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (client-réactif — aucun rafraîchissement)",
                color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs",
                  on_click=events.log.clear())
    log_text = ClientExpression(
        r"($bz.state.DatatableClientEvents.default.log || []).join('\n')"
        r" || '(aucun event — clique la démo ci-dessus)'"
    )
    ui.text(log_text, color="muted", size="sm",
            classes="font-mono whitespace-pre")

    ui.divider()

    emitted_html_block(
        "Emitted HTML (item_click client)",
        serialize_html(ui.datatable(
            state=ClientEventsQuery,
            columns=[ui.column("name", label="Name")],
            rows=[{"id": 1, "name": "Ada"}],
            row_key="id",
            search=False,
            on_item_click=events.log.push(clicked),
        )),
    )


@refreshable(deps=[EventsQuery])
def events_panel() -> None:
    ui.text(
        "``row_key=\"id\"`` + ``on_item_click=open_issue``, forwarded to "
        "the composed table. Sort and page while clicking rows : the "
        "row key is bound per row at render, so it stays correct after "
        "a re-sort.",
        color="muted", size="sm",
    )

    ui.datatable(state=EventsQuery, columns=SORTABLE_COLUMNS, rows=ISSUES,
                 row_key="id", on_item_click=open_issue)

    ui.divider()

    click_log_panel()

    ui.divider()

    emitted_html_block(
        "Emitted HTML (sort headers carry hx-post + the bound column "
        "key ; each <tr> carries its own row action)",
        serialize_html(ui.datatable(
            state=EventsQuery, columns=PLAIN_COLUMNS, rows=ISSUES[:2],
            search=False, row_key="id", on_item_click=open_issue,
        )),
    )


# ── Card 3 — Composability ───────────────────────────────────────────
@refreshable(deps=[ComposeQuery])
def compose_panel() -> None:
    with ui.card():
        with ui.vstack():
            with ui.hstack(justify="between", align="center"):
                ui.heading("Issues", level=3)
                ui.button("New", icon_left="plus", color="info")
            ui.datatable(state=ComposeQuery, columns=SORTABLE_COLUMNS,
                         rows=ISSUES, color="info", size="sm")


# ── Card 4 — A11y ────────────────────────────────────────────────────
@refreshable(deps=[A11yQuery])
def a11y_panel() -> None:
    ui.datatable(state=A11yQuery, columns=SORTABLE_COLUMNS, rows=ISSUES,
                 aria_label="Issue tracker", max_height="16rem")


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Datatable", level=1)
            ui.text(
                "``ui.table`` plus a query : sort, pagination and global "
                "search, all server-side. It assembles rather than "
                "reimplements — the grid is a composed ``ui.table``, the "
                "sort control a ``ui.button``, the search box a "
                "``ui.input``, the pager a ``ui.pagination``. Declare one "
                "``DatatableState`` subclass per table and wrap it in a "
                "``@refreshable`` that watches it. ``rows=`` takes a list "
                "(the component runs the pipeline) or a callable "
                "``(q: Query) -> (rows, total)`` — the callable tier is "
                "what unlocks the CSV export, since the server has to be "
                "able to re-run your query outside the render. Row "
                "selection and bulk actions are not in this slice.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    reference_panel()

                    ui.divider()

                    ui.heading("Size — density + the composed children",
                               level=3)
                    ui.text(
                        "The whole component at each density — search box, "
                        "sort headers, pager. ``size`` drives the cell "
                        "padding, the footer type scale and the pager ; the "
                        "HEADER type scale is deliberately fixed, so a "
                        "sortable title stays aligned with a plain one.",
                        color="muted", size="xs",
                    )
                    size_ladder_panel()

                    ui.heading("Color — header tint + pager accent",
                               level=3)
                    with ui.vstack():
                        for c in COLORS:
                            ui.text(f"color={c}", color="muted", size="xs")
                            ui.datatable(state=StaticQuery,
                                         columns=PLAIN_COLUMNS,
                                         rows=ISSUES[:3], color=c,
                                         search=False)

                    ui.heading("search=False — no toolbar at all", level=3)
                    ui.datatable(state=StaticQuery, columns=PLAIN_COLUMNS,
                                 rows=ISSUES[:3], search=False)

            # ── Card 2 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    edge_panel()

                    ui.divider()

                    ui.heading("Empty source (auto EmptyState)", level=3)
                    ui.datatable(state=StaticQuery, columns=PLAIN_COLUMNS,
                                 rows=[], search=False)

                    ui.heading("Empty — ``empty=`` escape hatch", level=3)
                    ui.datatable(
                        state=StaticQuery, columns=PLAIN_COLUMNS, rows=[],
                        search=False,
                        empty=lambda: ui.button("Create the first issue",
                                                icon_left="plus",
                                                color="primary"),
                    )

                    ui.heading("Single row — no pager, count still shown",
                               level=3)
                    ui.datatable(state=StaticQuery, columns=PLAIN_COLUMNS,
                                 rows=ISSUES[:1], search=False)

                    ui.heading("Missing / blank cells", level=3)
                    ui.text(
                        "Row 105 has ``score=None`` and row 110 has "
                        "``score=\"\"``. Sort the Score column in the "
                        "Reference table both ways : blanks stay at the "
                        "bottom in BOTH directions, because a screen full "
                        "of blanks is never what a header click meant.",
                        color="muted", size="xs",
                    )
                    ui.datatable(state=StaticQuery, columns=PLAIN_COLUMNS,
                                 rows=[ISSUES[4], ISSUES[9], ISSUES[0]],
                                 search=False)

                    ui.heading("HTML-special title (XSS escape)", level=3)
                    ui.datatable(
                        state=StaticQuery, columns=PLAIN_COLUMNS,
                        search=False,
                        rows=[{"id": 1, "title": "<script>alert(1)</script>",
                               "status": "open", "score": 1}],
                    )

                    ui.heading("Object rows (getattr lookup)", level=3)
                    ui.datatable(state=StaticQuery, columns=PLAIN_COLUMNS,
                                 search=False, rows=[
                                     Row(id=1, title="Object row 1",
                                         status="open", score=12),
                                     Row(id=2, title="Object row 2",
                                         status="closed", score=3),
                                 ])

            # ── Card 3 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text(
                        "Inside a card with its own header row, and "
                        "inside tabs. ``color`` flows to the header tint "
                        "and the pager so the block reads as one.",
                        color="muted", size="sm",
                    )
                    compose_panel()

                    ui.heading("Inside ui.tabs", level=3)
                    with ui.tabs(value="all"):
                        ui.tab("all",  label="All",  icon="list")
                        ui.tab("open", label="Open", icon="circle")
                        with ui.tab_panel(tab="all"):
                            ui.datatable(state=StaticQuery,
                                         columns=PLAIN_COLUMNS,
                                         rows=ISSUES[:4], search=False)
                        with ui.tab_panel(tab="open"):
                            ui.datatable(
                                state=StaticQuery, columns=PLAIN_COLUMNS,
                                search=False,
                                rows=[r for r in ISSUES[:12]
                                      if r["status"] == "open"],
                            )

            # ── Card 4 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Native ``<table>`` semantics carry through from "
                        "the composed table. Each sortable header is a "
                        "real ``<button>`` — reachable by Tab, activated "
                        "by Enter / Space, with the focus ring every "
                        "other button in the app has. The search box is "
                        "a real ``<input>``. ``max_height`` here also "
                        "pins the header while the body scrolls.",
                        color="muted", size="sm",
                    )
                    a11y_panel()

            # ── Card 5 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Every visual prop AND every escape hatch is "
                        "wired to a control ; the preview AND the emitted "
                        "HTML both refresh on every change. The preview "
                        "keeps its own query state, so sorting it does "
                        "not disturb the other cards.",
                        color="muted", size="sm",
                    )
                    server_panel()

            # ── Card 6 — Server events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server events", level=2)
                    ui.text(
                        "``on_item_click`` is forwarded to the composed "
                        "table — the datatable declares no event of its "
                        "own.",
                        color="muted", size="sm",
                    )
                    events_panel()

            # ── Card 7 — Client events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    client_events_panel()

