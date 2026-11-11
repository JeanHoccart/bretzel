"""``/badge`` — a status, a count, a tag."""

from bretzel import ui
from bretzel.state import ClientState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("Status pills, counters and removable filter chips — three "
           "variants, every colour, five sizes.")


def variants() -> None:
    with ui.hstack(gap="sm", wrap=True, justify="center"):
        ui.badge("Solid", variant="solid", size="lg")
        ui.badge("Soft", variant="soft", size="lg")
        ui.badge("Outline", variant="outline", size="lg")


def colors() -> None:
    with ui.vstack(gap="sm", align="center"):
        for variant in ("solid", "soft", "outline"):
            with ui.hstack(gap="sm", wrap=True, justify="center"):
                for color in ("primary", "secondary", "success", "warning",
                              "error", "info", "muted"):
                    ui.badge(color.capitalize(), color=color, variant=variant)


def sizes() -> None:
    with ui.hstack(gap="sm", wrap=True, justify="center", align="center"):
        for size in ("xs", "sm", "md", "lg", "xl"):
            ui.badge(f"Size {size}", size=size, variant="soft")


def in_a_list() -> None:
    invoices = [
        ("INV-2041", "Northwind Traders", "Paid", "success", "check"),
        ("INV-2040", "Lumen Studio", "Pending", "warning", "clock"),
        ("INV-2039", "Atlas Freight", "Overdue", "error", "circle-alert"),
        ("INV-2038", "Kinfolk & Co", "Draft", "muted", "pencil"),
    ]
    with ui.card(padding="md", classes="w-full max-w-lg"), ui.vstack(gap="sm"):
        for number, customer, status, color, icon in invoices:
            with ui.hstack(gap="md", justify="between"):
                with ui.vstack(gap="none"):
                    ui.text(customer, weight="medium")
                    ui.text(number, color="muted", size="sm")
                ui.badge(status, color=color, variant="soft", size="sm",
                         icon_left=icon)


def counters() -> None:
    with ui.hstack(gap="lg", wrap=True, justify="center"):
        with ui.hstack(gap="xs"):
            ui.text("Inbox", weight="medium")
            ui.badge("12", color="primary", size="xs")
        with ui.hstack(gap="xs"):
            ui.text("Mentions", weight="medium")
            ui.badge("3", color="error", size="xs")
        with ui.hstack(gap="xs"):
            ui.text("Plan", weight="medium")
            ui.badge("Pro", color="secondary", variant="outline", size="xs",
                     icon_left="sparkles")
        with ui.hstack(gap="xs"):
            ui.text("API", weight="medium")
            ui.badge("Beta", color="info", variant="soft", size="xs",
                     icon_right="flask-conical")


FILTERS = ["Status: Open", "Owner: Ada", "Label: Billing", "Due this week"]


class FilterChips(ClientState):
    removed: int = field(default=0)


def filter_bar() -> None:
    chips = FilterChips()
    with ui.hstack(gap="sm", wrap=True, justify="center"):
        for label in FILTERS:
            ui.badge(label, variant="soft", color="primary", dismissible=True,
                     on_close=chips.removed.increment())
        ui.text("No filters — showing all 248 tickets.", color="muted",
                size="sm", visible=chips.removed == len(FILTERS))


def page() -> None:
    page_header("badge", "Badge", SUMMARY)
    example("Variants", variants)
    example("Colours", colors,
            note="Every semantic colour of the theme, in each variant.")
    example("Sizes", sizes)
    example("Status in a list", in_a_list,
            note="Soft badges with an icon read at a glance without shouting "
                 "over the row.")
    example("Counters and tags", counters)
    example("Removable filters", filter_bar,
            uses=[FilterChips],
            note="dismissible adds the × and closes the chip in the browser; "
                 "on_close counts what is left, without a round trip.")
