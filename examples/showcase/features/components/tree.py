"""``/tree`` — a hierarchy you can fold, and pick from."""

from bretzel import ui
from bretzel.state import ClientState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("Nested nodes that fold and unfold, with icons, a selected row "
           "and a value the rest of the page can follow.")


def project_files() -> None:
    with ui.tree(value="invoices.py", expanded=["app", "features"],
                 classes="w-full max-w-xs"):
        with ui.tree_node("app", label="app", icon="folder"):
            with ui.tree_node("features", label="features", icon="folder"):
                ui.tree_node("invoices.py", label="invoices.py",
                             icon="file-code")
                ui.tree_node("customers.py", label="customers.py",
                             icon="file-code")
                ui.tree_node("reports.py", label="reports.py", icon="file-code")
            with ui.tree_node("static", label="static", icon="folder"):
                ui.tree_node("logo.svg", label="logo.svg", icon="image")
            ui.tree_node("main.py", label="main.py", icon="file-code")
        ui.tree_node("pyproject.toml", label="pyproject.toml", icon="settings")
        ui.tree_node(".env", label=".env (hidden)", icon="lock", disabled=True)


DOC_TITLES = {
    "start": "Getting started", "invite": "Invite your team",
    "import": "Import customers", "create": "Create an invoice",
    "recurring": "Recurring invoices", "refunds": "Refunds and credit notes",
    "api": "API keys", "webhooks": "Webhooks",
}


class Docs(ClientState):
    page: str = field(default="refunds")


def help_centre() -> None:
    page = Docs().page
    with ui.flex(direction={"base": "col", "md": "row"}, gap="md",
                 align="start", classes="w-full"):
        with ui.tree(value=page, expanded=["basics", "billing"],
                     classes="md:w-60 shrink-0"):
            with ui.tree_node("basics", label="Basics", icon="book-open"):
                ui.tree_node("start", label="Getting started")
                ui.tree_node("invite", label="Invite your team")
                ui.tree_node("import", label="Import customers")
            with ui.tree_node("billing", label="Billing", icon="receipt"):
                ui.tree_node("create", label="Create an invoice")
                ui.tree_node("recurring", label="Recurring invoices")
                ui.tree_node("refunds", label="Refunds")
            with ui.tree_node("developers", label="Developers", icon="code"):
                ui.tree_node("api", label="API keys")
                ui.tree_node("webhooks", label="Webhooks")
        with ui.card(padding="md", classes="flex-1"), ui.vstack(gap="sm"):
            ui.text("Help centre", size="xs", color="muted", weight="medium")
            for key, title in DOC_TITLES.items():
                ui.heading(title, level=3, size="lg", visible=page == key)
            ui.text("The article follows the node you pick in the tree, "
                    "without a request to the server.", color="muted", size="sm")


def org_chart() -> None:
    with (ui.tree(selectable=False, size="sm",
                  expanded=["ceo", "product", "sales"], classes="w-full max-w-xs"),
          ui.tree_node("ceo", label="Lena Park — CEO", icon="user")):
        with ui.tree_node("product", label="Product", icon="users"):
            ui.tree_node("omar", label="Omar Haddad — Design lead")
            ui.tree_node("chloe", label="Chloé Martin — Engineering")
        with ui.tree_node("sales", label="Sales", icon="users"):
            ui.tree_node("tomas", label="Tomás Silva — Account executive")
            ui.tree_node("priya", label="Priya Nair — Customer success")
        with ui.tree_node("ops", label="Operations", icon="users"):
            ui.tree_node("ingrid", label="Ingrid Berg — Finance")


def colors_and_sizes() -> None:
    with ui.grid(cols=2, gap="xl", classes="w-full max-w-lg"):
        with (ui.tree(value="inbox", color="secondary", size="sm",
                      expanded=["mail"]),
              ui.tree_node("mail", label="Mail", icon="mail")):
            ui.tree_node("inbox", label="Inbox", icon="inbox")
            ui.tree_node("sent", label="Sent", icon="send")
            ui.tree_node("spam", label="Spam", icon="shield-alert")
        with (ui.tree(value="q3", color="success", size="lg",
                      expanded=["reports"]),
              ui.tree_node("reports", label="Reports", icon="folder")):
            ui.tree_node("q2", label="Q2 2026", icon="file-text")
            ui.tree_node("q3", label="Q3 2026", icon="file-text")


def page() -> None:
    page_header("tree", "Tree", SUMMARY)
    example("A project's files", project_files,
            note="expanded= opens branches up front, value= marks the "
                 "selected node, disabled= greys one out.")
    example("Browse a help centre", help_centre,
            uses=[Docs], full=True,
            note="Bind value= to a ClientState field and the article follows "
                 "the picked node in the browser. Add on_change when Python "
                 "must load the article.")
    example("A read-only hierarchy", org_chart,
            note="selectable=False keeps folding but drops the selection — "
                 "an org chart, a table of contents.")
    example("Colours and sizes", colors_and_sizes)
