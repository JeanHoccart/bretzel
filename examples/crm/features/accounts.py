"""features/accounts — screen 2: the accounts, 50 000 rows, callable mode.

What this screen puts under constraint: ``ui.datatable`` with a
**callable** ``rows=``. Sorting, searching, column filters and CSV export
are translated into SQL by
:func:`~examples.crm.features.accounts_data.load_accounts`; the page
never loads more than twenty rows.

Two things the list tier does not require and this one imposes:

- every filter's domain is **declared** (``filter=[…]``) — the component
  holds no row to derive it from, and raises if given ``filter=True``;
- ``exportable=True`` **requires** the callable tier, because the CSV
  replays the query outside the render that threw the rows away.
"""

from __future__ import annotations

from bretzel import (
    Feature,
    page,
    refreshable,
    ui,
)
from bretzel.state import field
# ``DatatableState`` is imported from ``bretzel.components``, not from
# ``bretzel``: the file moved down into ``bretzel/state/`` but the DOOR
# stayed the component's (6baaf918). The repository's two other sites
# using it — ``crm/features/import_screen.py`` and
# ``playground/features/datatable.py`` — already wrote it that way.
from bretzel.components import DatatableState
from examples.crm.core.domain import (
    COUNTRY_KEYS,
    INDUSTRIES,
    OWNERS,
    SIZES,
    euros,
)
from examples.crm.core.ui import kpi
from examples.crm.features.access import ViewerPrefs, visible_owner
from examples.crm.features.accounts_data import accounts_summary, load_accounts
from examples.crm.features.shell import shell


class AccountsTable(DatatableState, scope="session", addressable=True):
    """THIS table's query. One subclass per table: states are keyed by
    class, so sharing the base would share the sort and the page.

    ``addressable=True``: **the view has an address.** Sorting,
    paginating or searching rewrites the URL, so the link shares,
    bookmarks, and the browser's arrows go back and forth. The names come
    from ``DatatableState`` (``tri`` / ``sens`` / ``p`` / ``q``); a
    ``URL = {…}`` would rename them.

    ``filters`` is NOT part of it, and the base layer guarantees it — it
    has no URL name, so the opt-in cannot turn it on. Sorting a list of
    accounts has nothing sensitive about it; filters set on a client
    portfolio do.
    """

    per_page: int = field(default=25)
    sort_key: str = field(default='name')


def arr_cell(value, _row):
    return ui.text(euros(value), weight="medium")


def size_cell(value, _row):
    colors = {"TPE": "muted", "PME": "info", "ETI": "primary",
              "Grand compte": "success"}
    return ui.badge(value, color=colors.get(value, "muted"), variant="soft",
                    size="xs")


def name_cell(value, row):
    """The account's name, as a LINK to its sheet.

    ⚠️ A link, not an ``on_item_click=`` that redirects. Both open the
    sheet and they do not navigate alike: the action makes the server
    answer ``HX-Redirect``, which htmx applies as ``window.location`` —
    the document is destroyed, the shell repainted, in two requests.
    Measured on 2026-09-12 on ``examples/atelier``: a marker set on
    ``window`` before the click did not survive it. An ``<a>`` goes
    through the shell's ``hx-boost``: one request, only the region
    changes.

    It is what :func:`bretzel.redirect`'s docstring says — "for a menu, a
    clickable row, a breadcrumb, navigation stays a ``ui.link``". It
    reserves ``redirect()`` for addresses that only exist AFTER a
    mutation.
    """
    return ui.link(value, href=f"/accounts/{row['id']}", variant="hover")


COLUMNS = [
    ui.column("name", label="Account", sortable=True, render=name_cell),
    ui.column("industry", label="Industry", sortable=True,
              filter=list(INDUSTRIES)),
    ui.column("country", label="Country", sortable=True,
              filter=list(COUNTRY_KEYS)),
    ui.column("city", label="City", sortable=True),
    ui.column("size", label="Size", sortable=True, filter=list(SIZES),
              render=size_cell),
    ui.column("arr", label="ARR", sortable=True, align="right",
              render=arr_cell),
    ui.column("owner", label="Owner", sortable=True,
              filter=list(OWNERS)),
]


def columns_for(owner: str | None) -> list:
    """The table's columns, according to the scoping.

    ⚠️ The "Owner" column loses its filter when scoped: five of
    its six values would return zero rows and the sixth would do nothing.
    It is the same reasoning as the three selectors removed elsewhere — a
    control that can take only one legal value is not a control — but it
    showed less here, because the affordance is data in a constant, not a
    ``ui.select`` in a function body.
    """
    if owner is None:
        return COLUMNS
    return [c for c in COLUMNS if c.key != "owner"]


# A single dep: screen 2 only READS. A revision token declared here
# would be a reactivity path that does not exist — the next reader would
# copy it onto a table that writes and believe the bump automatic.
def scoped_rows(q):
    """The ``rows=`` the datatable calls, scoped to the portfolio.

    ⚠️ The component calls its callable with the ``Query`` ONLY — it has
    no way of passing it a context. A scoped repo therefore takes one
    more parameter, and the screen must supply this closure. It is the
    price of the choice "the scoping is a parameter" (cf. ``access.py``),
    and it is paid here, once, visibly.
    """
    return load_accounts(q, visible_owner())


# ``ViewerPrefs`` in the ``deps``: without it, changing portfolio in the
# sidebar would leave the zone on the previous one's data.
@refreshable(deps=[AccountsTable, ViewerPrefs])
def accounts_table() -> None:
    ui.datatable(
        state=AccountsTable,
        columns=columns_for(visible_owner()),
        rows=scoped_rows,
        search_placeholder="Name, city, industry, owner…",
        exportable=True,
        export_filename="accounts.csv",
        max_height="calc(100vh - 20rem)",
        row_key="id",
    )


def summary_header() -> None:
    scope = visible_owner()
    stats = accounts_summary(scope)
    with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
        kpi("Accounts", f"{stats['total']:,}".replace(",", " "),
            "building-2", "primary")
        kpi("Cumulative ARR", euros(stats["arr"]), "banknote", "success")
        kpi("Owners", "1" if scope else str(len(OWNERS)),
            "user-round", "info")


@page("/accounts", layout=shell, title="Accounts")
def accounts_page() -> None:
    with ui.vstack(gap="lg"):
        ui.heading("Accounts", level=1, size="2xl")
        summary_header()
        accounts_table()


feature = Feature(
    name="accounts",
    kind="page",
    provides=[accounts_page, AccountsTable],
    uses=["accounts_data", "access"],
)
