"""``/number-input`` — a number with its own stepper."""

from bretzel import ui
from bretzel.state import ClientState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("A number field with ± steppers, bounds and a step — arrow keys "
           "and the steppers never leave the range.")

SEAT_PRICE = 12.0


class SeatOrder(ClientState):
    seats: int = field(default=5)


def seat_calculator() -> None:
    seats = SeatOrder().seats
    with ui.card(padding="md", classes="w-full max-w-sm"), ui.vstack(gap="md"):
        with ui.form_field(label="Seats", hint="From 1 to 50 on the Team plan."):
            ui.number_input(value=seats, min=1, max=50)
        ui.divider()
        with ui.hstack(justify="between"):
            ui.text(seats + f" × €{SEAT_PRICE:.0f} / month", color="muted")
            ui.heading("€" + (seats * SEAT_PRICE).to_fixed(2), level=3, size="xl")


def bounds_and_steps() -> None:
    with ui.grid(cols={"base": 1, "sm": 3}, gap="md", classes="w-full max-w-2xl"):
        with ui.form_field(label="Discount (%)", hint="Steps of 5."):
            ui.number_input(value=15, min=0, max=100, step=5)
        with ui.form_field(label="Parcel weight (kg)", hint="Steps of 0.1."):
            ui.number_input(value=2.4, min=0.1, max=30, step=0.1)
        with ui.form_field(label="Retries", hint="Between 0 and 5."):
            ui.number_input(value=3, min=0, max=5)


def sizes() -> None:
    with ui.vstack(gap="sm", classes="w-full max-w-xs"):
        for size in ("xs", "sm", "md", "lg", "xl"):
            ui.number_input(size=size, placeholder=f"Quantity ({size})", min=0)


def booking() -> None:
    with ui.card(padding="md", classes="w-full max-w-lg"), ui.vstack(gap="md"):
        ui.heading("Harbour View Loft · 3 nights", level=3, size="md")
        with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
            with ui.form_field(label="Adults"):
                ui.number_input(value=2, min=1, max=6, color="secondary")
            with ui.form_field(label="Children"):
                ui.number_input(value=0, min=0, max=4, color="secondary")
            with ui.form_field(label="Pets", hint="Not allowed here."):
                ui.number_input(value=0, disabled=True)


def page() -> None:
    page_header("number_input", "Number input", SUMMARY)
    example("A seat calculator", seat_calculator,
            uses=[SeatOrder],
            note="The count lives in a ClientState: the total is computed in "
                 "the browser as you step.")
    example("Bounds and steps", bounds_and_steps,
            note="min and max clamp every change, step sets the increment — "
                 "decimals included.")
    example("Sizes", sizes)
    example("A booking form", booking,
            note="color= tints the focus ring; disabled keeps the value "
                 "visible but out of reach.")
