"""``/radio`` — exactly one choice among a few."""

from bretzel import ui
from bretzel.state import ClientState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("A group of options where exactly one is picked — all visible at "
           "once, in a column or a row.")


def delivery() -> None:
    with (ui.form_field(label="Delivery", classes="max-w-sm"),
          ui.radio_group(name="delivery", value="standard")):
        ui.radio("standard", label="Standard — 3 to 5 days, free")
        ui.radio("express", label="Express — next day, €9.90")
        ui.radio("pickup", label="Pick up at the Lyon store")


def in_a_row() -> None:
    with ui.vstack(gap="md", classes="w-full max-w-md"):
        with (ui.form_field(label="Table density"),
              ui.radio_group(name="density", value="comfortable", direction="row")):
            ui.radio("compact", label="Compact")
            ui.radio("comfortable", label="Comfortable")
            ui.radio("spacious", label="Spacious")
        with (ui.form_field(label="Start the week on"),
              ui.radio_group(name="week_start", value="monday", direction="row")):
            ui.radio("monday", label="Monday")
            ui.radio("sunday", label="Sunday")


PRICES = {"monthly": 29, "yearly": 24}


class Billing(ClientState):
    period: str = field(default="yearly")


def billing_period() -> None:
    period = Billing().period
    yearly = period == "yearly"
    with ui.card(padding="md", classes="w-full max-w-sm"), ui.vstack(gap="md"):
        ui.heading("Team plan", level=3, size="md")
        with ui.radio_group(value=period, direction="row"):
            ui.radio("monthly", label="Monthly")
            ui.radio("yearly", label="Yearly")
        with ui.hstack(gap="sm", align="end"):
            ui.heading("€" + yearly.then_else(PRICES["yearly"], PRICES["monthly"]),
                       level=3, size="3xl")
            ui.text("per seat / month", color="muted")
        ui.badge("You save €60 per seat each year", color="success",
                 variant="soft", visible=yearly)
        ui.badge("Cancel any time", color="secondary", variant="soft",
                 visible=~yearly)
        ui.button("Start free trial", classes="w-full")


def sizes() -> None:
    with ui.vstack(gap="md"):
        for size in ("sm", "md", "lg"):
            with ui.radio_group(name=f"size_{size}", value="on", size=size,
                                direction="row"):
                ui.radio("on", label=f"Size {size}")
                ui.radio("off", label="Not picked")


def review_verdict() -> None:
    with (ui.form_field(label="Your review", classes="max-w-md"),
          ui.radio_group(name="verdict", value="approve", direction="row")):
        ui.radio("approve", label="Approve", color="success")
        ui.radio("changes", label="Request changes", color="warning")
        ui.radio("reject", label="Reject", color="error")


def disabled() -> None:
    with (ui.form_field(label="Data residency", classes="max-w-sm"),
          ui.radio_group(name="residency", value="eu")):
        ui.radio("eu", label="European Union (Frankfurt)")
        ui.radio("us", label="United States (Virginia)")
        ui.radio("apac", label="Asia-Pacific — coming soon", disabled=True)


def page() -> None:
    page_header("radio_group", "Radio group", SUMMARY)
    example("Delivery options", delivery,
            note="ui.radio_group holds the value; each ui.radio is one "
                 "choice, with its own label. A group bound to no state "
                 "takes a name=.")
    example("In a row", in_a_row,
            note="direction=\"row\" for two or three short choices.")
    example("A choice that changes the price", billing_period, uses=[Billing],
            note="The group writes a ClientState; the price and the badge "
                 "follow in the browser, with no request.")
    example("Sizes", sizes)
    example("A colour per choice", review_verdict,
            note="color= on the group tints every radio; on a single radio it "
                 "tints that choice only — here, the verdict's meaning.")
    example("A disabled choice", disabled)
