"""``/switch`` — a setting that takes effect."""

from bretzel import refreshable, ui
from bretzel.state import ClientState, PageState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("An on/off rail for settings that apply at once — in the browser "
           "through a binding, or on the server through a handler.")


def setting_row(title: str, description: str, on: bool) -> None:
    # The text IS the switch's label: the whole row toggles on click, and a
    # screen reader names the switch by it. flex-row-reverse puts the rail
    # on the right.
    with ui.vstack(gap="none", tag="span") as text:
        ui.text(title, size="md", weight="medium")
        ui.text(description, size="sm", color="muted", weight="normal")
    ui.switch(checked=on, label=text,
              classes="w-full flex-row-reverse justify-between")


def notification_settings() -> None:
    with ui.card(padding="md", classes="w-full max-w-lg"), ui.vstack(gap="md"):
        setting_row("Mentions", "When someone @mentions you in a comment.", True)
        ui.divider()
        setting_row("Invoice paid", "Each time a customer settles an invoice.",
                    True)
        ui.divider()
        setting_row("Weekly report", "A summary of revenue every Monday at 9:00.",
                    False)


class ExportOptions(ClientState):
    advanced: bool = field(default=False)


def reveal_options() -> None:
    options = ExportOptions()
    with ui.vstack(gap="md", classes="w-full max-w-sm"):
        with ui.form_field(label="File format"):
            ui.select(["CSV", "Excel (.xlsx)", "JSON"], value="CSV")
        ui.switch(checked=options.advanced, label="Show advanced options")
        with ui.vstack(gap="md", visible=options.advanced):
            with ui.form_field(label="Delimiter"):
                ui.select([",", ";", "Tab"], value=";")
            ui.checkbox(label="Include archived customers")


class Workspace(PageState):
    maintenance: bool = field(default=False)


def maintenance_changed(workspace: Workspace) -> None:
    """The typed parameter receives the switch's value; the status follows."""


@refreshable
def workspace_status() -> None:
    if Workspace().maintenance:
        ui.alert("Sign-ins are paused. Your customers see the maintenance page.",
                 title="Maintenance mode is on", color="warning", icon="construction")
    else:
        ui.alert("Everything is running. 1,284 people signed in today.",
                 title="All systems normal", color="success", icon="circle-check")


def server_switch() -> None:
    with ui.vstack(gap="md", classes="w-full max-w-md"):
        ui.switch(checked=Workspace().maintenance, label="Maintenance mode",
                  color="warning", on_change=maintenance_changed)
        workspace_status()


def sizes_and_colors() -> None:
    with ui.vstack(gap="md"):
        with ui.hstack(gap="lg", wrap=True, justify="center"):
            for size in ("xs", "sm", "md", "lg", "xl"):
                ui.switch(label=f"Size {size}", size=size, checked=True)
        with ui.hstack(gap="lg", wrap=True, justify="center"):
            for color in ("primary", "secondary", "success", "warning", "error",
                          "info"):
                ui.switch(label=color.capitalize(), color=color, checked=True)
        with ui.hstack(gap="lg", wrap=True, justify="center"):
            ui.switch(label="Single sign-on (Business plan)", disabled=True)
            ui.switch(label="Audit log (always on)", checked=True, disabled=True)


def page() -> None:
    page_header("switch", "Switch", SUMMARY)
    example("A settings list", notification_settings, uses=[setting_row],
            note="The usual layout: the setting explained on the left, the "
                 "switch on the right — and the whole row is the label, so "
                 "a click anywhere on it toggles.")
    example("Show more options", reveal_options, uses=[ExportOptions],
            note="Bound to a ClientState, the switch shows the extra fields in "
                 "the browser, with no request.")
    example("A switch that runs Python", server_switch,
            uses=[Workspace, maintenance_changed, workspace_status],
            note="on_change sends the new value to Python; the status below "
                 "re-renders.")
    example("Sizes, colours, disabled", sizes_and_colors)
