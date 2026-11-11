"""``/pagination`` — moving through a long list, one page at a time."""

from bretzel import refreshable, ui
from bretzel.state import PageState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("Previous, next and the pages in between — ellipses on long "
           "ranges, and a change that can re-query the server.")


def invoices() -> list[dict]:
    customers = ("Northwind Traders", "Lumen Studio", "Atlas Freight",
                 "Kinfolk & Co", "Harbor Labs", "Oakline", "Brightside Dental")
    return [
        {"number": f"INV-{2060 - i}",
         "customer": customers[i % len(customers)],
         "amount": f"€{(i * 373) % 4900 + 180:,}.00"}
        for i in range(42)
    ]


class Ledger(PageState):
    page: int = field(default=1)


def turn_page(page: int) -> None:
    Ledger().page = page


@refreshable
def ledger() -> None:
    page = int(Ledger().page)
    rows = invoices()[(page - 1) * 6:page * 6]
    with ui.vstack(gap="md", align="center", classes="w-full"):
        ui.table(columns=[ui.column("number", label="Invoice"),
                          ui.column("customer", label="Customer"),
                          ui.column("amount", label="Amount", align="right")],
                 rows=rows, size="sm", classes="w-full")
        ui.pagination(value=Ledger().page, total_pages=7, on_change=turn_page)


def paged_table() -> None:
    ledger()


def long_range() -> None:
    with ui.vstack(gap="md", align="center"):
        ui.pagination(value=1, total_pages=48, name="start")
        ui.pagination(value=24, total_pages=48, name="middle")
        ui.pagination(value=24, total_pages=48, max_visible=9, name="wide")


def sizes() -> None:
    with ui.vstack(gap="md", align="center"):
        for size in ("xs", "sm", "md", "lg"):
            ui.pagination(value=3, total_pages=8, size=size, name=f"size-{size}")


def colors() -> None:
    with ui.vstack(gap="md", align="center"):
        for color in ("primary", "secondary", "success", "warning"):
            ui.pagination(value=2, total_pages=5, color=color,
                          name=f"color-{color}")
        ui.pagination(value=2, total_pages=5, disabled=True, name="disabled")


def remote_control() -> None:
    with ui.vstack(gap="md", align="center"):
        photos = ui.pagination(value=1, total_pages=12, name="photos")
        with ui.hstack(gap="sm"):
            ui.button("First", variant="ghost", size="sm", on_click=photos.set(1))
            ui.button("Previous", variant="outline", size="sm",
                      icon_left="arrow-left", on_click=photos.prev())
            ui.button("Next", size="sm", icon_right="arrow-right",
                      on_click=photos.next())
            ui.button("Last", variant="ghost", size="sm", on_click=photos.set(12))


def page() -> None:
    page_header("pagination", "Pagination", SUMMARY)
    example("Under a table", paged_table, full=True,
            uses=[invoices, Ledger, turn_page, ledger],
            note="Bound to a server state: on_change receives the page, the "
                 "table re-renders with the next six rows.")
    example("Long ranges", long_range,
            note="Past max_visible pages, the ends and the neighbourhood of "
                 "the current page stay; the rest folds into an ellipsis.")
    example("Sizes", sizes)
    example("Colours and disabled", colors)
    example("Driven from other buttons", remote_control,
            note=".set(), .prev() and .next() return client actions: the "
                 "pager moves without a round trip, and stays in bounds.")
