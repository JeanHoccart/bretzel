"""``/datatable`` — a table that sorts, filters, searches, pages and exports."""

from bretzel import refreshable, ui
from bretzel.components import DatatableState, Query, apply_query
from bretzel.state import PageState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("Search, sort, filter by column, page through and export to CSV "
           "— the whole query runs in Python.")


def customers() -> list[dict]:
    names = ["Ada Lovelace", "Omar Haddad", "Chloé Martin", "Tomás Silva",
             "Lena Park", "Yusuf Demir", "Ingrid Berg", "Kenji Sato",
             "Priya Nair", "Lucas Moreau", "Sofia Rossi", "Noah Fischer"]
    companies = ["Northwind", "Lumen Studio", "Atlas Freight", "Kinfolk",
                 "Brightline", "Harbor & Co", "Juniper Labs"]
    countries = ["France", "Germany", "Spain", "Italy", "Sweden"]
    plans = {"Starter": 29, "Team": 290, "Scale": 990}
    statuses = ["Active", "Active", "Trial", "Active", "Past due", "Churned"]
    rows = []
    for i in range(48):
        seed = (i * 7919 + 13) % 1009  # a stable shuffle, same on every render
        plan = list(plans)[seed % 3]
        rows.append({
            "id": 1040 + i,
            "name": names[i % len(names)],
            "company": companies[(seed // 3) % len(companies)],
            "country": countries[(seed // 7) % len(countries)],
            "plan": plan,
            "mrr": plans[plan] * (1 + seed % 4),
            "status": statuses[(i + seed // 11) % len(statuses)],
            "since": f"2026-{1 + seed % 9:02d}-{1 + (seed // 9) % 28:02d}",
        })
    return rows


def customer_cell(value, row):
    with ui.hstack(gap="sm") as cell:
        ui.avatar(name=value, size="xs", color="secondary")
        with ui.vstack(gap="none"):
            ui.text(value, weight="medium")
            ui.text(row["company"], size="xs", color="muted")
    return cell


def status_cell(value, row):
    color = {"Active": "success", "Trial": "info", "Past due": "warning",
             "Churned": "muted"}[value]
    return ui.badge(value, color=color, variant="soft", size="sm")


def mrr_cell(value, row):
    return ui.text(f"€{value:,}", weight="medium")


def customer_columns() -> list:
    return [
        ui.column("name", label="Customer", sortable=True, render=customer_cell),
        ui.column("country", label="Country", sortable=True,
                  filter=["France", "Germany", "Spain", "Italy", "Sweden"]),
        ui.column("plan", label="Plan", filter=["Starter", "Team", "Scale"]),
        ui.column("status", label="Status", render=status_cell,
                  filter=["Active", "Trial", "Past due", "Churned"]),
        ui.column("since", label="Customer since", sortable=True),
        ui.column("mrr", label="MRR", align="right", sortable=True,
                  render=mrr_cell),
    ]


def load_customers(query: Query) -> tuple[list, int]:
    # A real app turns the query into SQL; the demo filters a list.
    return apply_query(customers(), customer_columns(), query)


class Customers(DatatableState):
    per_page: int = field(default=8)
    sort_key: str = field(default="mrr")
    sort_dir: str = field(default="desc")


@refreshable
def customer_list() -> None:
    ui.datatable(
        state=Customers,
        columns=customer_columns(),
        rows=load_customers,
        search_placeholder="Search customers…",
        exportable=True,
        export_filename="customers.csv",
        empty_text="No customer matches",
        empty_icon="search",
        empty_description="Try another name, or clear a filter.",
    )


def full() -> None:
    customer_list()


def payments() -> list[dict]:
    methods = ["Visa ···· 4242", "SEPA debit", "Mastercard ···· 8210",
               "Bank transfer"]
    return [
        {"id": f"PAY-{7310 - i}", "date": f"Sep {29 - i % 28:02d}",
         "method": methods[i % 4], "amount": 29 + (i * 37) % 900}
        for i in range(30)
    ]


def amount_cell(value, row):
    return ui.text(f"€{value:,}.00")


class Payments(DatatableState):
    per_page: int = field(default=30)


@refreshable
def payment_log() -> None:
    ui.datatable(
        state=Payments,
        columns=[
            ui.column("id", label="Payment", sortable=True),
            ui.column("date", label="Date", sortable=True),
            ui.column("method", label="Method"),
            ui.column("amount", label="Amount", align="right", sortable=True,
                      render=amount_cell),
        ],
        rows=payments(),
        search=False,
        size="sm",
        max_height="18rem",
    )


def compact() -> None:
    payment_log()


class Team(DatatableState):
    per_page: int = field(default=5)


class Selected(PageState):
    customer: int = field(default=1041)


def select_customer(customer_id: int) -> None:
    Selected().customer = customer_id


@refreshable
def picker_table() -> None:
    ui.datatable(
        state=Team,
        columns=[
            ui.column("name", label="Customer", sortable=True),
            ui.column("company", label="Company", sortable=True),
            ui.column("plan", label="Plan"),
        ],
        rows=customers(),
        row_key="id",
        on_item_click=select_customer,
        search_placeholder="Find a customer…",
        color="secondary",
    )


@refreshable
def selected_customer() -> None:
    row = next(r for r in customers() if r["id"] == Selected().customer)
    with ui.card(padding="md"), ui.hstack(gap="md", justify="between", wrap=True):
        with ui.hstack(gap="sm"):
            ui.avatar(name=row["name"], color="secondary")
            with ui.vstack(gap="none"):
                ui.text(row["name"], weight="semibold")
                ui.text(f"{row['company']} · {row['country']} · since "
                        f"{row['since']}", size="sm", color="muted")
        status_cell(row["status"], row)


def picker() -> None:
    picker_table()
    selected_customer()


def page() -> None:
    page_header("datatable", "Data table", SUMMARY)
    example("A customer list", full,
            uses=[customers, customer_cell, status_cell, mrr_cell,
                  customer_columns, load_customers, Customers, customer_list],
            full=True,
            note="Click a header to sort, use a column's filter, type to "
                 "search, export every matching row. rows= takes a function "
                 "of the query, so the same code can run it as SQL.")
    example("A compact, scrolling log", compact,
            uses=[payments, amount_cell, Payments, payment_log], full=True,
            note="size=\"sm\" and max_height= give a dense list with a "
                 "sticky header; search=False drops the toolbar.")
    example("Pick a row", picker,
            uses=[customers, status_cell, Team, Selected, select_customer, picker_table,
                  selected_customer],
            full=True,
            note="on_item_click sends the row's key to Python; the card "
                 "below follows the selection.")
