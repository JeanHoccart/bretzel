"""``/toggle-group`` — a row of joined buttons: pick one, or several."""

from bretzel import ui
from bretzel.state import ClientState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("Joined buttons for a view switch, a toolbar or a filter — one "
           "pick or several, with icons, labels and tooltips.")


def view_switch() -> None:
    with ui.toggle_group(value="board"):
        ui.toggle_button("board", label="Board", icon="columns-3")
        ui.toggle_button("list", label="List", icon="list")
        ui.toggle_button("timeline", label="Timeline", icon="gantt-chart")


def toolbar() -> None:
    with ui.card(padding="sm"), ui.hstack(gap="sm", wrap=True):
        with ui.toggle_group(value=["bold"], multiple=True, size="sm"):
            ui.toggle_button("bold", icon="bold", tooltip="Bold")
            ui.toggle_button("italic", icon="italic", tooltip="Italic")
            ui.toggle_button("underline", icon="underline", tooltip="Underline")
            ui.toggle_button("strike", icon="strikethrough", tooltip="Strikethrough")
        ui.divider(orientation="vertical", classes="self-stretch")
        with ui.toggle_group(value="left", size="sm"):
            ui.toggle_button("left", icon="align-left", tooltip="Align left")
            ui.toggle_button("center", icon="align-center", tooltip="Centre")
            ui.toggle_button("right", icon="align-right", tooltip="Align right")
        ui.divider(orientation="vertical", classes="self-stretch")
        with ui.toggle_group(value="p", size="sm"):
            ui.toggle_button("p", label="Text")
            ui.toggle_button("h2", label="Heading")
            ui.toggle_button("code", label="Code", disabled=True,
                             tooltip="Available on the Pro plan")


def billing_period() -> None:
    with ui.vstack(gap="sm", align="center"):
        ui.toggle_group(value="yearly", size="lg", color="success",
                        options=[("monthly", "Monthly"),
                                 ("yearly", "Yearly · save 20%")])
        ui.text("Billed €192 once a year instead of €20 a month.",
                color="muted", size="sm")


def sizes() -> None:
    with ui.vstack(gap="md", align="center"):
        for size in ("xs", "sm", "md", "lg", "xl"):
            ui.toggle_group(value="week", size=size, name=f"range-{size}",
                            options=[("day", "Day"), ("week", "Week"),
                                     ("month", "Month")])


TICKETS = [
    ("Invoice PDF shows the wrong VAT number", "open", "Billing"),
    ("SSO login loops on Safari 18", "open", "Auth"),
    ("Export to CSV drops accented names", "pending", "Data"),
    ("Webhook retries flood the audit log", "open", "Platform"),
    ("Dark mode: unreadable chart legend", "closed", "UI"),
    ("Seat count not updated after downgrade", "pending", "Billing"),
]


class TicketView(ClientState):
    status: str = field(default="open")


def filter_a_list() -> None:
    status = TicketView().status
    with ui.card(padding="md", classes="w-full max-w-xl"), ui.vstack(gap="md"):
        ui.toggle_group(value=status, color="secondary",
                        options=[("open", "Open"), ("pending", "Pending"),
                                 ("closed", "Closed"), ("all", "All")])
        with ui.vstack(gap="xs", classes="w-full"):
            for title, ticket_status, team in TICKETS:
                shown = (status == "all") | (status == ticket_status)
                with ui.hstack(gap="sm", justify="between", visible=shown):
                    ui.text(title, truncate=True)
                    ui.badge(team, variant="soft", size="sm")


def page() -> None:
    page_header("toggle_group", "Toggle group", SUMMARY)
    example("Switch a view", view_switch,
            note="ui.toggle_button children give each item a label and an "
                 "icon; exactly one stays pressed.")
    example("A formatting toolbar", toolbar,
            note="multiple=True lets several buttons stay pressed. Icon-only "
                 "items carry a tooltip, and a single item can be disabled.")
    example("Billing period", billing_period,
            note="options= builds the buttons from (value, label) pairs "
                 "in one line.")
    example("Sizes", sizes)
    example("Filter a list", filter_a_list,
            uses=[TicketView],
            note="The group writes a ClientState and each ticket shows or "
                 "hides itself in the browser, with no request.")
