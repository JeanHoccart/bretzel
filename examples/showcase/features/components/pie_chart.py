"""``/pie-chart`` — parts of a whole, as a pie or a donut."""

from bretzel import refreshable, ui
from bretzel.state import PageState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("Parts of a whole as a pie or a donut, with a figure in the "
           "middle, labels on the slices and a click that runs Python.")


def traffic_sources() -> list[tuple[str, float]]:
    return [("Organic search", 19840), ("Direct", 12310), ("Referral", 7420),
            ("Social", 5260), ("Email", 3370)]


def donut() -> None:
    with ui.card(padding="md", classes="w-full max-w-md"), ui.vstack(gap="sm"):
        with ui.hstack(justify="between", align="center"):
            ui.text("Traffic sources · September", size="sm", color="muted")
            ui.badge("+9.1%", color="success", variant="soft", size="sm")
        ui.pie_chart(data=traffic_sources(), variant="donut",
                     center_text="48.2k visits", value_unit="visits")


def storage() -> None:
    with ui.card(padding="md", classes="w-full max-w-md"), ui.vstack(gap="sm"):
        with ui.vstack(gap="none"):
            ui.text("Storage used", size="sm", color="muted")
            ui.heading("182 GB of 250 GB", level=3, size="xl")
        ui.pie_chart(data=[("Videos", 94), ("Design files", 41),
                           ("Documents", 29), ("Backups", 18)],
                     show_labels=True, value_unit="GB", show_data=True,
                     colors=["primary", "secondary", "info", "muted"])


def devices(web: int, ios: int, android: int) -> list[tuple[str, float]]:
    return [("Web", web), ("iOS", ios), ("Android", android)]


def small_multiples() -> None:
    with ui.grid(min_col="12rem", gap="md"):
        for region, split in (("North America", devices(58, 30, 12)),
                              ("Europe", devices(47, 22, 31)),
                              ("Asia-Pacific", devices(29, 24, 47))):
            with ui.card(padding="md"), ui.vstack(gap="xs", align="center"):
                ui.text(region, size="sm", weight="medium")
                ui.pie_chart(data=split, variant="donut", size="sm",
                             value_unit="%", show_legend=False)
                ui.text("Web · iOS · Android", size="xs", color="muted")


def open_tickets(category: str) -> list[str]:
    return {
        "Billing": ["Refund for a duplicate charge", "VAT number missing on invoice",
                    "Switch to annual billing"],
        "Bugs": ["Export to CSV times out", "Calendar sync skips recurring events",
                 "Dark mode: unreadable tooltip"],
        "How-to": ["Invite a guest to one board", "Set up SSO with Okta",
                   "Restore a deleted workspace"],
        "Feature requests": ["Gantt view", "Custom fields on tasks",
                             "Slack thread replies"],
    }[category]


class Breakdown(PageState):
    category: str = field(default="Bugs")


def pick_category(label: str, value: float) -> None:
    Breakdown().category = label


@refreshable
def category_tickets() -> None:
    category = Breakdown().category
    with ui.vstack(gap="sm"):
        ui.heading(category, level=3, size="md")
        for subject in open_tickets(category):
            with ui.hstack(gap="sm", align="center"):
                ui.icon("message-square", size="sm", color="muted")
                ui.text(subject, size="sm")


def drilldown() -> None:
    with ui.card(padding="md"), ui.grid(cols={"base": 1, "md": 2}, gap="lg"):
        with ui.vstack(gap="sm"):
            ui.text("Open tickets · click a slice", size="sm", color="muted")
            ui.pie_chart(data=[("Billing", 34), ("Bugs", 58), ("How-to", 41),
                               ("Feature requests", 23)],
                         variant="donut", center_text="156 open",
                         on_item_click=pick_category)
        category_tickets()


def page() -> None:
    page_header("pie_chart", "Pie chart", SUMMARY)
    example("A donut with its total", donut, uses=[traffic_sources],
            note="The donut leaves room in the middle for the figure the "
                 "reader looks for first.")
    example("Labels on the slices", storage,
            note="show_labels writes each share on its slice; colors picks "
                 "the theme colours, in order; show_data folds the figures "
                 "and their shares under the pie.")
    example("Small multiples", small_multiples, uses=[devices], full=True,
            note="Three small donuts compare better than one crowded pie.")
    example("A click that runs Python", drilldown,
            uses=[open_tickets, Breakdown, pick_category, category_tickets], full=True,
            note="on_item_click receives the slice's label and value; the "
                 "list next to it is rendered again on the server.")
