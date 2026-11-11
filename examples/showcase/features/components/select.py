"""``/select`` — pick from a list you can read at a glance."""

from bretzel import ui
from bretzel.state import ClientState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("A styled dropdown for short lists: one value or several, custom "
           "option bodies, and a value the rest of the page can follow.")

COUNTRIES = [("fr", "France"), ("de", "Germany"), ("es", "Spain"),
             ("it", "Italy"), ("nl", "Netherlands"), ("gb", "United Kingdom"),
             ("us", "United States")]


def pick_one() -> None:
    with ui.grid(cols={"base": 1, "sm": 2}, gap="md", classes="w-full max-w-xl"):
        with ui.form_field(label="Country"):
            ui.select(COUNTRIES, placeholder="Select a country")
        with ui.form_field(label="Currency"):
            ui.select(["EUR", "GBP", "USD", "CHF"], value="EUR")


PLANS = [
    {"value": "starter", "label": "Starter — €0"},
    {"value": "team", "label": "Team — €12 / seat"},
    {"value": "business", "label": "Business — €24 / seat"},
    {"value": "enterprise", "label": "Enterprise — talk to sales",
     "disabled": True},
]


def plans() -> None:
    with ui.form_field(label="Plan", hint="Enterprise is set up with our team.",
                       classes="max-w-xs"):
        ui.select(PLANS, value="team")


CHANNELS = [("email", "Email"), ("slack", "Slack"), ("sms", "SMS"),
            ("push", "Push notification"), ("webhook", "Webhook")]


def several() -> None:
    with ui.form_field(label="Alert me by", classes="max-w-sm"):
        ui.select(CHANNELS, multiple=True, bulk_actions=True,
                  value=["email", "slack"], placeholder="Pick channels")


PRIORITY = {"urgent": "error", "high": "warning", "normal": "info", "low": "secondary"}


def priority_option(value, label):
    return ui.badge(label, color=PRIORITY[value], variant="soft", size="sm")


def custom_options() -> None:
    with ui.form_field(label="Priority", classes="max-w-xs"):
        ui.select([("urgent", "Urgent"), ("high", "High"),
                   ("normal", "Normal"), ("low", "Low")],
                  value="normal", render=priority_option)


INVOICES = [
    ("INV-2041", "Northwind Traders", "€4,280.00", "paid"),
    ("INV-2040", "Lumen Studio", "€1,150.00", "pending"),
    ("INV-2039", "Atlas Freight", "€9,600.00", "overdue"),
    ("INV-2038", "Kinfolk & Co", "€720.00", "paid"),
    ("INV-2037", "Harbor Health", "€2,310.00", "pending"),
]

STATUS_COLOR = {"paid": "success", "pending": "warning", "overdue": "error"}


class InvoiceFilter(ClientState):
    status: str = field(default="all")


def live_filter() -> None:
    status = InvoiceFilter().status
    with ui.card(padding="md", classes="w-full max-w-xl"), ui.vstack(gap="md"):
        with ui.hstack(justify="between"):
            ui.heading("Invoices", level=3, size="md")
            ui.select([("all", "All statuses"), ("paid", "Paid"),
                       ("pending", "Pending"), ("overdue", "Overdue")],
                      value=status, size="sm", classes="w-48")
        with ui.vstack(gap="sm"):
            for number, customer, amount, state in INVOICES:
                shown = (status == "all") | (status == state)
                with ui.hstack(gap="md", justify="between", visible=shown):
                    with ui.hstack(gap="sm"):
                        ui.text(number, color="muted", size="sm",
                                classes="font-mono")
                        ui.text(customer, weight="medium")
                    with ui.hstack(gap="sm"):
                        ui.text(amount)
                        ui.badge(state.capitalize(), color=STATUS_COLOR[state],
                                 variant="soft", size="sm")


def sizes_and_states() -> None:
    with ui.vstack(gap="sm", classes="w-full max-w-xs"):
        for size in ("xs", "sm", "md", "lg", "xl"):
            ui.select(["Daily", "Weekly", "Monthly"], size=size,
                      placeholder=f"Report frequency ({size})")
        ui.select(["Daily", "Weekly", "Monthly"], value="Weekly", disabled=True)


def page() -> None:
    page_header("select", "Select", SUMMARY)
    example("Pick one", pick_one,
            note="Options are plain strings, or (value, label) pairs when "
                 "what you store is not what you show.")
    example("A disabled option", plans,
            note="An option as a dict can carry disabled=True: it stays "
                 "visible, but cannot be picked.")
    example("Several values", several,
            note="multiple=True shows the picks as pills; bulk_actions adds "
                 "Select all and Clear to the panel.")
    example("Custom option bodies", custom_options,
            note="render= draws the inside of each option — here a coloured "
                 "badge per priority.")
    example("Filter a list", live_filter,
            uses=[InvoiceFilter],
            note="The select writes a ClientState and each row shows or hides "
                 "itself in the browser. Give on_change a Python function to "
                 "filter on the server instead.")
    example("Sizes and disabled", sizes_and_states)
