"""features/search — screen 8: the global search.

What this screen puts under constraint: the use case that would decide
``ui.command_palette``. It is built here with what exists — a debounced
``ui.input``, three grouped lists, and navigation by click — so the
question "what is missing?" has a measured answer rather than an
intuition.

What a palette would bring and this page does not have, observed while
building it:

1. **it opens on top, from anywhere**; here you have to navigate to
   ``/recherche``, hence leave what you were looking at — the opposite of
   the gesture;
2. **it is driven from the keyboard end to end** (↑↓ across heterogeneous
   groups, Enter to open, Escape to close). ``ui.combobox`` can do that,
   but on ONE list of homogeneous options that writes a value; here each
   result leads to a different URL and nothing is selected;
3. **it has a shortcut** (Ctrl+K) — no component in the catalogue listens
   for a global combination.

None of these three gaps is made up for here: the page stays a page.
"""

from __future__ import annotations

from bretzel import Feature, page, refreshable, ui
from bretzel.state import PageState, field
from examples.crm.core.domain import (
    STAGE_COLOR,
    STAGE_LABEL,
    euros,
    initials,
    status_badge,
)
from examples.crm.features.access import ViewerPrefs, visible_owner
from examples.crm.features.search_data import PER_KIND, search_everywhere
from examples.crm.features.shell import shell


class SearchUI(PageState):
    needle: str = field(default='')


def search_changed(state: SearchUI) -> None:
    """Typing hydrates ``needle``; ``deps=`` re-renders the results."""


def result_row(icon: str, color: str, title: str, subtitle: str, href: str,
               trailing: str) -> None:
    with ui.card(padding="sm", hoverable=True, href=href):
        with ui.hstack(gap="sm", align="center"):
            ui.icon(icon, color=color, size="sm")
            with ui.vstack(gap="none", classes="min-w-0 flex-1"):
                ui.text(title, size="sm", weight="medium", truncate=True)
                ui.text(subtitle, color="muted", size="xs", truncate=True)
            ui.text(trailing, color="muted", size="xs")


def result_group(title: str, icon: str, rows: list, render) -> None:
    with ui.vstack(gap="sm"):
        with ui.hstack(gap="sm", align="center"):
            ui.icon(icon, color="muted", size="sm")
            ui.heading(title, level=2, size="sm")
            ui.badge(f"{len(rows)}" + ("+" if len(rows) == PER_KIND else ""),
                     variant="soft", color="muted", size="xs")
        if not rows:
            ui.text("Nothing here.", color="muted", size="sm")
        for row in ui.each(rows, key="id"):
            render(row)


def account_result(row: dict) -> None:
    result_row("building-2", "primary", row["name"],
               f"{row['industry']} · {row['city']}",
               f"/accounts/{row['id']}", euros(row["arr"]))


def contact_result(row: dict) -> None:
    label, _color = status_badge(row["status"])
    result_row(
        "user", "info",
        f"{row['first_name']} {row['last_name']} "
        f"({initials(row['first_name'], row['last_name'])})",
        f"{row['email']} · {row['account_name']}",
        f"/contacts/{row['id']}", label,
    )


def deal_result(row: dict) -> None:
    result_row("folder-open", STAGE_COLOR.get(row["stage"], "muted"),
               f"{row['account_name']} — {row['name']}",
               f"{STAGE_LABEL.get(row['stage'], row['stage'])} · "
               f"closing {row['close_date']}",
               f"/accounts/{row['account_id']}", euros(row["amount"]))


@refreshable(deps=[SearchUI, ViewerPrefs])
def results() -> None:
    state = SearchUI()
    needle = str(state.needle).strip()
    if len(needle) < 2:
        ui.empty_state(
            "Search an account, a contact or a deal",
            icon="search",
            description="Two characters are enough. The search is on the "
                        "START of the name — that is what an index can do "
                        "without scanning 170 000 rows at every keystroke.",
        )
        return
    found = search_everywhere(needle, visible_owner())
    total = sum(len(v) for v in found.values())
    if not total:
        ui.empty_state(f"Nothing starts with \u201c{needle}\u201d", icon="search-x",
                       description="Try the first letters of the account "
                                   "name, the last name or the email.")
        return
    with ui.grid(cols={"base": 1, "lg": 3}, gap="lg"):
        result_group("Accounts", "building-2", found["accounts"],
                     account_result)
        result_group("Contacts", "users", found["contacts"], contact_result)
        result_group("Affaires", "folder-open", found["deals"],
                     deal_result)


@page("/search", layout=shell, title="Search")
def search_page() -> None:
    state = SearchUI()
    with ui.vstack(gap="lg"):
        ui.heading("Search", level=1, size="2xl")
        # ``on_input`` and not ``on_change``: a global search reads
        # while typing. ``on_change`` is the native event — it only
        # arrives on blur or Enter, and the ``debounce`` would have
        # nothing to debounce.
        ui.input(value=state.needle, icon_left="search", clearable=True,
                 placeholder="Account, last name, email…",
                 on_input=search_changed, debounce=250)
        results()


feature = Feature(
    name="search",
    kind="page",
    provides=[search_page, SearchUI],
    uses=["search_data", "access"],
)
