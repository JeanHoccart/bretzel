"""features/account_detail — screen 5: an account's sheet.

What this screen puts under constraint: **sub-tables** and **container
nesting**. An account sheet is not a flat page — it is a header, then two
`ui.table` inside two `ui.card` inside a `ui.grid`, each with its own
density and its own emptiness.

It is the repository's first screen to put a table INSIDE a card INSIDE a
grid: the 17 apps mount their tables at the page's first level.
"""

from __future__ import annotations

from bretzel import Feature, abort, page, ui
from examples.crm.core.domain import (
    STAGE_COLOR,
    STAGE_LABEL,
    euros,
    initials,
    status_badge,
)
from examples.crm.core.ui import kpi
from examples.crm.features.access import visible_owner
from examples.crm.features.accounts_data import account_totals, get_account
from examples.crm.features.contacts_data import account_contacts
from examples.crm.features.deals_data import account_deals
from examples.crm.features.shell import shell


def contact_avatar_cell(_value, row):
    return ui.avatar(
        initials=initials(row["first_name"], row["last_name"]),
        size="xs", color="muted",
    )


def contact_status_cell(value, _row):
    label, color = status_badge(value)
    return ui.badge(label, color=color, variant="soft", size="xs")


def contact_link_cell(_value, row):
    return ui.link(f"{row['first_name']} {row['last_name']}",
                   href=f"/contacts/{row['id']}", variant="underline")


CONTACT_COLUMNS = [
    ui.column("avatar", label="", width="3rem", render=contact_avatar_cell),
    ui.column("last_name", label="Contact", render=contact_link_cell),
    ui.column("title", label="Job title"),
    ui.column("status", label="Status", render=contact_status_cell),
]


def deal_stage_cell(value, _row):
    return ui.badge(STAGE_LABEL.get(value, value),
                    color=STAGE_COLOR.get(value, "muted"), variant="soft",
                    size="xs")


def deal_amount_cell(value, _row):
    return ui.text(euros(value), weight="medium")


DEAL_COLUMNS = [
    ui.column("name", label="Deal"),
    ui.column("stage", label="Stage", render=deal_stage_cell),
    ui.column("amount", label="Amount", align="right",
              render=deal_amount_cell),
    ui.column("close_date", label="Close date"),
]


def totals_row(account: dict, totals: dict) -> None:
    with ui.grid(cols={"base": 2, "md": 4}, gap="md"):
        kpi("ARR", euros(account["arr"]), "banknote", "primary")
        kpi("Contacts", str(totals["contacts"]), "users", "info")
        kpi("Open pipeline", euros(totals["open"]), "trending-up",
            "warning")
        kpi("Won", euros(totals["won"]), "circle-check", "success")


def sub_table(title: str, total: int, columns, rows, empty: str,
              empty_icon: str) -> None:
    """A sub-table: card + header + ``ui.table``, rendered twice.

    ``total`` is the REAL count, not ``len(rows)``: both reads are capped
    at 25 rows, so beyond that the badge would say "25" beside a KPI card
    telling the truth, forty pixels away.
    """
    with ui.card(padding="md"):
        with ui.vstack(gap="sm"):
            with ui.hstack(justify="between", align="center"):
                ui.heading(title, level=2, size="md")
                ui.badge(str(total), variant="soft", color="muted", size="xs")
            ui.table(columns=columns, rows=rows, row_key="id", size="sm",
                     empty_text=empty, empty_icon=empty_icon)


@page("/accounts/{account_id}", layout=shell, title="Account sheet")
def account_sheet_page(account_id: int) -> None:
    # Outside the portfolio → 404, not 403: saying "forbidden" would
    # confirm the account exists. The scoping is in ``get_account``, so
    # both cases arrive here indistinguishable — that is intended.
    account = get_account(int(account_id), visible_owner())
    if account is None:
        abort(404)
    totals = account_totals(account["id"])
    contacts = account_contacts(account["id"])
    deals = account_deals(account["id"])

    with ui.vstack(gap="lg"):
        with ui.breadcrumb():
            ui.breadcrumb_item(label="Accounts", href="/accounts",
                               icon="building-2")
            ui.breadcrumb_item(label=account["name"])

        with ui.hstack(gap="md", align="center", wrap=True):
            with ui.vstack(gap="none", classes="min-w-0 flex-1"):
                ui.heading(account["name"], level=1, size="xl")
                ui.text(f"{account['industry']} · {account['city']}, "
                        f"{account['country']} · {account['owner']}",
                        color="muted", size="sm", truncate=True)
            ui.badge(account["size"], variant="soft", color="primary")

        totals_row(account, totals)

        # Two sub-tables side by side: it is the nesting the screen puts
        # under constraint — table in card in grid.
        with ui.grid(cols={"base": 1, "xl": 2}, gap="lg"):
            sub_table("Contacts", totals["contacts"], CONTACT_COLUMNS,
                      contacts, "No contact attached", "user-x")
            sub_table("Affaires", totals["deals"], DEAL_COLUMNS, deals,
                      "Aucune affaire", "folder-open")


feature = Feature(
    name="account_detail",
    kind="page",
    provides=[account_sheet_page],
    uses=["access", "accounts_data", "contacts_data", "deals_data"],
)
