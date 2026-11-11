"""``/histogram`` — raw values counted per tranche, the spread at a glance."""

from bretzel import refreshable, ui
from bretzel.state import PageState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("Give the raw values: the histogram counts them per tranche — per "
           "point, per step or between your own bounds — and marks the mean.")


def response_times() -> list[float]:
    return [182, 210, 195, 240, 260, 199, 305, 221, 188, 470, 233, 215, 251,
            199, 207, 342, 228, 190, 214, 236, 268, 201, 223, 289, 512, 245]


def latency() -> None:
    with ui.card(padding="md"), ui.vstack(gap="sm"):
        with ui.vstack(gap="none"):
            ui.text("API response time · last hour", size="sm", color="muted")
            ui.heading("p50 · 224 ms", level=3, size="2xl")
        ui.histogram(response_times(), x_min=150, x_max=550, step=50,
                     show_mean=True, x_label="ms", y_label="Requests", size="sm")


def ratings() -> list[float]:
    return [9, 10, 8, 7, 9, 10, 6, 9, 8, 10, 3, 9, 7, 8, 10, 9, 5, 10, 9, 8]


def nps() -> None:
    with ui.card(padding="md"), ui.vstack(gap="sm"):
        ui.text("Would you recommend us? · 0 to 10", size="sm", color="muted")
        ui.histogram(ratings(), x_min=0, x_max=10, show_values=True, size="sm",
                     color="success")


def bands() -> None:
    with ui.card(padding="md"), ui.vstack(gap="sm"):
        ui.text("Deal size · the sales team's bands", size="sm", color="muted")
        ui.histogram([1.2, 4.8, 2.5, 18, 7.5, 3.1, 42, 9.9, 5.5, 12, 1.8, 26, 6.2,
                      3.9, 15],
                     bins=[0, 5, 10, 25, 50], show_values=True, size="sm",
                     x_label="k$", color="info")


class Bucket(PageState):
    tranche: str = field(default="")


def pick_tranche(low: float, high: float) -> None:
    Bucket().tranche = f"{low}–{high} ms"


@refreshable
def bucket_detail() -> None:
    tranche = Bucket().tranche
    ui.text(f"Slow requests between {tranche}: the traces open here."
            if tranche else "Click a tranche to open its requests.",
            size="sm", color="muted")


def drilldown() -> None:
    with ui.card(padding="md"), ui.vstack(gap="sm"):
        ui.text("Response time · click a tranche", size="sm", color="muted")
        ui.histogram(response_times(), x_min=150, x_max=550, step=50,
                     on_item_click=pick_tranche, size="sm")
        bucket_detail()


def page() -> None:
    page_header("histogram", "Histogram", SUMMARY)
    example("A spread and its mean", latency, uses=[response_times], full=True,
            note="Raw values in; x_min, x_max and step set the tranches; "
                 "show_mean draws the mean over the bars.")
    example("Per point", nps, uses=[ratings], full=True,
            note="A step of 1 counts per point — the top of the scale is a "
                 "bar of its own.")
    example("Your own bounds", bands, full=True,
            note="bins= sets irregular tranches; a value outside them is "
                 "refused, not dropped.")
    example("A click that runs Python", drilldown,
            uses=[response_times, Bucket, pick_tranche, bucket_detail], full=True,
            note="on_item_click receives the tranche's bounds: (low, high).")
