"""``/month-picker`` — a month field with a year of months in a popover."""

from datetime import date

from bretzel import refreshable, ui
from bretzel.state import PageState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("A month field for billing periods, statements and reports: a "
           "year grid in a popover, and a plain YYYY-MM value.")


def billing_month() -> None:
    with ui.form_field(label="Billing month", classes="w-full max-w-xs"):
        ui.month_picker(value=date.today())


def statements() -> None:
    this_month = date.today().strftime("%Y-%m")
    with ui.grid(min_col="16rem", gap="md", classes="w-full max-w-xl"):
        with ui.form_field(label="Statement",
                           hint="Available since your account opened in "
                                "March 2025."):
            ui.month_picker(min="2025-03", max=this_month,
                            placeholder="Choose a month", color="secondary")
        with ui.form_field(label="Card expiry"):
            ui.month_picker(value="2028-11", clearable=False, name="expiry")


def sizes() -> None:
    with ui.vstack(gap="md", classes="w-full max-w-xs"):
        ui.month_picker(value="2026-01", size="sm", name="month-sm")
        ui.month_picker(value="2026-02", size="md", name="month-md")
        ui.month_picker(value="2026-03", size="lg", name="month-lg")
        ui.month_picker(value="2025-12", disabled=True, name="month-closed")


def last_month() -> str:
    first = date.today().replace(day=1)
    return date(first.year - (first.month == 1), (first.month - 2) % 12 + 1, 1
                ).strftime("%Y-%m")


class MonthlyReport(PageState):
    month: str = field(default_factory=last_month)


def change_month(report: MonthlyReport) -> None:
    """The picked month is already in ``report``; the KPIs re-render."""


@refreshable
def monthly_kpis() -> None:
    month = date.fromisoformat(MonthlyReport().month + "-01")
    seed = month.month + month.year % 10
    with ui.vstack(gap="sm", classes="w-full"):
        ui.heading(f"{month:%B %Y}", level=3, size="md")
        with ui.grid(cols=3, gap="md"):
            for label, value, color in (
                ("New customers", str(40 + seed * 7), "success"),
                ("Churned", str(3 + seed % 5), "error"),
                ("MRR", f"€{18_400 + seed * 910:,}", "primary"),
            ):
                with ui.vstack(gap="none"):
                    ui.text(label, color="muted", size="sm")
                    ui.text(value, size="xl", weight="semibold", color=color)


def monthly_report() -> None:
    with ui.card(padding="md", classes="w-full max-w-lg"), ui.vstack(gap="md"):
        ui.month_picker(value=MonthlyReport().month, clearable=False,
                        max=date.today(), on_change=change_month,
                        classes="max-w-xs")
        monthly_kpis()


def page() -> None:
    page_header("month_picker", "Month picker", SUMMARY)
    example("A billing month", billing_month,
            note="A date is accepted and truncated to its month; the value "
                 "reads back as “2026-09”.")
    example("Statements and expiry", statements,
            note="min and max grey out the months outside the window; a "
                 "placeholder when nothing is picked yet.")
    example("Sizes", sizes)
    example("A monthly report", monthly_report,
            uses=[last_month, MonthlyReport, change_month, monthly_kpis],
            note="on_change sends the month to Python; the figures "
                 "re-render.")
