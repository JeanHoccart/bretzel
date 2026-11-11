"""``/stat`` — a key figure, and what it means."""

from bretzel import ui
from examples.showcase.lib.example import example, page_header

SUMMARY = ("A number, its label and its change. Say what it means — a range, "
           "an objective, which way is better — and the gauge and its colour "
           "follow.")


def figures() -> None:
    with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
        ui.stat("Revenue", 48240, unit="€", delta="+12.4 %", description="vs August")
        ui.stat("Active customers", 1284, delta=36)
        ui.stat("Response time", 72, unit="min", delta=-9, good="down")


def gauges() -> None:
    with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
        ui.stat("Class average", 12.4, max=20, delta=0.8, description="vs first term")
        ui.stat("Copies typed", 19, max=24, target=24, description="Test of 12 November")
        ui.stat("Skill mastered", 71, unit="%", max=100, target=60)


def less_is_better() -> None:
    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
        ui.stat("Below 10", 4, unit="pupils", max=28, target=2, good="down", delta=-2)
        ui.stat("Churn", 2.1, unit="%", target=2, good="down", delta="+0.3 pt")


def page() -> None:
    page_header("stat", "Stat", SUMMARY)
    example("A number and its change", figures, full=True,
            note="The page writes the number in its language; delta= is "
                 "signed for you and green the good way.")
    example("A range draws a gauge", gauges, full=True,
            note="max= gives the range; target= marks the objective — green "
                 "reached, orange not.")
    example("Less is better", less_is_better, full=True,
            note="good=\"down\" turns it around: fewer pupils below 10 is a "
                 "success. Without max=, the objective is said in a line.")
