"""``/table`` — rows and columns, with cells that can hold components."""

from bretzel import refreshable, ui
from bretzel.state import PageState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("Columns declared once, rows as plain dicts — and any cell can "
           "render a badge, an avatar or a button.")


def invoices() -> list[dict]:
    return [
        {"id": "INV-2041", "customer": "Northwind Traders", "issued": "Sep 24",
         "amount": "€4,280.00", "status": "paid"},
        {"id": "INV-2040", "customer": "Lumen Studio", "issued": "Sep 22",
         "amount": "€1,150.00", "status": "pending"},
        {"id": "INV-2039", "customer": "Atlas Freight", "issued": "Sep 15",
         "amount": "€9,600.00", "status": "overdue"},
        {"id": "INV-2038", "customer": "Kinfolk & Co", "issued": "Sep 12",
         "amount": "€720.00", "status": "paid"},
        {"id": "INV-2037", "customer": "Brightline Labs", "issued": "Sep 08",
         "amount": "€2,340.00", "status": "draft"},
    ]


def status_cell(value, row):
    label, color = {
        "paid": ("Paid", "success"), "pending": ("Pending", "warning"),
        "overdue": ("Overdue", "error"), "draft": ("Draft", "muted"),
    }[value]
    return ui.badge(label, color=color, variant="soft", size="sm")


def invoice_table() -> None:
    ui.table(
        columns=[
            ui.column("id", label="Invoice", width="7rem"),
            ui.column("customer", label="Customer"),
            ui.column("issued", label="Issued"),
            ui.column("status", label="Status", render=status_cell),
            ui.column("amount", label="Amount", align="right"),
        ],
        rows=invoices(),
        row_key="id",
    )


def team() -> list[dict]:
    return [
        {"name": "Lena Park", "email": "lena@northwind.io", "role": "Owner",
         "seen": "Online"},
        {"name": "Omar Haddad", "email": "omar@northwind.io", "role": "Admin",
         "seen": "2 h ago"},
        {"name": "Chloé Martin", "email": "chloe@northwind.io", "role": "Editor",
         "seen": "Yesterday"},
        {"name": "Tomás Silva", "email": "tomas@northwind.io", "role": "Viewer",
         "seen": "Last week"},
    ]


def member_cell(value, row):
    with ui.hstack(gap="sm") as cell:
        ui.avatar(src=f"https://i.pravatar.cc/96?u={row['email']}", name=value,
                  size="sm")
        with ui.vstack(gap="none"):
            ui.text(value, weight="medium")
            ui.text(row["email"], size="sm", color="muted")
    return cell


def role_cell(value, row):
    color = {"Owner": "primary", "Admin": "info"}.get(value, "muted")
    return ui.badge(value, color=color, variant="outline", size="sm")


def actions_cell(value, row):
    return ui.icon_button("more-horizontal", variant="ghost", size="xs",
                          aria_label=f"Actions for {row['name']}")


def team_table() -> None:
    ui.table(
        columns=[
            ui.column("name", label="Member", render=member_cell),
            ui.column("role", label="Role", render=role_cell),
            ui.column("seen", label="Last seen"),
            ui.column("", label="", align="right", render=actions_cell),
        ],
        rows=team(),
        row_key="email",
        size="lg",
    )


class Opened(PageState):
    invoice: str = field(default="INV-2039")


def open_invoice(invoice_id: str) -> None:
    Opened().invoice = invoice_id


@refreshable
def invoice_detail() -> None:
    row = next(r for r in invoices() if r["id"] == Opened().invoice)
    with ui.card(padding="md"), ui.hstack(gap="md", justify="between", wrap=True):
        with ui.vstack(gap="none"):
            ui.text(f"{row['id']} · {row['customer']}", weight="semibold")
            ui.text(f"Issued {row['issued']} — {row['amount']}", size="sm",
                    color="muted")
        with ui.hstack(gap="sm"):
            ui.button("Download PDF", icon_left="download", variant="outline",
                      size="sm")
            ui.button("Send reminder", icon_left="send", size="sm")


def clickable() -> None:
    ui.table(
        columns=[
            ui.column("id", label="Invoice", width="7rem"),
            ui.column("customer", label="Customer"),
            ui.column("status", label="Status", render=status_cell),
            ui.column("amount", label="Amount", align="right"),
        ],
        rows=invoices(),
        row_key="id",
        on_item_click=open_invoice,
        size="sm",
        color="primary",
    )
    invoice_detail()


def empty() -> None:
    ui.table(
        columns=[
            ui.column("id", label="Invoice"),
            ui.column("customer", label="Customer"),
            ui.column("amount", label="Amount", align="right"),
        ],
        rows=[],
        empty_text="No invoice this month",
        empty_icon="receipt",
        empty_description="Invoices you issue in October will show up here.",
    )


def page() -> None:
    page_header("table", "Table", SUMMARY)
    example("Invoices", invoice_table, uses=[invoices, status_cell], full=True,
            note="ui.column names the key, the label and the alignment; "
                 "render= turns a raw status into a badge.")
    example("Team members", team_table,
            uses=[team, member_cell, role_cell, actions_cell], full=True,
            note="A cell can hold a whole layout. size=\"lg\" gives the rows "
                 "room for an avatar and two lines.")
    example("Click a row to open it", clickable,
            uses=[Opened, open_invoice, invoice_detail], full=True,
            note="on_item_click receives the row's key on the server; the "
                 "detail below re-renders. Rows are keyboard operable too.")
    example("When there is nothing to show", empty, full=True,
            note="An empty table shows an empty state, not a lonely header.")
