"""``DatatableState`` — the query a :class:`Datatable` reads and writes.

A Datatable needs somewhere to remember what the user asked for : which
column is sorted and in which direction, which page is showing, what was
typed in the search box. That memory has to survive the action round-trip
(the server rebuilds the page on every click), so it lives in a
:class:`~bretzel.state.PageState`.

Rather than making every app re-declare the same six fields, the
framework ships the schema and the app subclasses it ::

    from bretzel.components import DatatableState

    class Issues(DatatableState):
        per_page: int = field(default=25)          # override a default, or add nothing

    @refreshable
    def issues_table() -> None:
        ui.datatable(state=Issues, columns=COLUMNS, rows=IssueStore().items)

**Subclassing is mandatory** — ``state=DatatableState`` directly would make
two tables on the same page share one query. The subclass *is* the table's
identity (states are keyed by class), so one subclass per table.

The state is deliberately readable : ``Issues().sort_key`` in a handler
tells you what the user is looking at, which is what makes the server-side
CSV export possible — it replays the exact view rather than guessing at
it. That is the whole reason the query lives here instead of in the
browser.
"""

from __future__ import annotations

# DEEP intra-package imports, not a dive: going through ``bretzel.state``
# from here would be a circular import — it is ``state/__init__.py`` that
# loads us. Same shape as ``live_connection.py``, which takes
# ``ClientState`` from ``scopes.client``.
from bretzel.state.datatable.query import Query
from bretzel.state.fields.descriptor import field
from bretzel.state.scopes.server import ServerState


class DatatableState(ServerState, scope="page"):
    """The query behind one Datatable — sort, page, search.

    Three sort positions, cycled by a header click : ``asc`` → ``desc`` →
    **neutral** (``sort_key == ""``, rows in source order). The neutral
    position is reachable, unlike the two-state toggle most table widgets
    ship — once you have sorted those, you can never get the original
    order back. Ported from the V1 datatable, which got this right.

    Subclass it once per table (see the module docstring). Every field
    has a working default, so a bare ``class Issues(DatatableState): pass``
    is a complete declaration.
    """

    # Column key currently sorted on. Empty string = source order.
    sort_key: str = field(default="", url="sort")
    # ``"asc"`` / ``"desc"``. Only meaningful while ``sort_key`` is set ;
    # kept across a reset to neutral so re-sorting the same column
    # resumes where it left off rather than always restarting ascending.
    sort_dir: str = field(default="asc", url="dir")
    # 1-indexed, to pair directly with ``ui.pagination`` (whose ``value``
    # runs 1…total_pages).
    page: int = field(default=1, url="p")
    per_page: int = field(default=20, url="size")
    # Global search box. Matched case-insensitively against every
    # column's stringified value.
    search: str = field(default="", url="q")
    #: ⚠️ ``filters`` **deliberately has NO** ``url=``, and that is what
    #: keeps it out of the address: ``addressable=True`` only lights up
    #: the fields the framework has named. Two reasons, one technical and
    #: one decisive.
    #:
    #: Technical: it is a ``dict``, a query only carries strings, and no
    #: format exists for this one yet (the declaration is refused, cf.
    #: :mod:`bretzel.state.url`).
    #:
    #: Decisive: a filter value is the most likely thing to be personal —
    #: ``?status=in_collection`` ends up in the server access logs and in
    #: the ``Referer`` of the first external link clicked from the page.
    #:
    #: If you want a filter to SURVIVE without being published, the URL is
    #: not what you need: the scope is. ``class Issues(DatatableState,
    #: scope="session")`` and the filter crosses navigations, server-side,
    #: exposing nothing.
    #
    # Per-column narrowing : ``{column_key: [shown values]}``. A key only
    # appears while the reader has ticked SOME values of the column :
    # ticking none and ticking all are both "no filter" — the same view —
    # so neither is stored (the full domain would make the state grow with
    # the data). An empty list is never stored.
    filters: dict = field(default_factory=dict)

    def to_query(self, *, for_export: bool = False) -> Query:
        """Snapshot this state as the value object handed to a callable.

        The state is STORAGE (mutable, scoped, tracked) ; :class:`Query`
        is the value that travels — frozen, so a rows callable can't
        change what the component believes it rendered. Reading the six
        fields here is also the one place that pays the descriptor cost.
        """
        # Coerced to PLAIN builtins on the way out. A State field hands
        # back a tracked str subclass, and those do not survive
        # ``dataclasses.asdict`` — which the export link needs, since it
        # serialises the query into its URL. The value object holding
        # values rather than instrumented ones is the point of it.
        return Query(
            sort_key=str(self.sort_key),
            sort_dir=str(self.sort_dir),
            # ``for_export``: the page is NORMALISED to 1, not copied.
            # ``Query.offset`` already returns 0 in that mode, so the
            # value has no effect — but it is serialised into the signed
            # URL of the CSV button, and a URL that changes on every
            # pagination would make the toolbar differ on every page
            # change — and the zone diff ship it again each time.
            page=1 if for_export else int(self.page),
            per_page=max(1, int(self.per_page)),
            search=str(self.search),
            # An empty list never leaves : it would read as "match nothing"
            # in a callable's ``.in_(values)``, and here it means no filter.
            filters={
                str(key): [str(v) for v in values]
                for key, values in self.filters.items() if values
            },
            for_export=for_export,
        )

    def toggle_filter(self, key: str, value: str, domain: list[str]) -> None:
        """Tick / untick one value in ``key``'s filter.

        ⚠️ No call site left in the component since the panel applies in
        ONE action on close (``set_filter``). Kept as public surface of
        ``DatatableState``: a user handler may want to toggle a value
        from elsewhere (a click on a row badge, a shortcut). If nobody
        uses it by 2.0, it goes.

        The first tick on an untouched column shows that value alone ;
        unticking the last one — or ticking the last missing one — drops
        the key, so the column filters nothing again.
        """
        current = list(self.filters.get(key, ()))
        if value in current:
            current.remove(value)
        else:
            current.append(value)
        self.set_filter(key, current, domain)

    def clear_filter(self, key: str) -> None:
        """Drop ``key``'s filter — the column stops narrowing anything."""
        updated = dict(self.filters)
        updated.pop(key, None)
        self.filters = updated
        self.page = 1

    def set_filter(self, key: str, values: list[str], domain: list[str]) -> None:
        """Show only ``values`` of column ``key`` — none or all of them
        means no filter.

        Neither is stored : ticking nothing and ticking everything both
        show every row, and the full domain would make the state grow with
        the data. The kept values follow ``domain`` order — the panel
        lists the domain, and a value that jumped position on every toggle
        would read as the list reshuffling itself.
        """
        # dict field : reassign, never mutate in place, or the snapshot
        # diff sees no change and the zone never re-renders.
        updated = dict(self.filters)
        if not values or set(values) == set(domain):
            updated.pop(key, None)
        else:
            updated[key] = [v for v in domain if v in values]
        self.filters = updated
        self.page = 1

    def clear_filters(self) -> None:
        """Drop every column filter — the "reset" the toolbar offers."""
        self.filters = {}
        self.page = 1

    def cycle_sort(self, key: str) -> None:
        """Advance the sort on ``key`` one position : asc → desc → neutral.

        Clicking a *different* column starts it ascending. Any sort change
        sends the reader back to page 1 — staying on page 7 of a list that
        was just reordered shows rows they never asked for.
        """
        if self.sort_key != key:
            self.sort_key = key
            self.sort_dir = "asc"
        elif self.sort_dir == "asc":
            self.sort_dir = "desc"
        else:
            # Third click on the same column : back to source order. The
            # direction is intentionally NOT reset — cf. the field comment.
            self.sort_key = ""
        self.page = 1
