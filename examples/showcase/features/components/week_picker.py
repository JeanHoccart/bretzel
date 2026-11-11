"""``/week-picker`` — pick a whole week by clicking any of its days."""

from datetime import date, timedelta

from bretzel import refreshable, ui
from bretzel.state import PageState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("A week field: click any day and the whole row is picked. The "
           "value is the week's first day.")


def this_week() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())


def timesheet() -> None:
    with ui.form_field(label="Timesheet week", classes="w-full max-w-xs"):
        ui.week_picker(value=this_week())


def rota() -> None:
    monday = this_week()
    shifts = {monday + timedelta(days=offset): 1 for offset in (2, 3, 9, 16, 17)}
    with ui.grid(min_col="16rem", gap="md", classes="w-full max-w-xl"):
        with ui.form_field(label="Store rota",
                           hint="Weeks start on Sunday. A dot marks your "
                                "shifts."):
            ui.week_picker(value=monday - timedelta(days=1), week_start=0,
                           marks=shifts, color="secondary")
        with ui.form_field(label="Payroll week",
                           hint="Closed weeks cannot be reopened."):
            ui.week_picker(value=monday - timedelta(days=14), disabled=True,
                           name="payroll")


def sizes() -> None:
    monday = this_week()
    with ui.vstack(gap="md", classes="w-full max-w-xs"):
        for offset, size in enumerate(("sm", "md", "lg")):
            ui.week_picker(value=monday + timedelta(weeks=offset), size=size,
                           name=f"week-{size}")


def next_week() -> str:
    return (this_week() + timedelta(weeks=1)).isoformat()


class Sprint(PageState):
    week: str = field(default_factory=next_week)


def plan_sprint(sprint: Sprint) -> None:
    """The picked week is already in ``sprint``; the plan re-renders."""


@refreshable
def sprint_plan() -> None:
    start = date.fromisoformat(Sprint().week)
    end = start + timedelta(days=4)
    ceremonies = [("Planning", start), ("Design review", start + timedelta(days=2)),
                  ("Demo & retro", end)]
    with ui.vstack(gap="sm", classes="w-full"):
        ui.text(f"Sprint {start.isocalendar().week} · {start:%b} {start.day} – "
                f"{end:%b} {end.day}", weight="medium")
        for name, day in ceremonies:
            with ui.hstack(justify="between"):
                ui.text(name)
                ui.text(f"{day:%A}", color="muted", size="sm")


def plan_a_sprint() -> None:
    with ui.card(padding="md", classes="w-full max-w-sm"), ui.vstack(gap="md"):
        with ui.form_field(label="Sprint week"):
            ui.week_picker(value=Sprint().week, clearable=False,
                           on_change=plan_sprint)
        ui.divider()
        sprint_plan()


def page() -> None:
    page_header("week_picker", "Week picker", SUMMARY)
    example("A timesheet week", timesheet, uses=[this_week],
            note="Click any day: the row lights up and the value snaps to "
                 "its Monday. A typed date snaps the same way.")
    example("Rota and payroll", rota, uses=[this_week],
            note="week_start=0 for Sunday weeks, marks on the days that "
                 "matter, and a disabled field.")
    example("Sizes", sizes, uses=[this_week])
    example("Plan a sprint", plan_a_sprint,
            uses=[this_week, next_week, Sprint, plan_sprint, sprint_plan],
            note="on_change sends the week to Python; the sprint plan "
                 "re-renders.")
