"""``/slider`` — drag to pick a number, or a range of them."""

from bretzel import ui
from bretzel.state import ClientState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("Drag, click the track or use the arrow keys — one handle for a "
           "value, two for a range, and the live value above the thumb.")


def volume() -> None:
    with ui.hstack(gap="sm", classes="w-full max-w-sm"):
        ui.icon("volume-1", color="muted")
        ui.slider(value=65, classes="flex-1")
        ui.icon("volume-2", color="muted")


def default_price() -> list[int]:
    return [40, 220]


class PriceFilter(ClientState, persist="memory"):
    price: list = field(default_factory=default_price)


def price_range() -> None:
    price = PriceFilter().price
    with ui.card(padding="md", classes="w-full max-w-sm"), ui.vstack(gap="md"):
        with ui.hstack(justify="between"):
            ui.text("Price per night", weight="medium")
            ui.text("€" + price.join(" – €"), color="muted", classes="font-mono")
        ui.slider(value=price, range=True, min=0, max=500, step=10)


def resource_limits() -> None:
    with ui.vstack(gap="lg", classes="w-full max-w-sm"):
        with ui.form_field(label="CPU (vCPU)"):
            ui.slider(value=4, min=1, max=16)
        with ui.form_field(label="Memory (GB)"):
            ui.slider(value=24, min=4, max=64, step=4, color="success")
        with ui.form_field(label="Burst budget (%)"):
            ui.slider(value=30, color="warning")
        with ui.form_field(label="Replicas", hint="Fixed on the Starter plan."):
            ui.slider(value=2, min=1, max=10, disabled=True)


def sizes() -> None:
    with ui.vstack(gap="lg", classes="w-full max-w-sm"):
        for level, size in enumerate(("xs", "sm", "md", "lg", "xl")):
            ui.slider(value=20 + level * 15, size=size)


class SeatPlan(ClientState):
    seats: int = field(default=12)


def seat_pricing() -> None:
    seats = SeatPlan().seats
    with ui.card(padding="md", classes="w-full max-w-sm"), ui.vstack(gap="md"):
        ui.text("Team seats", weight="medium")
        ui.slider(value=seats, min=1, max=50)
        with ui.hstack(justify="between"):
            ui.text(seats + " seats × €12", color="muted")
            ui.heading("€" + seats * 12 + " / month", level=3, size="lg")


def page() -> None:
    page_header("slider", "Slider", SUMMARY)
    example("Volume", volume,
            note="One handle between two icons; the value pops up while "
                 "you drag.")
    example("A price range", price_range, uses=[default_price, PriceFilter],
            note="range=True gives two handles and a [low, high] value. Bound "
                 "to a ClientState, the label follows without a round trip.")
    example("Resource limits", resource_limits,
            note="min, max and step fit the unit; colour tells the settings "
                 "apart, and disabled locks one.")
    example("Sizes", sizes)
    example("Price a plan", seat_pricing, uses=[SeatPlan],
            note="The quote is computed in the browser while you drag. A "
                 "Python on_change fires once, when the handle settles.")
