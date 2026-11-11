"""``/tabs`` — several panels in the space of one."""

from bretzel import ui
from bretzel.state import ClientState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("Switch between panels without a round trip — with icons, sizes, "
           "colours, the active tab in the URL or in a state the page reads.")


def settings() -> None:
    with ui.tabs(value="profile", name="settings", classes="w-full"):
        ui.tab("profile", label="Profile", icon="user")
        ui.tab("notifications", label="Notifications", icon="bell")
        ui.tab("billing", label="Billing", icon="credit-card")
        with ui.tab_panel("profile"), ui.vstack(gap="md", classes="max-w-md pt-2"):
            with ui.form_field(label="Full name"):
                ui.input(value="Ada Lovelace", name="full_name")
            with ui.form_field(label="Job title"):
                ui.input(value="Head of Analytics", name="job_title")
        with ui.tab_panel("notifications"), ui.vstack(gap="sm", classes="pt-2"):
            ui.switch(label="Weekly digest", checked=True, name="digest")
            ui.switch(label="Mentions and replies", checked=True, name="mentions")
            ui.switch(label="Product announcements", name="announcements")
        with ui.tab_panel("billing"), ui.vstack(gap="xs", classes="pt-2"):
            ui.text("Team plan · 12 seats", weight="medium")
            ui.text("Next invoice: €240.00 on 1 October", color="muted")


def sizes() -> None:
    with ui.vstack(gap="lg", classes="w-full"):
        for size in ("sm", "md", "lg"):
            with ui.tabs(value="overview", size=size, name=f"size-{size}"):
                ui.tab("overview", label="Overview")
                ui.tab("activity", label="Activity")
                ui.tab("members", label="Members")


def colors() -> None:
    with ui.vstack(gap="lg", classes="w-full"):
        for color in ("primary", "secondary", "success"):
            with ui.tabs(value="open", color=color, name=f"color-{color}"):
                ui.tab("open", label="Open · 24")
                ui.tab("closed", label="Closed · 318")
                ui.tab("archived", label="Archived", disabled=True)


def linkable() -> None:
    with ui.tabs(value="overview", url="tab", name="project", classes="w-full"):
        ui.tab("overview", label="Overview", icon="layout-dashboard")
        ui.tab("activity", label="Activity", icon="activity")
        with ui.tab_panel("overview"):
            ui.text("Website redesign · 68 % done · due 14 November", color="muted")
        with ui.tab_panel("activity"):
            ui.text("Grace moved “Hero illustration” to Review, 5 minutes ago.",
                    color="muted")


FIGURES = {
    "week": ("€12.4k", "+4.1 %", "38 invoices"),
    "month": ("€48.2k", "+12.4 %", "184 invoices"),
    "quarter": ("€139.7k", "+9.8 %", "521 invoices"),
}


class Report(ClientState):
    period: str = field(default="month")


def bound_tabs() -> None:
    period = Report().period
    with ui.vstack(gap="md", classes="w-full"):
        with ui.tabs(value=period):
            ui.tab("week", label="This week")
            ui.tab("month", label="This month")
            ui.tab("quarter", label="This quarter")
        for key, (total, delta, count) in FIGURES.items():
            with ui.hstack(gap="md", align="end", visible=period == key):
                ui.heading(total, level=3, size="3xl")
                ui.badge(delta, color="success", variant="soft")
                ui.text(count, color="muted")


def page() -> None:
    page_header("tabs", "Tabs", SUMMARY)
    example("Settings sections", settings, full=True,
            note="ui.tab declares the strip, ui.tab_panel the content. "
                 "Switching is instant: it never calls the server.")
    example("Sizes", sizes, full=True)
    example("Colours and a disabled tab", colors, full=True)
    example("The active tab in the URL", linkable, full=True,
            note="url=\"tab\" writes ?tab=activity into the address bar, so a "
                 "link or a reload lands on the same tab.")
    example("The active tab, read elsewhere", bound_tabs, full=True,
            uses=[Report],
            note="value= is bound to a ClientState, so any part of the page "
                 "can follow the tab: here the figures, outside the strip. "
                 "Give on_change a Python function to load them from the "
                 "server instead.")
