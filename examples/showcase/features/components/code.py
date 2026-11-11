"""``/code`` — a block of source, highlighted on the server."""

from bretzel import ui
from examples.showcase.lib.example import example, page_header

SUMMARY = ("Syntax highlighting done in Python with Pygments — hundreds of "
           "languages, zero JavaScript, repainted by the theme.")


def python_snippet() -> None:
    ui.code('''from bretzel import refreshable, ui
from bretzel.state import PageState, field


class Cart(PageState):
    items: int = field(default=0)


def add_to_cart() -> None:
    Cart().items += 1


@refreshable
def cart_button() -> None:
    ui.button(f"Cart · {Cart().items}", on_click=add_to_cart)''',
            lang="python", classes="w-full")


def api_request() -> None:
    with ui.tabs(value="curl", size="sm", name="api-request", classes="w-full"):
        ui.tab("curl", label="cURL")
        ui.tab("python", label="Python")
        ui.tab("js", label="JavaScript")
        with ui.tab_panel(tab="curl"):
            ui.code('curl https://api.northwind.dev/v1/invoices \\\n'
                    '  -H "Authorization: Bearer $NORTHWIND_KEY" \\\n'
                    '  -d customer=cus_8f2a -d amount=428000', lang="bash")
        with ui.tab_panel(tab="python"):
            ui.code('import httpx\n\n'
                    'httpx.post("https://api.northwind.dev/v1/invoices",\n'
                    '           headers={"Authorization": f"Bearer {key}"},\n'
                    '           data={"customer": "cus_8f2a", "amount": 428000})',
                    lang="python")
        with ui.tab_panel(tab="js"):
            ui.code('await fetch("https://api.northwind.dev/v1/invoices", {\n'
                    '  method: "POST",\n'
                    '  headers: { Authorization: `Bearer ${key}` },\n'
                    '  body: new URLSearchParams({ customer: "cus_8f2a", '
                    'amount: "428000" }),\n'
                    '});', lang="javascript")


def response_and_query() -> None:
    with ui.grid(cols={"base": 1, "md": 2}, gap="md", classes="w-full"):
        with ui.vstack(gap="xs"):
            ui.text("200 OK · application/json", size="sm", color="muted")
            ui.code('{\n  "id": "inv_2041",\n  "status": "paid",\n'
                    '  "amount": 428000,\n  "currency": "eur"\n}', lang="json")
        with ui.vstack(gap="xs"):
            ui.text("migrations/0042_overdue.sql", size="sm", color="muted")
            ui.code("SELECT customer, SUM(amount) AS due\nFROM invoices\n"
                    "WHERE status = 'overdue'\nGROUP BY customer\n"
                    "ORDER BY due DESC;", lang="sql")


def config_file() -> None:
    with ui.vstack(gap="xs", classes="w-full max-w-xl"):
        ui.text("pyproject.toml", size="sm", color="muted", classes="font-mono")
        ui.code('[project]\nname = "northwind-billing"\nrequires-python = ">=3.12"\n'
                'dependencies = ["bretzel>=2.0", "httpx"]\n\n'
                '[tool.ruff]\nline-length = 100', lang="toml")


def plain_log() -> None:
    ui.code("2026-09-29 09:41:02  INFO   worker-3  invoice INV-2041 sent\n"
            "2026-09-29 09:41:05  WARN   worker-1  retrying webhook (2/5)\n"
            "2026-09-29 09:41:09  INFO   worker-1  webhook delivered in 212 ms",
            lang="text", classes="w-full")


def page() -> None:
    page_header("code", "Code", SUMMARY)
    example("A Python snippet", python_snippet, full=True,
            note="lang= names a Pygments lexer; the colours come from the theme.")
    example("One request, three languages", api_request, full=True,
            note="Tabs and code blocks: the classic API reference layout.")
    example("A response and a query", response_and_query, full=True)
    example("A config file", config_file)
    example("Plain text", plain_log, full=True,
            note="lang defaults to Python; lang=\"text\" shows the text as is, "
                 "in the monospace font.")
